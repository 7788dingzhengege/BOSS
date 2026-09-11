# 指标层: 准确率/召回率/错投率计算 + 历史趋势

from datetime import datetime
from . import store

# ====== Embedding 分界配置 ======
# 第 EMBEDDING_START_INDEX (从1开始) 轮及以后为 embedding 阶段
# 之前为纯规则阶段。两段在滚动累计模式下各自独立累计分母, 互不混。
# 当前: 第 1~10 轮纯规则, 第 11 轮及以后 embedding
EMBEDDING_START_INDEX = 11


def compute_metrics(run_id=None, group=None):
    """
    计算准确率指标
    :param run_id: 指定轮次; None=全量
    :param group: 岗位分组名; None=全部
    :return: dict
    """
    labeled = store.get_labeled(group)
    if run_id:
        labeled = [j for j in labeled if j.get("run_id") == run_id]

    G1, G2, G3, G4 = 0, 0, 0, 0
    for j in labeled:
        s = j.get("status")
        l = j.get("label")
        if s == "applied" and l == "accepted":
            G1 += 1
        elif s == "applied" and l == "rejected":
            G2 += 1
        elif s == "excluded" and l == "accepted":
            G3 += 1
        elif s == "excluded" and l == "rejected":
            G4 += 1

    total = G1 + G2 + G3 + G4

    def safe_rate(a, b):
        return round(a / b, 4) if b > 0 else None

    return {
        "run_id": run_id or "all",
        "total_labeled": total,
        "G1": G1, "G2": G2, "G3": G3, "G4": G4,
        # 投递准确率 = 投对 / (投对 + 错投)
        "apply_accuracy": safe_rate(G1, G1 + G2),
        # 过滤准确率 = 拦对 / (拦对 + 漏投)
        "exclude_accuracy": safe_rate(G4, G3 + G4),
        # 综合准确率 = (投对 + 拦对) / 总标注
        "overall_accuracy": safe_rate(G1 + G4, total),
        # 错投率 = 错投 / (错投 + 拦对)
        "false_apply_rate": safe_rate(G2, G2 + G4),
        # 漏投率 = 漏投 / (投对 + 漏投)
        "miss_rate": safe_rate(G3, G1 + G3),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
    }


def compute_run_metrics(run_id):
    """计算单轮指标并追加到历史"""
    m = compute_metrics(run_id)
    store.append_metrics(m)
    return m


def recompute_all_run_metrics():
    """
    重新计算所有 run_id 的指标并覆盖 metrics_history
    在标注完成后调用, 确保趋势图显示最新指标
    """
    labeled = store.get_labeled()
    run_ids = sorted(set(j.get("run_id", "") for j in labeled if j.get("run_id")))
    history = store.load_metrics_history()
    # 保留已有但已不在 labels 里的记录? 直接覆盖为最新
    new_rounds = []
    for rid in run_ids:
        new_rounds.append(compute_metrics(rid))
    store.save_metrics_history({"rounds": new_rounds})
    return new_rounds


def compute_all_runs():
    """计算所有已记录轮次的指标(用于趋势)"""
    history = store.load_metrics_history()
    return history.get("rounds", [])


def compute_all_runs_rolling(alpha=1.0):
    """
    滚动累计 + Laplace 平滑 (工业级小样本准确率)
    公式: acc = (sum + alpha) / (count + 2*alpha)
    alpha=1 时即 Laplace 平滑 (加 1 正确 + 1 错误的先验)
    防止小样本出现 100%/0% 的极端值

    分段独立累计: 第 1~(EMBEDDING_START_INDEX-1) 轮为纯规则段,
    第 EMBEDDING_START_INDEX 轮及以后为 embedding 段。
    两段各自从 0 开始累计 G1/G2/G3/G4, 分母互不混。
    每轮记录带 is_embedding 标记, 供趋势图用不同颜色绘制。
    """
    rounds = compute_all_runs()
    if not rounds:
        return []

    # 两段各自的累计计数器
    rule_G1, rule_G2, rule_G3, rule_G4 = 0, 0, 0, 0      # 纯规则段
    embed_G1, embed_G2, embed_G3, embed_G4 = 0, 0, 0, 0   # embedding 段

    result = []

    for idx, r in enumerate(rounds):
        run_idx = idx + 1  # 从 1 开始的轮次序号
        is_embed = run_idx >= EMBEDDING_START_INDEX

        if is_embed:
            embed_G1 += r.get("G1", 0)
            embed_G2 += r.get("G2", 0)
            embed_G3 += r.get("G3", 0)
            embed_G4 += r.get("G4", 0)
            g1, g2, g3, g4 = embed_G1, embed_G2, embed_G3, embed_G4
        else:
            rule_G1 += r.get("G1", 0)
            rule_G2 += r.get("G2", 0)
            rule_G3 += r.get("G3", 0)
            rule_G4 += r.get("G4", 0)
            g1, g2, g3, g4 = rule_G1, rule_G2, rule_G3, rule_G4

        total = g1 + g2 + g3 + g4

        # 投递准确率 = 投对 / (投对 + 错投) + Laplace
        apply_n = g1 + g2
        apply_acc = (g1 + alpha) / (apply_n + 2 * alpha) if apply_n > 0 else None

        # 过滤准确率 = 拦对 / (拦对 + 漏投) + Laplace
        exclude_n = g3 + g4
        exclude_acc = (g4 + alpha) / (exclude_n + 2 * alpha) if exclude_n > 0 else None

        # 综合准确率 = (投对 + 拦对) / 总数 + Laplace
        correct_n = g1 + g4
        overall_acc = (correct_n + 2 * alpha) / (total + 4 * alpha) if total > 0 else None

        result.append({
            "run_id": r["run_id"],
            "total_labeled": total,
            "G1": g1, "G2": g2, "G3": g3, "G4": g4,
            "apply_accuracy": round(apply_acc, 4) if apply_acc is not None else None,
            "exclude_accuracy": round(exclude_acc, 4) if exclude_acc is not None else None,
            "overall_accuracy": round(overall_acc, 4) if overall_acc is not None else None,
            "false_apply_rate": round(g2 / (g2 + g4), 4) if (g2 + g4) > 0 else None,
            "miss_rate": round(g3 / (g1 + g3), 4) if (g1 + g3) > 0 else None,
            "is_embedding": is_embed,  # 标记: True=embedding段, False=纯规则段
        })
    return result


def predict_next_round(series, alpha=0.5, beta=0.3, horizon=1):
    """
    Holt 双参数指数平滑预测 (工业级时序预测)
    - alpha: 水平平滑系数 (0~1, 推荐 0.5)
    - beta:  趋势平滑系数 (0~1, 推荐 0.3)
    - horizon: 预测几步
    返回: 未来 horizon 轮的预测值 (None 表示数据不足)
    """
    if not series or len(series) < 3:
        return None

    # 过滤 None
    series = [x for x in series if x is not None]
    if len(series) < 3:
        return None

    # 初始化 level 和 trend
    level = series[0]
    trend = series[1] - series[0]

    # 递推更新
    for x in series[1:]:
        prev_level = level
        level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend

    # 预测 horizon 步后的值
    pred = level + horizon * trend
    # 限制在 [0, 1] 区间
    return max(0.0, min(1.0, pred))


def predict_overall_accuracy(rounds=None, horizon=1):
    """
    预测下一轮综合准确率
    rounds: 已计算好的轮次列表 (None=自动从历史加载, 使用滚动累计)
    返回: 预测值 (0~1) 或 None
    """
    if rounds is None:
        rounds = compute_all_runs_rolling()
    series = [r.get("overall_accuracy") for r in rounds]
    return predict_next_round(series, alpha=0.5, beta=0.3, horizon=horizon)


def format_metrics(m):
    """格式化指标为可读字符串"""
    def pct(v):
        return f"{v*100:.1f}%" if v is not None else "N/A"

    lines = []
    lines.append("=" * 50)
    lines.append("📊 飞轮指标" + (f" (轮次: {m['run_id']})" if m["run_id"] != "all" else " (全量)"))
    lines.append("=" * 50)
    lines.append("【四象限分布】")
    lines.append(f"  G1 投对: {m['G1']}  G2 错投: {m['G2']}")
    lines.append(f"  G3 漏投: {m['G3']}  G4 拦对: {m['G4']}")
    lines.append(f"  总标注:  {m['total_labeled']}")
    lines.append("")
    lines.append("【准确率】")
    lines.append(f"  投递准确率: {pct(m['apply_accuracy'])}   (投对/投对+错投)")
    lines.append(f"  过滤准确率: {pct(m['exclude_accuracy'])}   (拦对/拦对+漏投)")
    lines.append(f"  综合准确率: {pct(m['overall_accuracy'])}   (投对+拦对/总数)")
    lines.append("")
    lines.append("【问题率】")
    lines.append(f"  错投率:     {pct(m['false_apply_rate'])}   (错投/错投+拦对)")
    lines.append(f"  漏投率:     {pct(m['miss_rate'])}   (漏投/投对+漏投)")
    lines.append("=" * 50)
    return "\n".join(lines)


def format_trend(rounds):
    """格式化趋势表"""
    if not rounds:
        return "暂无历史数据, 标注后才会生成趋势。"

    lines = []
    lines.append("=" * 65)
    lines.append("📈 飞轮趋势")
    lines.append("=" * 65)
    lines.append(f"{'轮次':<16} {'投递准确':>8} {'过滤准确':>8} {'综合准确':>8} {'错投':>4} {'漏投':>4}")
    lines.append("-" * 65)

    def pct(v):
        return f"{v*100:.1f}%" if v is not None else "  N/A"

    prev_overall = None
    for r in rounds[-10:]:  # 最近10轮
        rid = str(r.get("run_id", ""))[:14]
        oa = r.get("overall_accuracy")
        arrow = ""
        if prev_overall is not None and oa is not None:
            if oa > prev_overall:
                arrow = " ↑"
            elif oa < prev_overall:
                arrow = " ↓"
        lines.append(
            f"{rid:<16} {pct(r.get('apply_accuracy')):>8} "
            f"{pct(r.get('exclude_accuracy')):>8} {pct(oa):>8}{arrow} "
            f"{r.get('G2',0):>4} {r.get('G3',0):>4}"
        )
        prev_overall = oa

    lines.append("=" * 65)
    return "\n".join(lines)


def flywheel_health():
    """飞轮健康度判断"""
    rounds = compute_all_runs()
    if len(rounds) < 2:
        return "数据不足, 至少需要2轮标注才能判断趋势"

    recent = rounds[-3:]
    overalls = [r.get("overall_accuracy") for r in recent if r.get("overall_accuracy") is not None]
    if len(overalls) < 2:
        return "数据不足"

    if all(overalls[i] <= overalls[i+1] for i in range(len(overalls)-1)):
        return "✅ 飞轮在转(综合准确率连续上升)"
    elif all(overalls[i] >= overalls[i+1] for i in range(len(overalls)-1)):
        return "⚠️ 飞轮倒退(准确率下降, 检查最近挖掘的规则)"

    # 看最近一轮的问题率
    last = rounds[-1]
    miss = last.get("miss_rate")
    false_apply = last.get("false_apply_rate")
    if miss is not None and miss > 0.3:
        return "⚠️ 漏投率过高(>30%), 规则太严, 建议加白名单或删排除词"
    if false_apply is not None and false_apply > 0.2:
        return "⚠️ 错投率过高(>20%), 规则太松, 建议加排除词"
    return "✅ 飞轮状态正常"
