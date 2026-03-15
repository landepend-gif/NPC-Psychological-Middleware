import chromadb
import ollama # 保留 Ollama 用于本地 Embedding (速度快/免费)
import uuid
import datetime
import os
import re
import json
from openai import OpenAI # 引入 OpenAI 库
from dotenv import load_dotenv
from core.llm_client import client

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "chromadb")
PROMPTS_PATH = os.path.join(BASE_DIR, "config", "memory_prompts.json")

#load_dotenv() # 加载 .env 文件

class MemoryManager:
    def __init__(self, npc_name, llm_model='deepseek-ai/DeepSeek-V3.2'):
        self.npc_name = npc_name
        self.llm_model = llm_model

        # 1. 使用共享的 LLM 客户端
        self.client = client

        # 加载 Prompt
        self.prompts = self._load_prompts()

        # 确保路径存在
        os.makedirs(DB_PATH, exist_ok=True)

        #  2: 给 ChromaDB 客户端改名，防止和上面的 self.client 冲突
        self.chroma_client = chromadb.PersistentClient(path=DB_PATH) 

        # 使用改名后的 chroma_client 来创建集合
        self.collection = self.chroma_client.get_or_create_collection(name=f"memory_{npc_name}")
        
        self.embedding_model = 'nomic-embed-text' 
        self.recent_importance_accumulator = 0
        self.REFLECTION_THRESHOLD = 20 

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

        if type == "observation":
            self.recent_importance_accumulator += importance
            if self.recent_importance_accumulator >= self.REFLECTION_THRESHOLD:
                self._trigger_reflection()
                self.recent_importance_accumulator = 0 

    # --- 重要性打分 (调用 API) ---
    def _evaluate_importance(self, text):
        template = self.prompts.get("importance_scoring")
        if template:
            prompt = template.format(npc_name=self.npc_name, description=text)
        else:
            prompt = f"请对以下记忆片段对于{self.npc_name}的重要性打分(1-10)。记忆：{text}"
            
        try:
            # 这里调用 self.client (OpenAI) 
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.1,
                max_tokens=10 
            )
            content = response.choices[0].message.content.strip()
            match = re.search(r'\d+', content)
            if match:
                return max(1, min(10, int(match.group())))
            return 5
        except Exception as e:
            print(f"❌ 评分失败: {e}")
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

    # --- 检索 ---
    def search_memory(self, query, n_results=3):
        vec = self.get_embedding(query)
        if not vec: return []

        results = self.collection.query(
            query_embeddings=[vec], 
            n_results=n_results
        )
        return results['documents'][0] if results['documents'] else []

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