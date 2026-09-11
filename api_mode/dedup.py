# 中央去重存储 —— 原子 check-and-set，跨进程 / 重启生效
#
# 旧模式用 applied.json（普通文件、无锁）做去重，并发下会重复投递。
# 这里用 SQLite：job_id 作为 PRIMARY KEY，INSERT OR IGNORE 保证「同一职位只被预约/投递一次」，
# 所有 worker 先 try_reserve 抢占，抢占成功才去投递。

import os
import sqlite3
import threading
from datetime import datetime, date

_lock = threading.Lock()


def _connect(db_path: str):
    parent = os.path.dirname(db_path) or "."
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS applied (
               job_id    TEXT PRIMARY KEY,
               name      TEXT,
               company   TEXT,
               salary    TEXT,
               status    TEXT,
               run_id    TEXT,
               created_at TEXT
           )"""
    )
    conn.commit()
    return conn


class DedupStore:
    def __init__(self, db_path: str = "data/dedup.db"):
        self.db_path = db_path
        self._conn = _connect(db_path)

    def _today(self) -> str:
        return date.today().isoformat()

    def try_reserve(self, job_id, name="", company="", salary="", run_id="") -> bool:
        """原子预约：未被处理过返回 True 并标记 reserved；已存在返回 False。"""
        with _lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO applied"
                "(job_id,name,company,salary,status,run_id,created_at) VALUES(?,?,?,?,?,?,?)",
                (job_id, name, company, salary, "reserved", run_id,
                 datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def mark_applied(self, job_id):
        with _lock:
            self._conn.execute(
                "UPDATE applied SET status='applied' WHERE job_id=?", (job_id,)
            )
            self._conn.commit()

    def release(self, job_id):
        """投递失败，释放预约以便后续重试。"""
        with _lock:
            self._conn.execute(
                "DELETE FROM applied WHERE job_id=? AND status='reserved'", (job_id,)
            )
            self._conn.commit()

    def is_applied(self, job_id) -> bool:
        with _lock:
            row = self._conn.execute(
                "SELECT 1 FROM applied WHERE job_id=? AND status='applied'", (job_id,)
            ).fetchone()
            return row is not None

    def today_count(self) -> int:
        with _lock:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM applied WHERE status='applied'"
                " AND substr(created_at,1,10)=?",
                (self._today(),),
            ).fetchone()[0]
            return n
