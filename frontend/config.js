const { createApp } = Vue;
const API_BASE = 'http://127.0.0.1:8000'; 

createApp({
    data() {
        return {
            loading: false,
            allCharacters: {},
            allSeeds: {},
            worldConfig: {}, //存放世界地图配置
            isEditing: false, // 标记当前是修改还是新建
            
            // 表单绑定的数据
            currentForm: {
                char_id: '',
                name: '',
                role: '',
                ocean: { O: 0.5, C: 0.5, E: 0.5, A: 0.5, N: 0.5 }
            },
            seedsText: '', // 文本域里用换行符分割的字符串
            
            oceanLabels: {
                'O': 'O - 开放性 (Openness)',
                'C': 'C - 尽责性 (Conscientiousness)',
                'E': 'E - 外向性 (Extraversion)',
                'A': 'A - 宜人性 (Agreeableness)',
                'N': 'N - 神经质 (Neuroticism)'
            }
        }
    },
    mounted() {
        this.loadConfigs();
        this.loadWorldConfig(); // 页面加载时请求世界地图
    },
    methods: {
        // 1. 从后端拉取所有 JSON 配置 (角色信息)
        async loadConfigs() {
            try {
                const res = await fetch(`${API_BASE}/config/all`);
                const result = await res.json();
                if (result.status === 'success') {
                    this.allCharacters = result.data.characters;
                    this.allSeeds = result.data.seeds;
                }
            } catch (e) {
                alert("拉取配置失败，请检查后端是否运行！");
            }
        },
        
        // 拉取地图坐标配置
        async loadWorldConfig() {
            try {
                const res = await fetch(`${API_BASE}/world`);
                this.worldConfig = await res.json();
                
                // 确保 DOM 渲染完毕后再初始化 ECharts
                this.$nextTick(() => {
                    this.initWorldMap();
                });
            } catch (e) {
                console.error("加载世界配置失败", e);
            }
        },

        // 初始化 ECharts 地图
        initWorldMap() {
            const chartDom = document.getElementById('world-map');
            if (!chartDom) return; 
            
            // 使用 echarts.getInstanceByDom 防止重复初始化报错
            let myChart = echarts.getInstanceByDom(chartDom);
            if (!myChart) {
                myChart = echarts.init(chartDom);
            }
            
            // 处理后端传来的地点数据
            const dataPoints = Object.entries(this.worldConfig.locations || {}).map(([name, info]) => {
                let desc = typeof info === 'string' ? info : info.desc;
                let x = typeof info === 'object' && info.x !== undefined ? info.x : Math.floor(Math.random() * 400 + 50);
                let y = typeof info === 'object' && info.y !== undefined ? info.y : Math.floor(Math.random() * 400 + 50);
                return { name, value: [x, y], desc };
            });

            const option = {
                tooltip: {
                    formatter: function (params) {
                        return `<b style="color:#3b82f6;">${params.data.name}</b><br/>${params.data.desc}`;
                    }
                },
                xAxis: { min: 0, max: 500, show: false }, 
                yAxis: { min: 0, max: 500, show: false },
                series: [{
                    type: 'scatter',
                    data: dataPoints,
                    symbolSize: 24,
                    itemStyle: {
                        color: '#3b82f6',
                        shadowBlur: 10,
                        shadowColor: 'rgba(59, 130, 246, 0.5)'
                    },
                    label: { 
                        show: true, 
                        formatter: '{b}', 
                        color: '#fff', 
                        position: 'bottom',
                        distance: 10,
                        fontSize: 13
                    }
                }]
            };

            myChart.setOption(option);

            // 监听点击地图空白处事件
            myChart.getZr().off('click'); 
            myChart.getZr().on('click', (params) => {
                // 如果点击在已经存在的圆点上，则不触发新建
                if (params.target) return;

                // 转换点击的像素坐标为数据坐标
                const pointInPixel = [params.offsetX, params.offsetY];
                const pointInGrid = myChart.convertFromPixel({ seriesIndex: 0 }, pointInPixel);

                if (pointInGrid) {
                    const locName = prompt("📍 [创建新地点]\n请输入新地点名称 (如: 藏经阁):");
                    if (!locName) return;
                    
                    const locDesc = prompt(`请描述一下 [${locName}] 的环境:`);
                    if (!locDesc) return;

                    // 发送创建请求
                    this.createNewLocation(locName, locDesc, Math.round(pointInGrid[0]), Math.round(pointInGrid[1]));
                }
            });
        },

        // 提交新地点到后端
        async createNewLocation(name, desc, x, y) {
            try {
                const res = await fetch(`${API_BASE}/config/location`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, desc, x, y })
                });
                const result = await res.json();
                
                if (result.status === 'success') {
                    // 创建成功后重新拉取一次地图刷新画面
                    this.loadWorldConfig();
                } else {
                    alert("创建失败: " + result.message);
                }
            } catch (e) {
                alert("网络错误，无法创建地点！请检查 server.py 接口是否配置。");
            }
        },
        // ==========================================


        // 2. 点击左侧列表，把数据填入右侧表单
        editCharacter(id) {
            this.isEditing = true;
            const char = this.allCharacters[id];
            this.currentForm = {
                char_id: id,
                name: char.name,
                role: char.role,
                ocean: { ...char.ocean } // 浅拷贝，防止直接修改原始数据
            };
            
            // 把数组形式的种子记忆，用换行符拼成字符串塞进 textarea
            const seedsArr = this.allSeeds[id] || [];
            this.seedsText = seedsArr.join('\n');
        },

        // 3. 点击新建按钮，清空表单
        createNew() {
            this.isEditing = false;
            this.currentForm = {
                char_id: '',
                name: '',
                role: '',
                ocean: { O: 0.5, C: 0.5, E: 0.5, A: 0.5, N: 0.5 }
            };
            this.seedsText = '';
        },

        // 4. 保存提交到后端
        async saveCharacter() {
            if (!this.currentForm.char_id || !this.currentForm.name) {
                alert("角色 ID 和姓名不能为空！");
                return;
            }

            // 把 textarea 里的多行文本，按换行符劈开变成数组，并去掉空行
            const seedsArray = this.seedsText.split('\n').map(s => s.trim()).filter(s => s !== '');

            const payload = {
                char_id: this.currentForm.char_id,
                name: this.currentForm.name,
                role: this.currentForm.role,
                ocean: this.currentForm.ocean,
                seeds: seedsArray
            };

            try {
                const res = await fetch(`${API_BASE}/config/character`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                if (result.status === 'success') {
                    alert(result.message);
                    this.loadConfigs(); // 重新拉取最新数据刷新列表
                } else {
                    alert("保存失败: " + result.message);
                }
            } catch (e) {
                alert("请求失败，请检查后端！");
            }
        }
    }
}).mount('#config-app');