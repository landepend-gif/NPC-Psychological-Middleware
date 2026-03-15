import uvicorn
import os
import sys
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 引入核心逻辑
# 确保 sys.path 包含了当前目录，以便能找到 core 包
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.npc_agent import NPCAgent
from core.world import WorldManager

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_npcs = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 🔥 修复：取消注释，因为后面 load_characters_config 用到了它
CONFIG_PATH = os.path.join(BASE_DIR, "config", "characters.json")

# 初始化世界管理器
world_mgr = WorldManager(os.path.join(BASE_DIR, "config", "world.json"))

class ChatRequest(BaseModel):
    character_id: str
    user_input: str

# --- 读取角色列表的辅助函数 ---
def load_characters_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 无法读取配置文件: {e}")
        return {}

def get_npc(char_id: str):
    if char_id not in active_npcs:
        print(f"🔄 初始化角色: {char_id}")
        agent = NPCAgent(char_id)
        active_npcs[char_id] = agent
        # 初始化时注册位置
        loc = agent.state.get("current_location", "大雪山剑庐")
        world_mgr.update_npc_location(char_id, loc)
    return active_npcs[char_id]

# --- 🔥 新增接口：获取世界地图配置 (配合前端渲染) ---
@app.get("/world")
def get_world_info():
    """
    返回所有地点的名称和描述，供前端按地点分组显示角色
    """
    # 这里 world_mgr.config_data 对应 world.json 的内容
    return world_mgr.config_data

# --- 获取所有角色列表 ---
@app.get("/characters")
def get_character_list():
    """
    前端初始化时调用，返回所有可用的角色信息
    """
    data = load_characters_config()
    char_list = []
    
    # 🔥 预加载所有角色到内存，确保旁观者听力生效
    # 如果不先 get_npc，那些没聊过天的 NPC 就不在 active_npcs 里，也就不在世界里，无法旁听
    for cid in data.keys():
        get_npc(cid)

    for cid, info in data.items():
        npc_temp = get_npc(cid) 
        char_list.append({
            "id": cid,
            "name": info.get("name"),
            "role": info.get("role"),
            "location": npc_temp.state.get("current_location") # 返回位置
        })
    return char_list

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    try:
        # 1. 获取主角 NPC
        main_npc = get_npc(request.character_id)
        current_loc = main_npc.state.get("current_location")
        
        # 确保位置同步
        world_mgr.update_npc_location(request.character_id, current_loc)

        # 2. 【广播：玩家说话】让同场景的其他 NPC 听到
        bystanders = world_mgr.get_npcs_in_location(current_loc, exclude_id=request.character_id)
        for bid in bystanders:
            other_npc = get_npc(bid)
            other_npc.observe(
                speaker_name="玩家", 
                target_name=main_npc.config['name'], 
                content=request.user_input
            )

        # 3. 主角思考与回复
        response = main_npc.chat(request.user_input)
        
        # 4. 【广播：主角回复】让同场景的其他 NPC 听到主角的话
        npc_reply = response.get('dialogue', '')
        for bid in bystanders:
            other_npc = get_npc(bid)
            other_npc.observe(
                speaker_name=main_npc.config['name'], 
                target_name="玩家", 
                content=npc_reply
            )

        # 5. 如果主角移动了，更新世界地图
        new_loc = response.get('current_location')
        if new_loc != current_loc:
            world_mgr.update_npc_location(request.character_id, new_loc)

        return {"status": "success", "data": response}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{character_id}")
def get_status(character_id: str):
    try:
        npc = get_npc(character_id)
        return {
            "character": npc.config.get("name"),
            "role": npc.config.get("role", ""),
            "emotion": npc.psychology.get_emotion_label(),
            "pad": npc.psychology.current_pad,
            "trust": npc.state.get("trust", 0),
            "location": npc.state.get("current_location"),
            "ocean": npc.config.get("ocean", {})
        }
    except Exception as e:
        return {"character": "未加载", "emotion": "未知", "pad": [0,0,0], "trust": 0, "ocean": {}}

# --- 获取全量 UI 历史记录接口 ---
@app.get("/history/{character_id}")
def get_history(character_id: str):
    try:
        npc = get_npc(character_id)
        # 直接返回在 npc_agent 中存好的全量展示日志
        history_log = npc.state.get("full_chat_log", [])
        return {"status": "success", "data": history_log}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- 获取 NPC 的长期向量记忆流 ---
@app.get("/memory/{character_id}")
def get_npc_memory(character_id: str):
    try:
        npc = get_npc(character_id)
        # 调用刚才写好的获取记忆方法
        mems = npc.memory.get_all_memories(limit=30)
        return {"status": "success", "data": mems}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 1. 定义接收前端数据的模型
class CharacterConfigData(BaseModel):
    char_id: str
    name: str
    role: str
    ocean: dict
    seeds: list

# 2. 获取所有配置（角色 + 记忆种子）
@app.get("/config/all")
def get_all_config():
    try:
        char_path = os.path.join(BASE_DIR, "config", "characters.json")
        seed_path = os.path.join(BASE_DIR, "config", "seeds.json")
        
        chars = json.load(open(char_path, 'r', encoding='utf-8')) if os.path.exists(char_path) else {}
        seeds = json.load(open(seed_path, 'r', encoding='utf-8')) if os.path.exists(seed_path) else {}
        
        return {"status": "success", "data": {"characters": chars, "seeds": seeds}}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 3. 保存新建/修改的角色
@app.post("/config/character")
def save_character(data: CharacterConfigData):
    try:
        char_path = os.path.join(BASE_DIR, "config", "characters.json")
        seed_path = os.path.join(BASE_DIR, "config", "seeds.json")
        
        # 保存基础设定和人格
        chars = json.load(open(char_path, 'r', encoding='utf-8')) if os.path.exists(char_path) else {}
        chars[data.char_id] = {"name": data.name, "role": data.role, "ocean": data.ocean}
        with open(char_path, 'w', encoding='utf-8') as f:
            json.dump(chars, f, ensure_ascii=False, indent=4)
            
        # 保存种子记忆
        seeds = json.load(open(seed_path, 'r', encoding='utf-8')) if os.path.exists(seed_path) else {}
        seeds[data.char_id] = data.seeds
        with open(seed_path, 'w', encoding='utf-8') as f:
            json.dump(seeds, f, ensure_ascii=False, indent=4)
            
        return {"status": "success", "message": f"角色 {data.name} 保存成功！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)