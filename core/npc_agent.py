import json
import os
import time
import threading  # 引入多线程模块
from core.memory import MemoryManager
from core.brain import Brain
from core.psychology import PsychologyEngine 
from core.world import WorldManager  

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLD_CONFIG_PATH = os.path.join(BASE_DIR, "config", "world.json")

class NPCAgent:
    def __init__(self, character_id):
        self.char_id = character_id
        
        # 1. 初始化世界管理器 (用于获取默认地点和校验)
        self.world_mgr = WorldManager(WORLD_CONFIG_PATH)

        # 2. 加载静态配置 
        self.config = self._load_config(character_id)
        if not self.config:
            print(f"⚠️ 警告: 未找到角色 '{character_id}' 的配置，将使用默认值。")
            self.config = {"name": "Unknown NPC", "role": "Villager"}

        # 3. 加载动态存档
        self.state = self._load_save_data() 

        # 初始化 UI 专用的全量对话记录账本
        if "full_chat_log" not in self.state:
            self.state["full_chat_log"] = []

        # 4. 准备初始化数据
        saved_pad = self.state.get("pad")
        config_pad = self.config.get("pad", [0, 0, 0])
        start_pad = saved_pad if saved_pad else config_pad
        
        last_time = self.state.get("last_interaction_time")
        ocean_data = self.config.get("ocean", {}) 

        # --- ：位置初始化与清洗 ---
        # 无论存档里写的是什么，先扔给 WorldManager 检查一遍
        raw_loc = self.state.get("current_location")
        self.state["current_location"] = self.world_mgr.validate_location(raw_loc)
        
        if "is_following" not in self.state:
            self.state["is_following"] = False

        # 5. 初始化组件
        self.memory = MemoryManager(character_id)
        self.brain = Brain()
        
        # 心理引擎初始化  
        self.psychology = PsychologyEngine(
            ocean_data=ocean_data, 
            initial_pad=start_pad,
            last_update_time=last_time 
        )

        # 6. 模拟“离线期间”的情绪沉淀
        if last_time:
            old_pad, new_pad, seconds = self.psychology.process_time_decay()
            hours = seconds / 3600
            if hours > 1:
                old_str = f"[P:{old_pad[0]:.2f}, A:{old_pad[1]:.2f}]"
                new_str = f"[P:{new_pad[0]:.2f}, A:{new_pad[1]:.2f}]"
                print(f"⏰ [系统]: 距离上次见面已过去 {hours:.1f} 小时...")
                print(f"   NPC 情绪已平复: {old_str} -> {new_str}")

        # 7. 检查并注入种子记忆
        if not self.state.get("seeds_injected", False):
            print(f"🌱 [系统]: 检测到 {self.config.get('name', 'NPC')} 初次觉醒，正在植入背景记忆...")
            self._inject_seed_memories()

        # 8. 短期记忆缓冲区
        self.history = [] 
        self.MAX_HISTORY = 10 

    def _load_config(self, char_id):
        path = os.path.join(BASE_DIR, "config", "characters.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(char_id, {})
        except:
            return {}

    def _load_save_data(self):
        save_path = os.path.join(BASE_DIR, "data", "saves", f"{self.char_id}_save.json")
        if os.path.exists(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    print(f"📂 [系统]: 读取存档成功 -> {save_path}")
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 存档读取失败 ({e})，将重置状态。")
                return {}
        else:
            print(f"✨ [系统]: 无存档，新建初始状态")
            return {"trust": 0, "pad": [0,0,0]}

    def _inject_seed_memories(self):
        seeds_path = os.path.join(BASE_DIR, "config", "seeds.json")
        try:
            with open(seeds_path, "r", encoding="utf-8") as f:
                all_seeds = json.load(f)
            my_seeds = all_seeds.get(self.char_id, [])
            if not my_seeds:
                self.state["seeds_injected"] = True
                self.save_state()
                return
            for seed_text in my_seeds:
                self.memory.add_memory(seed_text, type="background", importance=10)
            self.state["seeds_injected"] = True
            self.save_state()
            print(f"✅ [系统]: 成功植入 {len(my_seeds)} 条背景记忆！")
        except:
            pass

    # 旁观者观察模式 (听力)
    def observe(self, speaker_name, target_name, content):
        log_text = f"【旁听】我听到 {speaker_name} 对 {target_name} 说: \"{content}\""
        print(f"👂 [{self.config.get('name')}] 正在偷听: {log_text[:30]}...")
        self.history.append(f"[Overheard] {speaker_name} -> {target_name}: {content}")
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]
        # 将记忆存储放入后台线程执行，防止反思机制阻塞主线程
        threading.Thread(target=self.memory.add_memory, args=(log_text, "observation", 3)).start()

    def chat(self, user_input):
        """
        NPC 的主交互循环
        """
        # --- 1. 检索长期记忆(RAG) ---
        memories = self.memory.search_memory(user_input, n_results=2)
        if memories and isinstance(memories, list):
            memory_str = "\n".join([f"- {m}" for m in memories]) 
        else:
            memory_str = "（暂无相关记忆）"

        # --- 2. 准备短期记忆 ---
        if self.history:
            history_str = "\n".join(self.history)
        else:
            history_str = "（对话刚开始）"

        # --- 3. 获取当前心理状态 ---
        current_pad = self.psychology.current_pad
        current_mood = self.psychology.get_emotion_label()
        current_trust = self.state.get("trust", 0)
        current_loc = self.state.get("current_location", "未知地点")

        # --- 4. 获取合法地点列表 ---
        # 直接调用 world_mgr 的方法，不需要这里再读文件了
        valid_locations_list = self.world_mgr.get_valid_locations_list()
        valid_locations_str = "、".join(valid_locations_list)

        # --- 5. 调用大脑 (Brain) ---
        result = self.brain.think(
            user_text=user_input, 
            profile=self.config,             
            memory_context=memory_str,   
            history_context=history_str, 
            pad_values=current_pad,
            mood_label=current_mood,
            trust=current_trust,
            current_location=current_loc,
            valid_locations=valid_locations_str 
        )

        # --- 6. 接收刺激并更新心理 ---
        stimulus = {
            "P": float(result.get("pleasure_change", 0)),
            "A": float(result.get("arousal_change", 0)),
            "D": float(result.get("dominance_change", 0))
        }
        self.psychology.update_pad(stimulus)

        # --- 7. 更新好感度 ---
        raw_trust_change = result.get("trust_change", 0)
        try:
            trust_delta = int(raw_trust_change)
        except:
            trust_delta = 0
        self.state["trust"] = self.state.get("trust", 0) + trust_delta
        
        # --- 8. 行动解析与校验 (Move / Stay) ---
        action = result.get("action", {})
        action_type = action.get("type", "stay")
        target = action.get("target", "")

        if action_type == "move":
            if target == "player":
                self.state["is_following"] = True
                self.state["current_location"] = "跟随玩家中"
            else:
                self.state["is_following"] = False
                # 双重保险：再次校验 LLM 返回的地点是否存在
                # 如果 target 是“后山”，validate_location 会返回默认地点或者保持原地（取决于你的策略）
                # 这里我们假设 validate_location 会返回 default_location 如果找不到
                validated_target = self.world_mgr.validate_location(target)
                self.state["current_location"] = validated_target

        elif action_type == "stay":
            self.state["is_following"] = False
        
        # --- 9. 记忆与存档 ---
        log_text = f"玩家: {user_input} | 我: {result['dialogue']}"
        # 必须把这里的 add_memory 也放进子线程，防止卡顿！
        threading.Thread(target=self.memory.add_memory, args=(log_text, "conversation")).start()

        self.history.append(f"Player: {user_input}")
        self.history.append(f"NPC: {result['dialogue']}")
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]

        # 给前端 UI 展示的全量记录（永久保存，不截断）
        self.state["full_chat_log"].append({"role": "user", "content": user_input})
        self.state["full_chat_log"].append({
            "role": "npc",
            "content": result["dialogue"],
            "thought": result["thought"],
            "action": action
        })
        
        self.save_state()

        return {
            "dialogue": result["dialogue"],
            "thought": result["thought"],
            "emotion": self.psychology.get_emotion_label(), 
            "pad": self.psychology.current_pad,
            "trust": self.state["trust"],
            "current_location": self.state["current_location"],
            "action": action
        }

    def save_state(self):
        save_dir = os.path.join(BASE_DIR, "data", "saves")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{self.char_id}_save.json")
        
        self.state['pad'] = self.psychology.current_pad
        self.state['emotion_label'] = self.psychology.get_emotion_label()
        self.state['last_interaction_time'] = self.psychology.last_update_time
        
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 存档失败: {e}") 