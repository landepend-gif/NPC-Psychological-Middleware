import chromadb
import ollama # 保留 Ollama 用于本地 Embedding (速度快/免费)
import uuid
import datetime
import os
# 关闭 Tokenizer 的内部并行，防止在后台子线程中死锁崩溃
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import re
import json
from openai import OpenAI # 引入 OpenAI 库
from dotenv import load_dotenv
from core.llm_client import client
from transformers import pipeline

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "chromadb")
PROMPTS_PATH = os.path.join(BASE_DIR, "config", "memory_prompts.json")

#load_dotenv() # 加载 .env 文件

class MemoryManager:
    def __init__(self, npc_name, llm_model='deepseek-ai/DeepSeek-V3.2'):
        self.npc_name = npc_name
        self.llm_model = llm_model
        self.client = client
        self.prompts = self._load_prompts()

        os.makedirs(DB_PATH, exist_ok=True)

        #  2: 给 ChromaDB 客户端改名，防止和上面的 self.client 冲突
        self.chroma_client = chromadb.PersistentClient(path=DB_PATH) 

        # 使用改名后的 chroma_client 来创建集合
        self.collection = self.chroma_client.get_or_create_collection(name=f"memory_{npc_name}")
        
        self.embedding_model = 'nomic-embed-text' 
        self.recent_importance_accumulator = 0
        self.REFLECTION_THRESHOLD = 20 

        # 从本地文件夹加载 Transformer 评分中枢
        try:
            # 使用项目根目录拼接出绝对路径，彻底避免相对路径报错
            local_model_path = os.path.join(BASE_DIR, "models", "roberta-jd-finetuned")
            print(f"⏳ 正在为 {npc_name} 从本地读取 Transformer ({local_model_path})...")
            
            # 直接将路径传给 model 参数
            self.scorer = pipeline("text-classification", model=local_model_path)
            print(f"✅ {npc_name} 的评分中枢加载完成！")
            
        except Exception as e:
            print(f"❌ 模型加载失败，将使用默认分数: {e}")
            self.scorer = None

    def _load_prompts(self):
        try:
            if not os.path.exists(PROMPTS_PATH):
                return {}
            with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加载 Prompt 失败: {e}")
            return {}

    def get_embedding(self, text):
        try:
            return ollama.embeddings(model=self.embedding_model, prompt=text)['embedding']
        except Exception as e:
            print(f"❌ Embedding 失败 (检查本地 Ollama): {e}")
            return []
    
    # --- 存入记忆 ---
    def add_memory(self, text, type="observation", importance=None):
        if importance is None:
            importance = self._evaluate_importance(text)

        mem_id = str(uuid.uuid4())
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        embedding = self.get_embedding(text)
        if not embedding: 
            print(f"❌ [Memory] Embedding 生成失败，请检查 Ollama 服务！记忆未保存: {text[:20]}...")
            return 

        self.collection.add(
            ids=[mem_id],
            documents=[text], 
            embeddings=[embedding],
            metadatas=[{
                "type": type,
                "importance": importance,
                "timestamp": current_time
            }]
        )
        print(f"💾 [存入]: '{text}' (类型:{type}, 重要性:{importance})")

        # 修复反思断层，让普通聊天和观察都能触发反思
        if type in ["observation", "conversation"]:
            self.recent_importance_accumulator += importance
            
            if self.recent_importance_accumulator >= self.REFLECTION_THRESHOLD:
                self._trigger_reflection()
                self.recent_importance_accumulator = 0

    # --- 重要性打分 (调用 API改为纯本地transformer) ---
    def _evaluate_importance(self, text):
        if not self.scorer:
            return 5 # 如果模型没加载成功，默认返回5分

        try:
            # 截断文本防止超长报错 (一般模型 max_length 是 512)
            safe_text = text[:500] 
            
            # Transformer 前向推理 (耗时通常在 20ms 左右)
            result = self.scorer(safe_text)[0]
            
            # result 格式类似于：{'label': 'positive (stars 4 and 5)', 'score': 0.98}
            # 我们将置信度 score (0.5 ~ 1.0) 映射放大到 1~10 分
            raw_score = result['score']
            
            # 数学映射逻辑：如果情绪极其强烈(无论是极好还是极坏)，置信度都会很高
            # 假设 0.5 是中立，1.0 是极端。
            importance_float = abs(raw_score - 0.5) * 20 
            
            # 向上取整并限制在 1-10 之间
            final_importance = max(1, min(10, int(importance_float) + 1))
            
            return final_importance
            
        except Exception as e:
            print(f"❌ 评分计算异常: {e}")
            return 5

    # --- 反思 (调用 API) ---
    def _trigger_reflection(self):
        print(f"\n🤔 {self.npc_name} 正在陷入沉思...")

        recent_mems = self.collection.peek(limit=5) 
        if not recent_mems['documents']: return

        context_str = "\n".join([f"- {doc}" for doc in recent_mems['documents'][0]])

        template = self.prompts.get("reflection_generation")
        if template:
            prompt = template.format(npc_name=self.npc_name, memory_stream=context_str)
        else:
            prompt = f"基于最近经历提炼一个观点：\n{context_str}"

        try:
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.7 
            )
            insight = response.choices[0].message.content.strip()
            
            print(f"✨ [灵光一闪]: {insight}")
            self.add_memory(text=insight, type="reflection", importance=8)
            
        except Exception as e:
            print(f"❌ 反思失败: {e}")

    # --- 检索 (融合重要性加权的混合检索) ---
    def search_memory(self, query, n_results=3):
        vec = self.get_embedding(query)
        if not vec: return []

        # 第一步：先用向量库粗筛出候选池（取需要的 3 倍数量，扩大召回率）
        candidate_count = n_results * 3
        results = self.collection.query(
            query_embeddings=[vec], 
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"] # 必须把距离和元数据拿出来
        )
        
        # 如果什么都没搜到，直接返回空
        if not results['documents'] or not results['documents'][0]:
            return []

        docs = results['documents'][0]
        metas = results['metadatas'][0]
        distances = results['distances'][0] # ChromaDB 默认距离越小越相似

        # 第二步：混合打分重排 (Re-ranking)
        scored_memories = []
        for i in range(len(docs)):
            doc = docs[i]
            meta = metas[i]
            dist = distances[i]
            
            # 获取存入时的重要性分数，如果没有则默认为 5 分
            importance = meta.get('importance', 5)
            
            # 1. 将 ChromaDB 的距离转换为相似度得分 (距离越小，得分越高)
            sim_score = 1 / (1 + dist) 
            
            # 2. 归一化重要性 (将 1-10 分映射到 0.1-1.0)
            imp_score = importance / 10.0
            
            # 3. 黄金检索公式：语义相似度占 70%，记忆重要性占 30%
            final_score = (0.7 * sim_score) + (0.3 * imp_score)
            
            scored_memories.append({
                "doc": doc,
                "score": final_score
            })
            
        # 第三步：按最终混合得分从高到低排序
        scored_memories.sort(key=lambda x: x["score"], reverse=True)
        
        # 第四步：切片返回得分最高的前 n_results 条纯文本记忆
        final_docs = [item["doc"] for item in scored_memories[:n_results]]
        
        return final_docs

    # --- 获取所有记忆流 (供前端可视化展示) ---
    def get_all_memories(self, limit=50):
        try:
            # 从 ChromaDB 获取最近的 limit 条记录
            results = self.collection.get(limit=limit)
            mems = []
            if not results or not results.get('ids'): return []
            
            for i in range(len(results['ids'])):
                mems.append({
                    "id": results['ids'][i],
                    "text": results['documents'][i],
                    "metadata": results['metadatas'][i]
                })
            
            # 按照时间戳倒序排列（最新的在最上面）
            mems.sort(key=lambda x: x['metadata'].get('timestamp', ''), reverse=True)
            return mems
        except Exception as e:
            print(f"❌ 获取记忆流失败: {e}")
            return []