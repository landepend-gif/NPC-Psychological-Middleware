import os
import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification, 
    Trainer, 
    TrainingArguments
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(BASE_DIR, "models", "roberta-jd")
output_model_path = os.path.join(BASE_DIR, "models", "roberta-jd-finetuned")

print("⏳ 正在加载基础模型...")
tokenizer = AutoTokenizer.from_pretrained(model_path)
# 明确告诉模型这是一个二分类任务 (0和1)
model = AutoModelForSequenceClassification.from_pretrained(model_path, num_labels=2)

print("📖 正在加载游戏数据集...")
dataset = load_dataset('json', data_files='game_data.jsonl')

# 将数据集按 8:2 划分为训练集和验证集
dataset = dataset['train'].train_test_split(test_size=0.2)

# 4. 数据预处理函数 (Tokenization)
def tokenize_function(examples):
    # 将文本转化为模型能看懂的数字矩阵，统一填充或截断到128长度
    return tokenizer(
        examples["text"], 
        padding="max_length", 
        truncation=True, 
        max_length=128
    )

print("⚙️ 正在处理数据...")
tokenized_datasets = dataset.map(tokenize_function, batched=True)

# 5. 设置训练参数
training_args = TrainingArguments(
    output_dir="./training_logs",   # 训练过程中的临时日志目录
    eval_strategy="epoch",    # 每个 epoch 结束时评估一次
    learning_rate=2e-5,             # 学习率，微调通常设置得比较小
    per_device_train_batch_size=8,  # 批次大小，如果显存大可以调为16或32
    per_device_eval_batch_size=8,
    num_train_epochs=5,             # 训练轮数
    weight_decay=0.01,
    save_strategy="epoch",
    load_best_model_at_end=True,    # 训练结束后加载效果最好的那一轮模型
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets["train"],
    eval_dataset=tokenized_datasets["test"],
)

print("🚀 开始微调模型...")
trainer.train()

print(f"✅ 训练完成，正在保存模型至: {output_model_path}")
trainer.save_model(output_model_path)
tokenizer.save_pretrained(output_model_path)
print("🎉 微调圆满结束！")