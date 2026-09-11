# 标注逻辑层: 三类标注(投对/错投/漏投/拦对)

from . import store


def _trigger_embed_warmup():
    """标注完成后自动触发 embedding 缓存增量更新 (异步, 不阻塞 GUI)"""
    try:
        from . import embedder
        embedder.async_warmup()
    except Exception:
        pass  # embedding 未安装或不可用时静默跳过, 不影响标注流程


def label_accepted(job_id, note=""):
    """标注为 accepted(投对了 / 该投)"""
    store.update_label(job_id, "accepted", note)
    _trigger_embed_warmup()


def label_rejected(job_id, note=""):
    """标注为 rejected(错投了 / 该排)"""
    store.update_label(job_id, "rejected", note)
    _trigger_embed_warmup()


def batch_label_applied_accepted(job_ids):
    """批量: 已投递的标为 accepted(投对)"""
    store.batch_update_labels(job_ids, "accepted")
    _trigger_embed_warmup()


def batch_label_excluded_rejected(job_ids):
    """批量: 被过滤的标为 rejected(拦对)"""
    store.batch_update_labels(job_ids, "rejected")
    _trigger_embed_warmup()


def get_review_queue(group=None):
    """
    获取待标注队列, 分两组返回:
    {
        "applied": [已投递待标...],
        "excluded": [被过滤待标...]
    }
    :param group: 岗位分组名；None=全部（历史数据 group 为空串，也归入"全部"）
    """
    pending = store.get_pending(group)
    applied = [j for j in pending if j.get("status") == "applied"]
    excluded = [j for j in pending if j.get("status") == "excluded"]
    return {"applied": applied, "excluded": excluded}


def get_review_summary(group=None):
    """获取标注概要(用于按钮显示)；group=None=全部"""
    groups = store.get_groups(group)
    pending = store.get_pending(group)
    total_labeled = sum(len(g) for g in groups.values())

    return {
        "pending_count": len(pending),
        "applied_pending": sum(1 for j in pending if j.get("status") == "applied"),
        "excluded_pending": sum(1 for j in pending if j.get("status") == "excluded"),
        "total_labeled": total_labeled,
        "G1": len(groups["G1"]),
        "G2": len(groups["G2"]),
        "G3": len(groups["G3"]),
        "G4": len(groups["G4"]),
    }
