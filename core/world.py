import json
import os

class WorldManager:
    def __init__(self, config_path):
        self.config_data = self._load_config(config_path)
        
        # 1. 获取默认地点（防止代码里写死）
        # 如果 json 里没写 default_location，就随便取 locations 里的第一个 key 作为保底
        self.locations_map = self.config_data.get("locations", {})
        self.default_location = self.config_data.get(
            "default_location", 
            list(self.locations_map.keys())[0] if self.locations_map else "未知荒野"
        )
        
        # 内存位置表
        self.npc_locations = {} 

    def _load_config(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加载世界配置失败: {e}")
            return {}

    def get_location_description(self, loc_name):
        return self.locations_map.get(loc_name, "一片混沌之地")

    # --- 地点校验逻辑 ---
    def validate_location(self, loc_name):
        """
        检查地点是否合法。
        - 如果合法：返回原地点。
        - 如果不合法（如幻觉、旧存档残留）：返回 default_location。
        """
        if loc_name in self.locations_map:
            return loc_name
        
        # 特殊处理：如果是“跟随状态”，暂时视为合法（或者由业务逻辑单独处理）
        if loc_name and "跟随" in loc_name:
            return loc_name
            
        print(f"⚠️ [World] 检测到无效地点 '{loc_name}'，已重置为 '{self.default_location}'")
        return self.default_location

    def update_npc_location(self, npc_id, location):
        self.npc_locations[npc_id] = location

    def get_npcs_in_location(self, location, exclude_id=None):
        bystanders = []
        for nid, loc in self.npc_locations.items():
            if loc == location and nid != exclude_id:
                bystanders.append(nid)
        return bystanders
        
    def get_valid_locations_list(self):
        return list(self.locations_map.keys())