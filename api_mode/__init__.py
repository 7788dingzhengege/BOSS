# api_mode —— BOSS 直聘「token/API 模式」扩展包
#
# 设计原则（来自用户约束）：
#   1. 不修改 boss_auto_apply / boss_hr_helper / 旧 gui.py / config.py / spec 任何现有文件；
#   2. 通过 import 复用现有纯逻辑模块（flywheel.*、agent_filter、config）；
#   3. 沿用相同的「搜索→三层过滤→投递→标注→飞轮」流程逻辑；
#   4. 新入口在 GUI（gui_api.py）。
#
# 本包把「浏览器自动化」替换为「token + API 适配器」，并新增：
#   - 中央去重存储（原子 check-and-set，不重复投递）
#   - 本地 embedding RAG（离线、无外部依赖，替 n-gram）
#   - 并发抓取 + 限速投递（速度并行，遵守平台每日上限）
#   - API 适配器接口（你只需在 api_client.py 填 token + 接口）
#
# 合规提示：仅供本人学习/求职用途，请遵守平台协议与相关法律法规。

import os
import sys

# 把 boss_auto_apply 加入搜索路径，使其内部模块可被按包导入
# （flywheel 有 __init__.py，会作为顶层包导入；其相对导入 from . import store 据此解析）
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOSS_AA = os.path.join(os.path.dirname(_HERE), "boss_auto_apply")
# 把本包目录也加入搜索路径，使包内模块可用绝对导入
# （无论以脚本 python gui_api.py 运行，还是以 import api_mode.xxx 导入都能解析）
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _BOSS_AA not in sys.path:
    sys.path.insert(0, _BOSS_AA)

# 让 flywheel.store 的相对 data/ 指向 boss_auto_apply/data，与旧模式共享标注/规则
try:
    os.chdir(_BOSS_AA)
except Exception:
    pass
