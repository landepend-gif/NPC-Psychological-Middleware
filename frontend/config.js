const { createApp } = Vue;
const API_BASE = 'http://127.0.0.1:8000'; 

createApp({
    data() {
        return {
            loading: false,
            allCharacters: {},
            allSeeds: {},
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
    },
    methods: {
        // 1. 从后端拉取所有 JSON 配置
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