import sys
import os

# 确保能找到 core 文件夹
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import traceback
import colorama
from core.npc_agent import NPCAgent
from core.world import WorldManager  # ✨ 新增：引入世界管理器



# autoreset=True 会自动在每次 print 后重置颜色
colorama.init(autoreset=True)

# --- 🎨 颜色配置 ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GRAY = '\033[90m' # 新增灰色用于显示旁观信息

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "characters.json")
WORLD_PATH = os.path.join(BASE_DIR, "config", "world.json")

# ✨ 全局缓存，模拟服务器的内存状态
# 这样切换角色时，之前的状态（如位置、记忆）才会保留
active_npcs = {} 
world_mgr = WorldManager(WORLD_PATH) # ✨ 初始化世界

def load_character_list():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data 
    except Exception as e:
        print(f"{Colors.RED}❌ 无法读取角色列表: {e}{Colors.RESET}")
        return {}

def get_or_create_npc(char_id):
    """获取或初始化 NPC，并同步位置到世界管理器"""
    if char_id not in active_npcs:
        agent = NPCAgent(char_id)
        active_npcs[char_id] = agent
        # 注册初始位置
        loc = agent.state.get("current_location", "大雪山剑庐")
        world_mgr.update_npc_location(char_id, loc)
    return active_npcs[char_id]

def select_character(char_data):
    print(f"\n{Colors.HEADER}=== 🎭 NPC 角色选择大厅 ==={Colors.RESET}")
    char_ids = list(char_data.keys())
    
    # ✨ 预加载所有 NPC 到 active_npcs，确保他们都在世界里
    # 这样即使你还没和某人说话，他作为旁观者也是存在的
    for cid in char_ids:
        get_or_create_npc(cid)

    for index, char_id in enumerate(char_ids):
        info = char_data[char_id]
        # ✨ 显示当前 NPC 所在位置
        loc = active_npcs[char_id].state.get("current_location", "未知")
        print(f"{index + 1}. {Colors.BOLD}{info['name']}{Colors.RESET} ({info['role']}) - 📍 {loc}")
        
    print(f"{Colors.HEADER}============================={Colors.RESET}")
    
    while True:
        choice = input(f"{Colors.GREEN}请选择角色序号 (输入 q 退出): {Colors.RESET}")
        if choice.lower() in ['q', 'exit']:
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(char_ids):
                return char_ids[idx]
            else:
                print(f"{Colors.RED}⚠️ 无效序号，请重试。{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}⚠️ 请输入数字。{Colors.RESET}")

def chat_session(char_id):
    """开启与特定角色的聊天会话"""
    try:
        # 使用全局缓存获取 NPC
        npc = get_or_create_npc(char_id)
        name = npc.config.get('name', 'NPC')
        
        print(f"\n{Colors.CYAN}🚀 正在连接 {name} 的大脑...{Colors.RESET}")
        
        last_trust = npc.state.get('trust', 0)

        print(f"\n{Colors.HEADER}{'='*40}{Colors.RESET}")
        print(f"🔮 {Colors.BOLD}{name}{Colors.RESET} 已上线。")
        print(f"{Colors.GREEN}💡 提示: 输入 'back' 返回大厅，输入 'q' 彻底退出{Colors.RESET}")
        print(f"{Colors.HEADER}{'='*40}{Colors.RESET}\n")

        while True:
            # ✨ 每次循环前，更新当前 NPC 的位置（以防被外部因素修改）
            current_loc = npc.state.get("current_location", "大雪山剑庐")
            world_mgr.update_npc_location(char_id, current_loc)
            
            # 显示当前场景抬头
            print(f"{Colors.GRAY}📍 当前场景: [{current_loc}] | 👥 同场景: {world_mgr.get_npcs_in_location(current_loc)}{Colors.RESET}")

            try:
                user_text = input(f"{Colors.BLUE}👤 玩家: {Colors.RESET}")
            except EOFError:
                break 

            if user_text.lower() in ['q', 'exit']:
                print("程序退出。")
                sys.exit(0)
            
            if user_text.lower() in ['back', 'return', '切换']:
                print(f"\n{Colors.YELLOW}👋 正在断开与 {name} 的连接...{Colors.RESET}")
                return 

            if not user_text.strip():
                continue

            # --- ✨ 1. 广播玩家发言 (旁观者听觉) ---
            # 找出所有在同一个地方的其他 NPC
            bystanders = world_mgr.get_npcs_in_location(current_loc, exclude_id=char_id)
            for bid in bystanders:
                other = get_or_create_npc(bid) # 确保实例存在
                other.observe(speaker_name="玩家", target_name=name, content=user_text)
                print(f"{Colors.GRAY}   (👂 {other.config['name']} 听到了你说的话){Colors.RESET}")

            # --- 2. 核心交互 ---
            response = npc.chat(user_text)

            # --- ✨ 3. 广播 NPC 回复 (旁观者听觉) ---
            npc_reply = response.get('dialogue', '')
            for bid in bystanders:
                other = get_or_create_npc(bid)
                other.observe(speaker_name=name, target_name="玩家", content=npc_reply)

            # --- ✨ 4. 处理位置更新 ---
            # 如果 NPC 移动了，response['current_location'] 已经是新的了，但也需要更新 WorldManager
            new_loc = response.get('current_location')
            if new_loc != current_loc:
                world_mgr.update_npc_location(char_id, new_loc)

            # --- 数据展示 (UI更新) ---
            current_trust = response.get('trust', 0)
            trust_delta = current_trust - last_trust
            last_trust = current_trust 
            
            trust_str = f"{current_trust}"
            if trust_delta > 0: trust_str += f" ({Colors.GREEN}⬆️+{trust_delta}{Colors.RESET})"
            elif trust_delta < 0: trust_str += f" ({Colors.RED}⬇️{trust_delta}{Colors.RESET})"

            history_len = len(npc.history)
            max_hist = npc.MAX_HISTORY

            print("-" * 30)
            
            # 心理活动
            thought = response.get('thought', '...')
            print(f"{Colors.YELLOW}🧠 [心理]: {thought}{Colors.RESET}")
            
            # ✨ 行动反馈
            action = response.get('action', {})
            act_type = action.get('type', 'stay')
            act_target = action.get('target', '')
            if act_type == 'move':
                if act_target == 'player':
                    print(f"{Colors.GREEN}⚡ [行动]: 决定跟随你！(🏃 Follow){Colors.RESET}")
                else:
                    print(f"{Colors.GREEN}⚡ [行动]: 动身前往 -> {act_target}{Colors.RESET}")
            
            # 状态数值
            emotion = response.get('emotion', '未知')
            pad = response.get('pad', [0,0,0])
            pad_str = f"P:{pad[0]:.2f} A:{pad[1]:.2f} D:{pad[2]:.2f}"
            
            print(f"📉 [状态]: 情绪={emotion} ({pad_str})")
            # ✨ 增加位置显示
            print(f"📍 [位置]: {response.get('current_location')}")
            print(f"❤️ [好感]: {trust_str} | 📝 [Memory]: {history_len}/{max_hist}")
            
            # NPC 台词
            dialogue = response.get('dialogue', '...')
            print(f"{Colors.CYAN}🗣️  {name} : {dialogue}{Colors.RESET}\n")
            print("-" * 30)

            sys.stdout.flush()

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}用户强制中断。{Colors.RESET}")
        return
    except Exception:
        print(f"\n{Colors.RED}❌ 会话发生错误:{Colors.RESET}")
        traceback.print_exc()

def main():
    # 1. 加载所有角色数据
    char_data = load_character_list()
    if not char_data:
        return

    # 2. 外层循环
    while True:
        try:
            # 传入角色数据，此时内部会显示各个角色的当前位置
            selected_id = select_character(char_data)
            if selected_id is None:
                print("👋 再见！")
                break
            chat_session(selected_id)
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break

if __name__ == "__main__":
    main()