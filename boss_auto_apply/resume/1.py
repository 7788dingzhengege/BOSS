# Embedding 预热一键运行
# 自动定位到 boss_auto_apply 目录, 解决相对路径找不到 data/labels.json 的问题
# 用法: 直接 python 1.py 即可 (从任何目录运行都有效)

import os
import sys

# ====== 1. 自动切换到 boss_auto_apply 目录 ======
# store.py 用相对路径 data/labels.json, 必须在 boss_auto_apply 下运行
THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # .../resume
PROJECT_DIR = os.path.dirname(THIS_DIR)                        # .../boss_auto_apply
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

print(f"[1.py] 工作目录: {os.getcwd()}")
print(f"[1.py] 项目目录: {PROJECT_DIR}")

# ====== 2. 检查标注数据是否存在 ======
labels_path = os.path.join(PROJECT_DIR, "data", "labels.json")
if not os.path.exists(labels_path):
    print(f"[1.py] 错误: 找不到 {labels_path}")
    print("[1.py] 请确认已运行过投递流程并产生标注数据")
    sys.exit(1)

import json
try:
    with open(labels_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    jobs = data.get("jobs", [])
    labeled = [j for j in jobs if j.get("label") != "pending"]
    print(f"[1.py] 标注数据: 共 {len(jobs)} 条, 已标注 {len(labeled)} 条")
    if not labeled:
        print("[1.py] 警告: 没有已标注的职位, warmup 无意义")
        sys.exit(0)
except Exception as e:
    print(f"[1.py] 读取 labels.json 失败: {e}")
    sys.exit(1)

# ====== 3. 执行预热 ======
print("\n[1.py] 开始预热 embedding ...\n")
try:
    from flywheel.embedder import warmup
    count = warmup()
    print(f"\n[1.py] 预热完成, 共缓存 {count} 个职位 embedding")
    print("[1.py] 下次投递时 embedding 层将自动生效")
except Exception as e:
    print(f"\n[1.py] 预热失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
