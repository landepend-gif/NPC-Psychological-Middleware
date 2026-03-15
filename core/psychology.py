import math
import time 

class PsychologyEngine:
    def __init__(self, ocean_data=None, initial_pad=None, last_update_time=None):
        # 1.初始化PAD（优先使用传入的，否则初始化为0）
        if initial_pad and len(initial_pad) == 3:
            self.current_pad = initial_pad
        else:
            self.current_pad = [0.0, 0.0, 0.0]

        # 2. 初始化 OCEAN (优先使用传入的，否则给个默认中间值)
        self.ocean = {
            "O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5
        }
        if ocean_data:
            self.set_ocean(ocean_data)

        # 3. 初始化时间戳
        # 如果有存档时间就用存档的，否则用当前时间
        self.last_update_time = last_update_time if last_update_time else time.time()

    def set_ocean(self, ocean_data):
        """设置性格基准值"""
        if not ocean_data:
            return
        # 确保数据完整，没有的填默认值
        for key in ["O", "C", "E", "A", "N"]:
            # 确保读取到对应键值，若配置里漏了某一项，保持默认 0.5
            if key in ocean_data:
                self.ocean[key] = ocean_data[key]

    def set_pad(self, pad_data):
        """设置当前情绪状态"""
        if pad_data and len(pad_data) == 3:
            self.current_pad = pad_data

    def process_time_decay(self):
        """根据时间流逝计算自然衰减"""
        current_time = time.time()
        elapsed_seconds = current_time - self.last_update_time
        
        # 防止时间倒流（比如系统时间被改）
        if elapsed_seconds < 0: elapsed_seconds = 0
        
        # --- 衰减算法 ---
        # 设定“情绪半衰期”为 30 分钟 (1800秒)
        # 公式：新值 = 旧值 * (0.5 ^ (经过时间 / 半衰期))
        # 比如：过了 1800秒，情绪值 * 0.5；过了 3600秒，情绪值 * 0.25
        half_life = 1800 
        decay_factor = math.pow(0.5, elapsed_seconds / half_life)
        
        # 应用衰减
        old_pad = list(self.current_pad)
        self.current_pad = [x * decay_factor for x in self.current_pad]
        
        # 更新时间戳
        self.last_update_time = current_time
        
        return old_pad, self.current_pad, elapsed_seconds

    def update_pad(self, stimulus):
        """
        核心函数：根据外部刺激和性格，更新 PAD 值
        """
        # 1. 先结算这期间的时间流逝（玩家可能打字打了 1 分钟，情绪也要微弱衰减）
        self.process_time_decay()

        # 2. 获取刺激值
        d_p = stimulus.get("P", 0)
        d_a = stimulus.get("A", 0)
        d_d = stimulus.get("D", 0)

        # 3. 性格修正 
        # 如果是高神经质(N)，负面情绪影响更大
        if self.ocean.get("N", 0.5) > 0.6:
            if d_p < 0: d_p *= 1.2
            
        # 如果是高外向(E)，更容易激动
        if self.ocean.get("E", 0.5) > 0.6:
            if d_a > 0: d_a *= 1.1

        # 4. 应用更新
        self.current_pad[0] += d_p
        self.current_pad[1] += d_a
        self.current_pad[2] += d_d

        # 5. 限制范围在 -1 到 1 之间
        self.current_pad = [max(-1.0, min(1.0, x)) for x in self.current_pad]

    def get_emotion_label(self):
        """
        根据 PAD 返回情绪标签
        """
        p, a, d = self.current_pad
        
        if p > 0.3 and a > 0.3: return "兴奋"
        if p > 0.3 and a < -0.2: return "惬意"
        if p < -0.3 and a > 0.3: return "愤怒"
        if p < -0.3 and a < -0.2: return "悲伤"
        if abs(p) < 0.2 and abs(a) < 0.2: return "平静"
        
        return "情绪波动"