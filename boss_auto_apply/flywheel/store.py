# 数据存储层: labels.json / rules.json / rule_suggestions.json / metrics_history.json 读写

import os
import json
from datetime import datetime

# ====== 数据文件路径(相对项目根目录) ======
DATA_DIR = "data"
LABELS_FILE = os.path.join(DATA_DIR, "labels.json")
RULES_FILE = os.path.join(DATA_DIR, "rules.json")
SUGGESTIONS_FILE = os.path.join(DATA_DIR, "rule_suggestions.json")
METRICS_HISTORY_FILE = os.path.join(DATA_DIR, "metrics_history.json")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _atomic_write(path, data):
    """原子写入: 先写临时文件再覆盖, 避免写入中断损坏"""
    _ensure_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ========== labels.json ==========

def load_labels():
    """读取标注库, 返回 {"version":1, "jobs":[...]}"""
    if not os.path.exists(LABELS_FILE):
        return {"version": 1, "jobs": []}
    try:
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "jobs": []}


def save_labels(data):
    _atomic_write(LABELS_FILE, data)


def add_pending(job_id, job_name, company, salary, status, hit_keyword="", run_id="", group=""):
    """
    投递/过滤时写入一条 pending 记录
    :param status: "applied"=投了 | "excluded"=被规则拦
    :param hit_keyword: excluded 时填命中的排除词
    :param group: 岗位分组(当前搜索关键词)，用于多目标隔离
    """
    data = load_labels()
    # 去重: 同 job_id 若已存在则不重复写(避免同 run 多次记录)
    for j in data["jobs"]:
        if j.get("job_id") == job_id:
            return  # 已存在, 跳过
    now = datetime.now().isoformat(timespec="seconds")
    data["jobs"].append({
        "job_id": job_id,
        "job_name": job_name,
        "company": company,
        "salary": salary or "",
        "status": status,           # applied | excluded
        "label": "pending",         # pending | accepted | rejected
        "hit_keyword": hit_keyword,
        "note": "",
        "run_id": run_id,
        "group": (group or "").strip(),   # 岗位分组(空=未分组/历史数据)
        "applied_at": now if status == "applied" else "",
        "labeled_at": "",
    })
    save_labels(data)


def update_label(job_id, label, note=""):
    """人工标注: 更新 label 和 note, 写入 labeled_at"""
    data = load_labels()
    now = datetime.now().isoformat(timespec="seconds")
    for j in data["jobs"]:
        if j.get("job_id") == job_id:
            j["label"] = label      # accepted | rejected
            j["note"] = note or j.get("note", "")
            j["labeled_at"] = now
            break
    save_labels(data)


def batch_update_labels(job_ids, label):
    """批量标注(用于"全部投了的标为👍")"""
    data = load_labels()
    now = datetime.now().isoformat(timespec="seconds")
    id_set = set(job_ids)
    for j in data["jobs"]:
        if j.get("job_id") in id_set and j.get("label") == "pending":
            j["label"] = label
            j["labeled_at"] = now
    save_labels(data)


def get_pending(group=None):
    """获取待标注(label=pending)；group=None=全部, 指定则只取该组"""
    data = load_labels()
    if group is None:
        return [j for j in data["jobs"] if j.get("label") == "pending"]
    return [j for j in data["jobs"]
            if j.get("label") == "pending" and (j.get("group") or "") == group]


def get_labeled(group=None):
    """获取已标注(label!=pending)；group=None=全部, 指定则只取该组"""
    data = load_labels()
    if group is None:
        return [j for j in data["jobs"] if j.get("label") != "pending"]
    return [j for j in data["jobs"]
            if j.get("label") != "pending" and (j.get("group") or "") == group]


def get_all_groups():
    """返回所有出现过的岗位分组名(含空组=None), 用于 UI 下拉"""
    data = load_labels()
    groups = {}
    for j in data["jobs"]:
        g = j.get("group") or ""
        groups[g] = groups.get(g, 0) + 1
    return groups


def get_groups(group=None):
    """
    四象限分组:
      G1 = applied + accepted   (投对)
      G2 = applied + rejected   (错投)
      G3 = excluded + accepted  (漏投)
      G4 = excluded + rejected  (拦对)
    :param group: 岗位分组名；None=全部
    """
    labeled = get_labeled(group)
    G1, G2, G3, G4 = [], [], [], []
    for j in labeled:
        s = j.get("status")
        l = j.get("label")
        if s == "applied" and l == "accepted":
            G1.append(j)
        elif s == "applied" and l == "rejected":
            G2.append(j)
        elif s == "excluded" and l == "accepted":
            G3.append(j)
        elif s == "excluded" and l == "rejected":
            G4.append(j)
    return {"G1": G1, "G2": G2, "G3": G3, "G4": G4}


# ========== rules.json ==========

def load_rules():
    """读取飞轮规则库"""
    if not os.path.exists(RULES_FILE):
        return {
            "version": 1,
            "updated_at": "",
            "exclude_keywords": [],
            "include_keywords": [],
            "changelog": [],
        }
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "updated_at": "", "exclude_keywords": [],
                "include_keywords": [], "changelog": []}


def save_rules(data):
    _atomic_write(RULES_FILE, data)


def add_exclude_keywords(keywords, source="miner"):
    """添加排除词, 自动 version+1 写 changelog"""
    rules = load_rules()
    added = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in rules["exclude_keywords"]:
            rules["exclude_keywords"].append(kw)
            added.append(kw)
    if added:
        rules["version"] = rules.get("version", 1) + 1
        rules["updated_at"] = datetime.now().isoformat(timespec="seconds")
        rules.setdefault("changelog", []).append({
            "version": rules["version"],
            "action": "add_exclude",
            "keywords": added,
            "source": source,
            "date": datetime.now().strftime("%Y-%m-%d"),
        })
        save_rules(rules)
    return added


def add_include_keywords(keywords, source="miner"):
    """添加白名单词"""
    rules = load_rules()
    added = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in rules["include_keywords"]:
            rules["include_keywords"].append(kw)
            added.append(kw)
    if added:
        rules["version"] = rules.get("version", 1) + 1
        rules["updated_at"] = datetime.now().isoformat(timespec="seconds")
        rules.setdefault("changelog", []).append({
            "version": rules["version"],
            "action": "add_include",
            "keywords": added,
            "source": source,
            "date": datetime.now().strftime("%Y-%m-%d"),
        })
        save_rules(rules)
    return added


def remove_exclude_keyword(keyword, source="overkill_fix"):
    """移除误杀的排除词"""
    rules = load_rules()
    if keyword in rules["exclude_keywords"]:
        rules["exclude_keywords"].remove(keyword)
        rules["version"] = rules.get("version", 1) + 1
        rules["updated_at"] = datetime.now().isoformat(timespec="seconds")
        rules.setdefault("changelog", []).append({
            "version": rules["version"],
            "action": "remove_exclude",
            "keyword": keyword,
            "source": source,
            "date": datetime.now().strftime("%Y-%m-%d"),
        })
        save_rules(rules)
        return True
    return False


def get_effective_exclude():
    """获取飞轮维护的排除词列表(供 applier 合并使用)"""
    return load_rules().get("exclude_keywords", [])


def get_effective_include():
    """获取飞轮维护的白名单列表(全局层)"""
    return load_rules().get("include_keywords", [])


# ========== rules.json 分组规则（多岗位隔离）==========

def get_group_rules():
    """
    读取按岗位分组的规则: {"group名": {"include_keywords": [], "exclude_keywords": []}}
    向后兼容: 无 groups 字段时返回 {}
    """
    rules = load_rules()
    groups = rules.get("groups", {})
    return {g: {"include_keywords": list(v.get("include_keywords", [])),
                "exclude_keywords": list(v.get("exclude_keywords", []))}
            for g, v in groups.items() if isinstance(v, dict)}


def save_group_rules(group, include_keywords=None, exclude_keywords=None):
    """写入某个岗位分组的规则(白名单/排除词)，不影响全局层"""
    group = (group or "").strip()
    if not group:
        return False
    rules = load_rules()
    rules.setdefault("groups", {})
    g = rules["groups"].setdefault(group, {"include_keywords": [], "exclude_keywords": []})
    changed = False
    if include_keywords is not None:
        inc = [k.strip() for k in include_keywords if k and k.strip() not in g["include_keywords"]]
        if inc:
            g["include_keywords"] += inc
            changed = True
    if exclude_keywords is not None:
        exc = [k.strip() for k in exclude_keywords if k and k.strip() not in g["exclude_keywords"]]
        if exc:
            g["exclude_keywords"] += exc
            changed = True
    if changed:
        rules["version"] = rules.get("version", 1) + 1
        rules["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_rules(rules)
    return changed


def get_effective_include_for_group(group):
    """某岗位组的生效白名单 = config白名单 + 全局白名单(rules.json) + 该组白名单(去重)"""
    group = (group or "").strip()
    base = list(get_effective_include())
    # 兜底: 合并 config.py 的 INCLUDE_KEYWORDS（rules.json 全局白名单可能为空,
    # config 是用户手动维护的基础白名单, 必须始终生效）
    try:
        from config import INCLUDE_KEYWORDS as _cfg_inc
        for kw in _cfg_inc:
            kw = (kw or "").strip()
            if kw and kw.lower() not in {b.lower() for b in base}:
                base.append(kw)
    except Exception:
        pass  # config 不可用时退化为仅 rules.json
    if not group:
        return base
    gr = get_group_rules().get(group, {})
    merged, seen = [], set()
    for kw in base + list(gr.get("include_keywords", [])):
        kw = (kw or "").strip()
        if kw and kw.lower() not in seen:
            merged.append(kw)
            seen.add(kw.lower())
    return merged


# ========== rule_suggestions.json ==========

def load_suggestions():
    if not os.path.exists(SUGGESTIONS_FILE):
        return {"mined_at": "", "total_labels": 0, "groups": {},
                "suggested_exclude": [], "suggested_include": [],
                "overkill_alert": []}
    try:
        with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"mined_at": "", "total_labels": 0, "groups": {},
                "suggested_exclude": [], "suggested_include": [],
                "overkill_alert": []}


def save_suggestions(data):
    _atomic_write(SUGGESTIONS_FILE, data)


# ========== metrics_history.json ==========

def load_metrics_history():
    if not os.path.exists(METRICS_HISTORY_FILE):
        return {"rounds": []}
    try:
        with open(METRICS_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"rounds": []}


def save_metrics_history(data):
    _atomic_write(METRICS_HISTORY_FILE, data)


def append_metrics(round_metrics):
    """追加一轮指标记录"""
    data = load_metrics_history()
    # 同 run_id 覆盖
    rid = round_metrics.get("run_id")
    data["rounds"] = [r for r in data["rounds"] if r.get("run_id") != rid]
    data["rounds"].append(round_metrics)
    save_metrics_history(data)
