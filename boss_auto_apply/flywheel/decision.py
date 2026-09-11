# 决策层: 规则匹配, 合并 gui_exclude + rules.json 的排除词

from . import store


def get_merged_exclude_keywords(gui_exclude):
    """
    合并 GUI 配置的排除词和飞轮 rules.json 的排除词
    :param gui_exclude: list, 来自 gui_settings.json
    :return: 去重后的合并列表
    """
    rules_exclude = store.get_effective_exclude()
    merged = []
    seen = set()
    for kw in (gui_exclude or []) + (rules_exclude or []):
        kw = (kw or "").strip()
        if kw and kw.lower() not in seen:
            merged.append(kw)
            seen.add(kw.lower())
    return merged


def check_exclude(text, exclude_keywords):
    """
    检查文本是否命中排除词(大小写不敏感, 子串匹配)
    :return: (是否命中, 命中的词)
    """
    if not text or not exclude_keywords:
        return False, ""
    text_lower = text.lower()
    for kw in exclude_keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            return True, kw
    return False, ""


def check_include(text, include_keywords):
    """检查是否命中白名单(命中则高置信保留)"""
    if not text or not include_keywords:
        return False, ""
    text_lower = text.lower()
    for kw in include_keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            return True, kw
    return False, ""


def decide(job_name, company, gui_exclude):
    """
    对单个职位做规则决策
    :return: dict {
        "decision": "apply" | "exclude",
        "hit_keyword": str,
        "rule_source": "gui" | "rules" | "merged"
    }
    """
    merged = get_merged_exclude_keywords(gui_exclude)
    excluded, hit = check_exclude(job_name, merged)
    if not excluded:
        excluded, hit = check_exclude(company, merged)
    if excluded:
        # 判断来源: 若命中词在 rules.json 则 source=rules, 否则 gui
        rules_exclude = store.get_effective_exclude()
        source = "rules" if hit in rules_exclude else "gui"
        return {"decision": "exclude", "hit_keyword": hit, "rule_source": source}
    return {"decision": "apply", "hit_keyword": "", "rule_source": "merged"}
