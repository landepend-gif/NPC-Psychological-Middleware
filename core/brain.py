#import ollama
import json
import re
import os
from openai import OpenAI
from dotenv import load_dotenv
from core.llm_client import client

# 获取 prompt 文件的路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(BASE_DIR, "config", "system_prompt.txt")

#load_dotenv() # 加载 .env 文件

class Brain:
    def __init__(self, model_name='deepseek-ai/DeepSeek-V3.2'):
        self.model_name = model_name
        self.client = client
        # 初始化时加载 system_prompt.txt
        self.system_prompt_template = self._load_prompt_template()

    def _load_prompt_template(self):
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            print(f"❌ [Brain] 警告: 找不到 {PROMPT_PATH}，将使用默认简易 Prompt")
            return "你是一个 NPC，请用 JSON 格式回复。用户输入: {user_input}"

    def clean_json_string(self, json_str):
        """
        清洗 LLM 输出的字符串，去除 Markdown 标记
        """
        clean_str = re.sub(r'```json\s*', '', json_str)
        clean_str = re.sub(r'```', '', clean_str)
        return clean_str.strip()

    def think(self, user_text, profile, memory_context, history_context, pad_values, mood_label, trust, current_location, valid_locations):
        """
        根据心理状态和记忆进行思考
        """
        
        # 1. 准备填充模板所需的数据
        name = profile.get('name', 'NPC')
        role = profile.get('role', '未知职业')
        personality = profile.get('personality', '无')
        speaking_style = profile.get('speaking_style', '正常说话')
        ocean = profile.get('ocean', {})
        
        # 格式化 PAD
        p, a, d = pad_values
        pad_str = f"P:{p:.2f}, A:{a:.2f}, D:{d:.2f}"

        # 2. 填充 system_prompt.txt
        try:
            system_prompt = self.system_prompt_template.format(
                name=name,
                role=role,
                personality=personality,
                speaking_style=speaking_style,
                ocean_ocean=ocean, # 注意：如果txt里写的是 {ocean[O]}，这里传字典即可；如果是 {ocean} 则传字符串
                # 为了兼容性，建议在 txt 里用 {ocean[O]} 等方式读取，这里传入 ocean=ocean
                ocean=ocean, 
                pad_str=pad_str,
                emotion=mood_label,
                trust=trust,
                memory_context=memory_context,   # 长期记忆
                history_context=history_context, # 短期记忆 
                user_input=user_text,
                current_location=current_location,
                valid_locations=valid_locations
            )
        except KeyError as e:
            print(f"❌ [Brain] Prompt 格式化缺少参数: {e}")
            # 降级处理，避免程序崩溃
            system_prompt = f"系统错误：Prompt 参数缺失 {e}。用户输入：{user_text}"
        except Exception as e:
            print(f"❌ [Brain] Prompt 发生未知错误: {e}")
            system_prompt = user_text

        # 3. 调用 API
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_text}
                ],
                # 如果报错，可以尝试去掉 response_format 这一行，或者改为 text 模式再解析
                response_format={ 'type': 'json_object' }, 
                temperature=0.7 # 小模型建议温度稍微低一点，保持稳定
            )
            
            raw_content = response.choices[0].message.content
            clean_content = self.clean_json_string(raw_content)
            result = json.loads(clean_content)
            return result

        except Exception as e:
            print(f"❌ [Brain API Error]: {e}")
            return {
                "thought": "（意识模糊）...",
                "dialogue": "......",
                "pleasure_change": 0.0, "arousal_change": 0.0, "dominance_change": 0.0, "trust_change": 0
            }

        