# core/llm_client.py
import os
from dotenv import load_dotenv # 需要 pip install python-dotenv
from openai import OpenAI

# 1. 加载环境变量
load_dotenv()

# 2. 读取配置
api_key = os.getenv("SILICON_API_KEY")
base_url = "https://api.siliconflow.cn/v1"

# 安全检查
if not api_key:
    # 也可以选择打印警告而不是报错，看你偏好
    raise ValueError("❌ 严重错误: 未在 .env 文件中找到 SILICON_API_KEY！")

print(f"🔌 [系统]: 正在初始化共享 LLM 客户端...")

# 3. 实例化全局唯一的 client
# 所有的模块 import 这个变量时，拿到的都是同一个对象
client = OpenAI(
    api_key=api_key, 
    base_url=base_url
)