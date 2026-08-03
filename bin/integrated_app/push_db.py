"""PWA 推送订阅 SQLite 存储模块（Phase 3）。

架构说明：
    管理 Web Push 订阅记录（endpoint URL + 浏览器加密密钥），供后端
    ``push_sender.py`` 在生成完成时向所有订阅者发送推送通知。

    使用独立的 SQLite 数据库文件 ``data/push_subscriptions.db``，与
    ``history_db.py`` 分离，避免推送功能的增删操作影响历史记录查询性能。

    线程安全：使用 ``threading.local`` 维护线程本地连接，配合 WAL 模式
    支持并发读写（写不阻塞读）。

数据模型：
    push_subscriptions 表：
        - endpoint (TEXT PRIMARY KEY) — 推送服务端点 URL（唯一）
        - p256dh (TEXT) — 浏览器 ECDH 公钥（Base64URL）
        - auth (TEXT) — 浏览器认证密钥（Base64URL）
        - created_at (TEXT) — 订阅时间 ISO 格式
        - updated_at (TEXT) — 最后更新时间
        - user_agent (TEXT) — 订阅时浏览器 UA（调试用）

Refs:
    - RFC 8030: Generic Event Delivery Using HTTP Push
    - RFC 8291: Message Encryption for WebPush
    - MDN: PushManager.subscribe()
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any

logger = logging.getLogger("tts_multimodel.push_db")

_DB_PATH: str = ""
_db_lock = threading.Lock()
_thread_local = threading.local()
_initialized: bool = False

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint   TEXT PRIMARY KEY,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    user_agent TEXT DEFAULT ''
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_push_created_at
ON push_subscriptions(created_at)
"""


def _get_db_path() -> str:
    """获取推送订阅数据库路径（延迟初始化）。"""
    global _DB_PATH
    if not _DB_PATH:
        from .config import PROJECT_ROOT

        data_dir = os.path.join(PROJECT_ROOT, "data")
        os.makedirs(data_dir, exist_ok=True)
        _DB_PATH = os.path.join(data_dir, "push_subscriptions.db")
    return _DB_PATH


def _get_conn() -> sqlite3.Connection:
    """获取线程本地的 SQLite 连接。

    使用 threading.local 确保每个线程有独立的连接，
    避免 SQLite "threads can only be created in their own thread" 错误。
    """
    conn = getattr(_thread_local, "conn", None)
    if conn is None or _is_conn_closed(conn):
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        _thread_local.conn = conn
        _ensure_schema(conn)
    return conn


def _is_conn_closed(conn: sqlite3.Connection) -> bool:
    """检查连接是否已关闭。"""
    try:
        conn.execute("SELECT 1")
        return False
    except Exception:
        return True


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """应用 SQLite PRAGMA 优化配置。"""
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA cache_size=-8192")  # 8MB cache
    except sqlite3.DatabaseError as e:
        logger.warning("push_db PRAGMA 设置失败: %s", e)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """确保表和索引存在（幂等）。"""
    global _initialized
    if _initialized:
        return
    with _db_lock:
        if _initialized:
            return
        try:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.commit()
            _initialized = True
            logger.debug("push_db schema initialized: %s", _get_db_path())
        except sqlite3.DatabaseError as e:
            logger.error("push_db schema 初始化失败: %s", e)


def add_subscription(
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str = "",
) -> bool:
    """添加或更新推送订阅记录。

    如果 endpoint 已存在，则更新 p256dh / auth / updated_at / user_agent。

    Args:
        endpoint: 推送服务端点 URL（主键）。
        p256dh: 浏览器 ECDH P-256 公钥（Base64URL）。
        auth: 浏览器认证密钥（Base64URL）。
        user_agent: 订阅时浏览器 UA（可选，调试用）。

    Returns:
        True 表示写入成功，False 表示失败。
    """
    if not endpoint or not p256dh or not auth:
        logger.warning("add_subscription: 缺少必填字段 endpoint/p256dh/auth")
        return False

    now = datetime.now().isoformat()
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO push_subscriptions (endpoint, p256dh, auth, created_at, updated_at, user_agent)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(endpoint) DO UPDATE SET
                   p256dh=excluded.p256dh,
                   auth=excluded.auth,
                   updated_at=excluded.updated_at,
                   user_agent=excluded.user_agent
            """,
            (endpoint, p256dh, auth, now, now, user_agent),
        )
        conn.commit()
        logger.info("push_db: 订阅已保存 endpoint=%s...", endpoint[:60])
        return True
    except sqlite3.DatabaseError as e:
        logger.error("push_db add_subscription 失败: %s", e)
        return False


def remove_subscription(endpoint: str) -> bool:
    """删除推送订阅记录。

    Args:
        endpoint: 要删除的推送服务端点 URL。

    Returns:
        True 表示删除成功（或原本就不存在），False 表示数据库错误。
    """
    if not endpoint:
        return False
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        conn.commit()
        logger.info("push_db: 订阅已删除 endpoint=%s...", endpoint[:60])
        return True
    except sqlite3.DatabaseError as e:
        logger.error("push_db remove_subscription 失败: %s", e)
        return False


def get_all_subscriptions() -> list[dict[str, Any]]:
    """获取所有推送订阅记录。

    Returns:
        订阅字典列表，每项包含 endpoint / p256dh / auth / created_at / updated_at。
        数据库错误时返回空列表。
    """
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT endpoint, p256dh, auth, created_at, updated_at FROM push_subscriptions ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.DatabaseError as e:
        logger.error("push_db get_all_subscriptions 失败: %s", e)
        return []


def get_subscription_count() -> int:
    """获取当前订阅总数。

    Returns:
        订阅记录数；数据库错误时返回 0。
    """
    try:
        conn = _get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM push_subscriptions")
        return cursor.fetchone()[0]
    except sqlite3.DatabaseError as e:
        logger.error("push_db get_subscription_count 失败: %s", e)
        return 0


def close_all() -> None:
    """关闭所有线程本地连接（应用退出时调用）。"""
    global _initialized
    with _db_lock:
        conn = getattr(_thread_local, "conn", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
            _thread_local.conn = None
        _initialized = False
