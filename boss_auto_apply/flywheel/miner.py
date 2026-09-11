# 挖掘引擎: 从标注数据挖掘新规则

import re
from collections import Counter
from datetime import datetime
from . import store


def _extract_ngrams(text, n_list=(2, 3, 4)):
    """提取中英文 n-gram"""
    if not text:
        return []
    text = text.strip()
    grams = []
    for n in n_list:
        for i in range(len(text) - n + 1):
            gram = text[i:i+n]
            # 过滤纯标点/纯数字/含特殊字符的
            if re.match(r"^[\w\u4e00-\u9fa5]+$", gram) and not gram.isdigit():
                grams.append(gram)
    return grams


def _compute_score(target_count, other_count):
    """区分度: target 越多 other 越少, score 越高"""
    total = target_count + other_count
    if total == 0:
        return 0
    return round(target_count / (total + 1), 3)


def mine_exclude_suggestions():
    """
    从 G2(错投) 挖掘新排除词
    候选: 在 G2 频次高, 在 G1(投对) 频次低
    """
    groups = store.get_groups()
    G1_names = [j.get("job_name", "") for j in groups["G1"]]
    G2_names = [j.get("job_name", "") for j in groups["G2"]]

    # 统计 n-gram 频次
    G1_counter = Counter()
    G2_counter = Counter()
    for name in G1_names:
        G1_counter.update(_extract_ngrams(name))
    for name in G2_names:
        G2_counter.update(_extract_ngrams(name))

    # 现有排除词, 避免重复建议
    existing = set(kw.lower() for kw in store.get_effective_exclude())

    suggestions = []
    for gram, g2_count in G2_counter.items():
        if gram.lower() in existing:
            continue
        g1_count = G1_counter.get(gram, 0)
        # 阈值: G2 出现 >=2 次, 区分度 > 0.6
        if g2_count >= 2 and g1_count == 0:
            score = _compute_score(g2_count, g1_count)
            suggestions.append({
                "keyword": gram,
                "rejected": g2_count,
                "accepted": g1_count,
                "score": score,
                "status": "pending",
            })

    # 按错投次数排序
    suggestions.sort(key=lambda x: (-x["rejected"], -x["score"]))
    return suggestions


def mine_include_suggestions():
    """
    从 G3(漏投) 挖掘新白名单
    候选: 在 G3 频次高, 在 G4(拦对) 频次低
    """
    groups = store.get_groups()
    G3_names = [j.get("job_name", "") for j in groups["G3"]]
    G4_names = [j.get("job_name", "") for j in groups["G4"]]

    G3_counter = Counter()
    G4_counter = Counter()
    for name in G3_names:
        G3_counter.update(_extract_ngrams(name))
    for name in G4_names:
        G4_counter.update(_extract_ngrams(name))

    existing_include = set(kw.lower() for kw in store.get_effective_include())

    suggestions = []
    for gram, g3_count in G3_counter.items():
        if gram.lower() in existing_include:
            continue
        g4_count = G4_counter.get(gram, 0)
        if g3_count >= 2 and g4_count == 0:
            score = _compute_score(g3_count, g4_count)
            suggestions.append({
                "keyword": gram,
                "missed": g3_count,
                "correctly_excluded": g4_count,
                "score": score,
                "status": "pending",
            })

    suggestions.sort(key=lambda x: (-x["missed"], -x["score"]))
    return suggestions


def mine_overkill_alerts():
    """
    误杀告警: 从 G3(漏投) 找哪些排除词排得太宽
    """
    groups = store.get_groups()
    G3 = groups["G3"]
    if not G3:
        return []

    # 统计每个排除词被多少 G3(漏投) 命中
    overkill_counter = Counter()
    overkill_samples = {}
    for j in G3:
        hit = j.get("hit_keyword", "")
        if hit:
            overkill_counter[hit] += 1
            overkill_samples.setdefault(hit, []).append(j.get("job_name", ""))

    alerts = []
    for kw, count in overkill_counter.most_common():
        if count >= 2:  # 至少误杀2次才告警
            alerts.append({
                "keyword": kw,
                "overkill_count": count,
                "overkill_samples": overkill_samples.get(kw, [])[:5],
                "suggestion": "细化或移除",
                "status": "pending",
            })
    return alerts


def mine_all():
    """执行全部挖掘, 保存到 rule_suggestions.json"""
    groups = store.get_groups()

    suggestions = {
        "mined_at": datetime.now().isoformat(timespec="seconds"),
        "total_labels": sum(len(g) for g in groups.values()),
        "groups": {
            "G1": len(groups["G1"]),
            "G2": len(groups["G2"]),
            "G3": len(groups["G3"]),
            "G4": len(groups["G4"]),
        },
        "suggested_exclude": mine_exclude_suggestions(),
        "suggested_include": mine_include_suggestions(),
        "overkill_alert": mine_overkill_alerts(),
    }
    store.save_suggestions(suggestions)
    return suggestions


def apply_suggestions(add_exclude=None, add_include=None, remove_exclude=None):
    """
    应用挖掘建议到 rules.json
    :return: dict {"added_exclude": [...], "added_include": [...], "removed_exclude": [...]}
    """
    result = {"added_exclude": [], "added_include": [], "removed_exclude": []}
    if add_exclude:
        result["added_exclude"] = store.add_exclude_keywords(add_exclude, source="miner")
    if add_include:
        result["added_include"] = store.add_include_keywords(add_include, source="miner")
    if remove_exclude:
        for kw in remove_exclude:
            if store.remove_exclude_keyword(kw, source="overkill_fix"):
                result["removed_exclude"].append(kw)
    return result


def format_suggestions(sug):
    """格式化挖掘结果为可读字符串"""
    lines = []
    lines.append("=" * 55)
    lines.append("🔧 规则挖掘结果")
    lines.append("=" * 55)
    lines.append(f"挖掘时间: {sug.get('mined_at', '')}")
    lines.append(f"标注总数: {sug.get('total_labels', 0)}")
    g = sug.get("groups", {})
    lines.append(f"分组: G1投对={g.get('G1',0)} G2错投={g.get('G2',0)} "
                 f"G3漏投={g.get('G3',0)} G4拦对={g.get('G4',0)}")
    lines.append("")

    lines.append("【建议新增排除词】(来自错投样本)")
    excl = sug.get("suggested_exclude", [])
    if not excl:
        lines.append("  (无)")
    for s in excl[:15]:
        lines.append(f"  {s['keyword']:<12} (错投{s['rejected']}次, 投对{s['accepted']}次, 置信{s['score']})")
    lines.append("")

    lines.append("【建议新增白名单】(来自漏投样本)")
    incl = sug.get("suggested_include", [])
    if not incl:
        lines.append("  (无)")
    for s in incl[:15]:
        lines.append(f"  {s['keyword']:<12} (漏投{s['missed']}次, 拦对{s['correctly_excluded']}次, 置信{s['score']})")
    lines.append("")

    lines.append("【误杀告警】(现有排除词排太宽)")
    alerts = sug.get("overkill_alert", [])
    if not alerts:
        lines.append("  (无)")
    for a in alerts:
        samples = ", ".join(a.get("overkill_samples", [])[:3])
        lines.append(f"  '{a['keyword']}' 误杀{a['overkill_count']}次  样本: {samples}")
    lines.append("=" * 55)
    return "\n".join(lines)
