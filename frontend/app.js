const { createApp } = Vue

const API_BASE = 'http://127.0.0.1:8000';

createApp({
    data() {
        return {
            // --- 数据源 ---
            worldConfig: {},    // 存放世界地图配置 { locations: {...}, default: ... }
            rawCharList: [],    // 存放从后端拿到的扁平化角色列表
            
            // --- 状态控制 ---
            loadingWorld: true, // 是否正在加载地图
            selectedCharId: null, 
            isConnected: false,
            userInput: '',
            messages: [],       // 聊天记录
            stats: null,        // 当前角色的实时状态 (PAD, Trust)
            loading: false,     // 发送消息loading
            pollingTimer: null,  // 心跳定时器
            // ：心理画像相关数据
            showProfile: false,
            padHistory: {},      // 记录角色PAD历史轨迹
            oceanChart: null,    // 雷达图实例
            padChart: null,       // 折线图实例
            showMemory: false,
            memoryStream: [],
        }
    },
    computed: {
        // --- 核心逻辑：将角色按地点分组 ---
        // 对应 HTML 中的 v-for="(locInfo, locName) in groupedWorld"
        groupedWorld() {
            // 如果地图还没加载好，返回空
            if (!this.worldConfig.locations) return {};

            // 1. 初始化所有地点容器 (根据 world.json)
            const groups = {};
            for (const [locName, desc] of Object.entries(this.worldConfig.locations)) {
                groups[locName] = {
                    desc: desc,
                    chars: [] // 准备一个空数组放人
                };
            }
            
            // 2. 遍历角色列表，把他们扔进对应的地点容器里
            this.rawCharList.forEach(char => {
                let targetLoc = char.location;
                
                // 处理特殊情况：如果 NPC 在“跟随中”或者在“未知区域”
                // 如果后端返回的 location 不在我们的地图配置里
                if (!groups[targetLoc]) {
                    // 动态创建一个“临时区域”或者“特殊状态区”
                    // 比如 targetLoc 是 "跟随玩家中"
                    if (!groups[targetLoc]) {
                        groups[targetLoc] = { 
                            desc: "特殊状态或未知区域", 
                            chars: [] 
                        };
                    }
                }
                
                // 标记是否跟随 (简单逻辑：如果地点名包含'跟随'或者后端有专门字段)
                // 这里我们假设后端返回的 location 字符串包含 "跟随"
                char.is_following = targetLoc.includes("跟随");

                // 入列
                groups[targetLoc].chars.push(char);
            });

            return groups;
        },

        // 获取当前选中角色的名字
        currentDisplayName() {
            if (!this.selectedCharId) return '';
            const char = this.rawCharList.find(c => c.id === this.selectedCharId);
            return char ? char.name : this.selectedCharId;
        },

        // 获取当前选中角色的位置
        currentLocation() {
             if (!this.selectedCharId) return '';
             const char = this.rawCharList.find(c => c.id === this.selectedCharId);
             return char ? char.location : '';
        }
    },
    
    // 页面加载完成后执行
    mounted() {
        this.initWorld();
    },

    methods: {
        // --- 初始化：同时拉取地图和人 ---
        async initWorld() {
            this.loadingWorld = true;
            try {
                // 并行请求，加快速度
                await Promise.all([this.fetchWorldConfig(), this.fetchCharacterList()]);
            } finally {
                this.loadingWorld = false;
            }
        },

        // 1. 获取世界地图配置
        async fetchWorldConfig() {
            try {
                const res = await fetch(`${API_BASE}/world`);
                this.worldConfig = await res.json();
            } catch (e) {
                console.error("无法获取地图配置", e);
                this.messages.push({role: 'system', content: '❌ 无法读取世界地图数据'});
            }
        },

        // 2. 获取角色列表 (扁平数据)
        async fetchCharacterList() {
            try {
                const res = await fetch(`${API_BASE}/characters`);
                const data = await res.json();
                this.rawCharList = data;
                
                // 如果还没有选中任何人，默认选中第一个
                if (!this.selectedCharId && this.rawCharList.length > 0) {
                    this.selectedCharId = this.rawCharList[0].id;
                }
            } catch (e) {
                console.error("无法获取角色列表", e);
            }
        },

        // 3. 选择角色
        selectChar(id) {
            if (this.isConnected) {
                alert("请先断开当前连接，再切换角色！");
                return;
            }
            this.selectedCharId = id;
            this.messages = []; // 切换角色时清空聊天屏
            this.stats = null;  // 清空状态面板
        },

        // 4. 建立连接 (✨ 已修改：支持拉取历史)
        startSession() {
            if (this.isConnected || !this.selectedCharId) return;
            this.isConnected = true;
            this.messages = [];
            this.messages.push({ role: 'system', content: `正在连接神经回路...` });
            
            setTimeout(async () => {
                this.fetchStatus(); // 立即获取一次状态
                this.fetchCharacterList(); // 再次刷新位置，防止滞后
                
                // ✨ 核心：等待历史记录拉取完成并渲染
                await this.fetchHistory();
                
                this.messages.push({ role: 'system', content: '✅ 信号同步成功。' });
                this.scrollToBottom();
                
                // 启动心跳轮询 (每3秒刷新一次状态)
                if (this.pollingTimer) clearInterval(this.pollingTimer);
                this.pollingTimer = setInterval(() => {
                    this.fetchStatus();
                }, 3000);
            }, 800);
        },

        // 5. 断开连接
        endSession() {
            if (!this.isConnected) return;
            this.isConnected = false;
            this.stats = null;
            if (this.pollingTimer) clearInterval(this.pollingTimer);
            this.messages.push({ role: 'system', content: '🔴 连接已断开。' });
        },

        // 6. 获取单人实时状态 (心跳)
        async fetchStatus() {
            if (!this.isConnected || !this.selectedCharId) return;
            try {
                const res = await fetch(`${API_BASE}/status/${this.selectedCharId}`);
                const data = await res.json();
                this.stats = data;
                this.recordPad(this.selectedCharId, data.pad);

                // 同步位置变化
                const charInList = this.rawCharList.find(c => c.id === this.selectedCharId);
                if (charInList && data.location && charInList.location !== data.location) {
                    charInList.location = data.location;
                }

            } catch (e) {
                console.error("Connection lost", e);
            }
        },

        // 7. 心理画像 
        // 记录 PAD 历史轨迹
        recordPad(charId, padValues) {
            if (!this.padHistory[charId]) {
                this.padHistory[charId] = { time: [], P: [], A: [], D: [] };
            }
            const hist = this.padHistory[charId];
            const now = new Date();
            const timeStr = `${now.getHours()}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
            
            hist.time.push(timeStr);
            hist.P.push(padValues[0]);
            hist.A.push(padValues[1]);
            hist.D.push(padValues[2]);
            
            // 最多保留最近的 20 个数据点，防止折线图太挤
            if (hist.time.length > 20) {
                hist.time.shift(); hist.P.shift(); hist.A.shift(); hist.D.shift();
            }
            
            // 如果面板正打开着，实时刷新折线图
            if (this.showProfile) this.renderPadChart();
        },

        // 打开画像面板
        openProfile() {
            this.showProfile = true;
            // 等待 DOM 渲染完成后初始化图表
            this.$nextTick(() => {
                this.renderOceanChart();
                this.renderPadChart();
            });
        },

        // 关闭画像面板
        closeProfile() {
            this.showProfile = false;
        },

        // 渲染 OCEAN 雷达图
        renderOceanChart() {
            if (!this.oceanChart) {
                this.oceanChart = echarts.init(document.getElementById('oceanChart'), 'dark');
            }
            const ocean = this.stats?.ocean || { O:0, C:0, E:0, A:0, N:0 };
            const option = {
                backgroundColor: 'transparent',
                tooltip: {},
                radar: {
                    indicator: [
                        { name: 'O (开放性)', max: 1 },
                        { name: 'C (尽责性)', max: 1 },
                        { name: 'E (外向性)', max: 1 },
                        { name: 'A (宜人性)', max: 1 },
                        { name: 'N (神经质)', max: 1 }
                    ],
                    radius: '65%',
                    splitArea: { areaStyle: { color: ['rgba(59, 130, 246, 0.1)', 'rgba(59, 130, 246, 0.05)'] } },
                    axisLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
                    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } }
                },
                series: [{
                    name: 'OCEAN',
                    type: 'radar',
                    data: [
                        {
                            value: [ocean.O, ocean.C, ocean.E, ocean.A, ocean.N],
                            name: '当前角色人格',
                            areaStyle: { color: 'rgba(16, 185, 129, 0.4)' },
                            lineStyle: { color: '#10b981' },
                            itemStyle: { color: '#10b981' }
                        }
                    ]
                }]
            };
            this.oceanChart.setOption(option);
        },

        // 渲染 PAD 折线图
        renderPadChart() {
            if (!this.padChart) {
                this.padChart = echarts.init(document.getElementById('padChart'), 'dark');
            }
            const hist = this.padHistory[this.selectedCharId] || { time: [], P: [], A: [], D: [] };
            const option = {
                backgroundColor: 'transparent',
                tooltip: { trigger: 'axis' },
                legend: { data: ['P (愉悦)', 'A (激活)', 'D (掌控)'], bottom: 0 },
                grid: { left: '10%', right: '5%', bottom: '15%', top: '10%' },
                xAxis: { type: 'category', data: hist.time, boundaryGap: false },
                yAxis: { type: 'value', min: -1, max: 1 },
                series: [
                    { name: 'P (愉悦)', type: 'line', data: hist.P, smooth: true, itemStyle: { color: '#10b981' } },
                    { name: 'A (激活)', type: 'line', data: hist.A, smooth: true, itemStyle: { color: '#ef4444' } },
                    { name: 'D (掌控)', type: 'line', data: hist.D, smooth: true, itemStyle: { color: '#3b82f6' } }
                ]
            };
            this.padChart.setOption(option);
        },

        // --- 8.记忆流面板方法 ---
        async openMemoryStream() {
            if (!this.selectedCharId) return;
            this.showMemory = true;
            this.memoryStream = []; // 先清空
            try {
                const res = await fetch(`${API_BASE}/memory/${this.selectedCharId}`);
                const result = await res.json();
                if (result.status === 'success') {
                    this.memoryStream = result.data;
                }
            } catch (e) {
                console.error("获取记忆流失败", e);
            }
        },

        closeMemory() {
            this.showMemory = false;
        },

        formatMemType(type) {
            const map = {
                'background': '🌱 初始种子',
                'conversation': '💬 对话记忆',
                'observation': '👀 旁听观察',
                'reflection': '✨ 高维反思'
            };
            return map[type] || type;
        },

        // 9.获取所有历史记录
        async fetchHistory() {
            if (!this.isConnected || !this.selectedCharId) return;
            try {
                const res = await fetch(`${API_BASE}/history/${this.selectedCharId}`);
                const result = await res.json();
                
                if (result.status === 'success' && result.data && result.data.length > 0) {
                    // 把拿到的历史记录推入消息列表
                    this.messages.push(...result.data);
                    // 插入分割线，提示用户以上是历史
                    this.messages.push({ role: 'system', content: '--- 📜 以上为历史记录 ---' });
                    this.scrollToBottom();
                }
            } catch (e) {
                console.error("无法获取历史记录", e);
            }
        },

        // 10. 发送消息
        async sendMessage() {
            if (!this.userInput.trim() || !this.isConnected || this.loading) return;
            const text = this.userInput;
            this.userInput = '';
            
            this.messages.push({ role: 'user', content: text });
            this.scrollToBottom();
            this.loading = true;

            // 发送期间暂停心跳，避免请求冲突
            if (this.pollingTimer) {
                clearInterval(this.pollingTimer);
                this.pollingTimer = null;
            }

            try {
                const res = await fetch(`${API_BASE}/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ character_id: this.selectedCharId, user_input: text })
                });
                const result = await res.json();
                
                if (result.status === 'success') {
                    const data = result.data;
                    
                    // 推送 NPC 回复
                    this.messages.push({
                        role: 'npc',
                        content: data.dialogue,
                        thought: data.thought,
                        action: data.action //  把 action 传给 HTML 显示
                    });
                    
                    // 更新面板
                    if (this.stats) {
                        this.stats.emotion = data.emotion;
                        this.stats.pad = data.pad;
                        this.stats.trust = data.trust;
                        this.recordPad(this.selectedCharId, data.pad);
                    }

                    // 如果发生了移动，强制刷新整个列表
                    if (data.action && data.action.type === 'move') {
                        setTimeout(() => this.fetchCharacterList(), 500);
                    }
                }
            } catch (e) {
                console.error(e);
                this.messages.push({ role: 'system', content: '❌ 信号中断' });
            } finally {
                this.loading = false;
                this.scrollToBottom();

                // 恢复心跳
                if (this.isConnected && !this.pollingTimer) {
                    this.fetchStatus(); 
                    this.pollingTimer = setInterval(this.fetchStatus, 3000);
                }
            }
        },

        // --- 工具函数 ---
        formatNum(val) { return (val > 0 ? '+' : '') + val.toFixed(2); },
        getBarStyle(val) {
            const percent = (val + 1) / 2 * 100;
            let color = '#10b981';
            if (val < -0.2) color = '#ef4444';
            else if (val > 0.6) color = '#f59e0b';
            return { width: Math.max(0, Math.min(100, percent)) + '%', backgroundColor: color };
        },
        scrollToBottom() {
            setTimeout(() => {
                const el = document.getElementById('chatContainer');
                if(el) el.scrollTop = el.scrollHeight;
            }, 100);
        }
    }
}).mount('#app');