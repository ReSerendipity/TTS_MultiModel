"""SQLite-based history index for fast querying of generation records.

重构说明 (H-R2/R3/R4/R5):
- H-R2: 统一 INSERT 逻辑，提取 _INSERT_SQL 常量 + _build_record_tuple 方法
- H-R3: 连接管理重构 — _apply_pragmas 统一 PRAGMA(含 busy_timeout),
        单例创建加锁, set 追踪所有线程连接, 新增 close_all()
        （修订：原 H-R3 使用 weakref.WeakSet 追踪连接，但 sqlite3.Connection
        是 C 扩展类型，不支持 __weakref__ 槽位，运行时抛 TypeError。改为
        普通集合 + 显式 close()/close_all() 清理，避免泄漏。）
- H-R4: delete_multiple_records 文件删除移出事务, 保证数据一致性
- H-R5: 批量操作分块 (_CHUNK_SIZE=500), 避免 SQLITE_MAX_VARIABLE_NUMBER
"""

import contextlib
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("tts_multimodel")

# --- 常量提取 (H-R3/A3-1 消除魔法数字) ---
# REFACTOR: [H-R3] 统一 PRAGMA 配置，消除三处重复
_PRAGMA_CONFIG = {
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    "cache_size": -64000,  # 64MB page cache (negative = KB)
    "temp_store": "MEMORY",
    "mmap_size": 268435456,  # 256MB memory-mapped I/O
    "busy_timeout": 5000,  # H-R3: 5s 锁等待，避免 database is locked 错误
}

# REFACTOR: [H-R5] 批量操作分块大小，SQLite 默认 SQLITE_MAX_VARIABLE_NUMBER=999
_CHUNK_SIZE = 500

# REFACTOR: [H-R2] 统一 INSERT SQL，消除 add_record/insert/insert_batch 三处重复
# 字段顺序必须与 _build_record_tuple 保持一致
_INSERT_FIELDS = (
    "filename, filepath, created_at, file_size_bytes, duration_seconds, "
    "text_preview, engine, model_type, model_size, lang, persona_name, "
    "output_format, temperature, seed, speed, is_success, error_msg, "
    "is_degraded, tags, hidden, created_timestamp"
)
_INSERT_PLACEHOLDERS = ", ".join(["?"] * 21)
_INSERT_SQL = f"INSERT OR REPLACE INTO generation_history ({_INSERT_FIELDS}) VALUES ({_INSERT_PLACEHOLDERS})"

# 时间过滤器常量 (A3-1)
_SECONDS_PER_DAY = 86400
_SECONDS_PER_WEEK = 604800
_SECONDS_PER_MONTH = 2592000

# 文本预览最大长度
_TEXT_PREVIEW_MAX_LENGTH = 100


class HistoryDatabase:
    """SQLite-based history index for efficient querying of generation records.

    Replaces slow glob-based filesystem scanning and JSON-based HistoryManager
    with indexed database queries.

    Performance features:
    - Thread-local connection pooling with set-based tracking (H-R3)
    - WAL mode + busy_timeout for concurrent read/write access (H-R3)
    - Unified PRAGMA configuration via _apply_pragmas (H-R3)
    - Chunked batch operations to respect SQLITE_MAX_VARIABLE_NUMBER (H-R5)
    - File deletion decoupled from DB transactions for consistency (H-R4)
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._thread_local = threading.local()
        self.last_sync_mtime: float = 0.0
        # H-R3: 用 set 追踪所有线程连接，支持 close_all()
        # 修订：原使用 weakref.WeakSet，但 sqlite3.Connection 是 C 扩展类型，
        # 不支持 __weakref__ 槽位，WeakSet.add() 会抛 TypeError。
        # 改为普通 set + 显式 close()/close_all() 清理，由调用方负责生命周期。
        self._all_connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.Lock()
        self._ensure_table()
        self._migrate_add_hidden_column()
        self._migrate_add_created_timestamp_column()
        self._migrate_add_file_missing_column()
        self._optimize_pragmas()
        self._ensure_indexes()

    # ------------------------------------------------------------------
    # 连接管理 (H-R3 重构)
    # ------------------------------------------------------------------

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """REFACTOR: [H-R3] 统一应用 PRAGMA 配置，消除三处重复。

        在每个新连接上设置 WAL、busy_timeout、cache_size 等。
        busy_timeout=5000 让锁竞争时等待 5s 而非立即抛错。
        """
        for pragma, value in _PRAGMA_CONFIG.items():
            try:
                conn.execute(f"PRAGMA {pragma}={value}")
            except sqlite3.DatabaseError as e:
                logger.debug(f"设置 PRAGMA {pragma}={value} 失败: {e}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local cached connection. Creates one on first access per thread.

        If the database is corrupted (sqlite3.DatabaseError), the corrupted file
        is renamed to {db_path}.corrupted and a fresh database is created.
        """
        conn = getattr(self._thread_local, "connection", None)
        if conn is None:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                self._apply_pragmas(conn)  # H-R3: 统一 PRAGMA
            except sqlite3.DatabaseError:
                logger.warning(f"数据库已损坏: {self._db_path}，尝试自动重建")
                # Close the failed connection if it was partially created
                if conn is not None:
                    with contextlib.suppress(Exception):
                        conn.close()
                # Rename corrupted file and create a fresh database
                corrupted_path = f"{self._db_path}.corrupted"
                try:
                    if os.path.exists(self._db_path):
                        # Avoid overwriting existing .corrupted file
                        if os.path.exists(corrupted_path):
                            corrupted_path = f"{self._db_path}.corrupted.{int(time.time())}"
                        os.rename(self._db_path, corrupted_path)
                        logger.warning(f"已将损坏的数据库重命名为: {corrupted_path}")
                except OSError as e:
                    logger.error(f"重命名损坏的数据库失败: {e}")
                # Create fresh connection with unified PRAGMAs (H-R3)
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                self._apply_pragmas(conn)
                # Re-run table and index creation for the fresh database
                self._ensure_table()
                self._ensure_indexes()
                logger.info("数据库损坏后重建成功")
            # H-R3: 注册到全局 set 以支持 close_all()
            with self._connections_lock:
                self._all_connections.add(conn)
            self._thread_local.connection = conn
        return conn

    def close(self):
        """Close the current thread's connection if open."""
        conn = getattr(self._thread_local, "connection", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
            # H-R3: 从全局 set 移除已关闭的连接，避免泄漏
            with self._connections_lock:
                self._all_connections.discard(conn)
            self._thread_local.connection = None

    def close_all(self):
        """REFACTOR: [H-R3] 关闭所有线程的连接，修复连接泄漏。

        在应用 shutdown 时调用，清理所有线程本地连接。
        普通集合无法自动 GC 已关闭的连接，因此需要显式遍历关闭并清空。
        """
        with self._connections_lock:
            for conn in list(self._all_connections):
                with contextlib.suppress(Exception):
                    conn.close()
            self._all_connections.clear()
        # 清理当前线程本地引用
        self._thread_local.connection = None
        logger.info("[history_db] 已关闭所有线程连接")

    @contextmanager
    def _transaction(self):
        """Context manager for transactional operations using thread-local connection."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _execute(self, sql: str, params=()):
        """Execute a query using thread-local connection (for read-only ops)."""
        conn = self._get_connection()
        return conn.execute(sql, params)

    # ------------------------------------------------------------------
    # Schema 与迁移
    # ------------------------------------------------------------------

    def _ensure_table(self):
        """Create the generation_history table if it doesn't exist."""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT '',
                    file_size_bytes INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL,
                    text_preview TEXT NOT NULL DEFAULT '',
                    engine TEXT NOT NULL DEFAULT 'unknown',
                    model_type TEXT,
                    model_size TEXT,
                    lang TEXT DEFAULT 'zh',
                    persona_name TEXT,
                    output_format TEXT DEFAULT 'wav',
                    temperature REAL DEFAULT 0.9,
                    seed INTEGER DEFAULT 42,
                    speed REAL DEFAULT 1.0,
                    is_success INTEGER NOT NULL DEFAULT 1,
                    error_msg TEXT,
                    is_degraded INTEGER NOT NULL DEFAULT 0,
                    tags TEXT DEFAULT '',
                    hidden INTEGER NOT NULL DEFAULT 0,
                    created_timestamp REAL NOT NULL DEFAULT 0
                )
            """)

    def _migrate_add_hidden_column(self):
        """Add 'hidden' column if it doesn't exist (migration for existing DBs)."""
        try:
            cursor = self._execute("SELECT hidden FROM generation_history LIMIT 1")
            cursor.fetchall()
        except sqlite3.OperationalError:
            with self._transaction() as conn:
                conn.execute("ALTER TABLE generation_history ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
            logger.info("数据库迁移: 已添加 'hidden' 列")

    def _migrate_add_created_timestamp_column(self):
        """Add 'created_timestamp' column if it doesn't exist (migration for existing DBs)."""
        try:
            cursor = self._execute("SELECT created_timestamp FROM generation_history LIMIT 1")
            cursor.fetchall()
        except sqlite3.OperationalError:
            with self._transaction() as conn:
                conn.execute("ALTER TABLE generation_history ADD COLUMN created_timestamp REAL NOT NULL DEFAULT 0")
            logger.info("数据库迁移: 已添加 'created_timestamp' 列")

    def _migrate_add_file_missing_column(self):
        """Add 'file_missing' column if it doesn't exist (migration for existing DBs)."""
        try:
            cursor = self._execute("SELECT file_missing FROM generation_history LIMIT 1")
            cursor.fetchall()
        except sqlite3.OperationalError:
            with self._transaction() as conn:
                conn.execute("ALTER TABLE generation_history ADD COLUMN file_missing INTEGER NOT NULL DEFAULT 0")
            logger.info("数据库迁移: 已添加 'file_missing' 列")

    def _ensure_indexes(self):
        """Create missing indexes for common query patterns."""
        indexes = [
            ("idx_history_created_at", "generation_history(created_at DESC)"),
            ("idx_history_engine", "generation_history(engine)"),
            ("idx_history_persona", "generation_history(persona_name)"),
            ("idx_history_engine_created", "generation_history(engine, created_at DESC)"),
            ("idx_history_persona_created", "generation_history(persona_name, created_at DESC)"),
            ("idx_history_is_success", "generation_history(is_success)"),
            # REFACTOR: [I2-1] 移除 idx_history_filepath — filepath UNIQUE 约束已自带索引
            ("idx_history_hidden", "generation_history(hidden)"),
            ("idx_history_created_timestamp", "generation_history(created_timestamp DESC)"),
            ("idx_history_file_missing", "generation_history(file_missing)"),
        ]
        with self._transaction() as conn:
            for name, columns in indexes:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {columns}")

    def _optimize_pragmas(self):
        """Set performance-oriented PRAGMAs for the database.

        H-R3: 委托给 _apply_pragmas，消除重复。
        """
        conn = self._get_connection()
        # optimize PRAGMA 需要单独处理（值=0 时执行 PRAGMA optimize）
        try:
            conn.execute("PRAGMA optimize")
        except sqlite3.DatabaseError as e:
            logger.debug(f"设置 PRAGMA optimize 失败: {e}")

    # ------------------------------------------------------------------
    # 记录构建 (H-R2 统一 INSERT 逻辑)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_record_tuple(record: dict[str, Any], timestamp: float | None = None) -> tuple:
        """REFACTOR: [H-R2] 统一构建 INSERT 参数元组，消除三处重复。

        字段顺序必须与 _INSERT_SQL 的占位符顺序一致。
        所有字段都提供默认值，避免 KeyError。
        """
        if timestamp is None:
            timestamp = record.get("created_timestamp", time.time())
        return (
            record.get("filename", ""),
            record.get("filepath", ""),
            record.get("created_at", ""),
            record.get("file_size_bytes", 0),
            record.get("duration_seconds"),
            record.get("text_preview", ""),
            record.get("engine", "unknown"),
            record.get("model_type"),
            record.get("model_size"),
            record.get("lang", "zh"),
            record.get("persona_name"),
            record.get("output_format", "wav"),
            record.get("temperature", 0.9),
            record.get("seed", 42),
            record.get("speed", 1.0),
            1 if record.get("is_success", True) else 0,
            record.get("error_msg"),
            1 if record.get("is_degraded", False) else 0,
            record.get("tags", ""),
            1 if record.get("hidden", False) else 0,
            timestamp,
        )

    # ------------------------------------------------------------------
    # 写入操作
    # ------------------------------------------------------------------

    def add_record(
        self,
        filename: str,
        filepath: str,
        created_at: str,
        file_size: int,
        text_preview: str = "",
        engine: str = "unknown",
        persona_name: str | None = None,
        duration_seconds: float = 0.0,
    ) -> int:
        """Add a new history record. Returns the record ID."""
        # H-R2: 复用 _build_record_tuple
        record = {
            "filename": filename,
            "filepath": filepath,
            "created_at": created_at,
            "file_size_bytes": file_size,
            "duration_seconds": duration_seconds,
            "text_preview": text_preview,
            "engine": engine,
            "persona_name": persona_name,
        }
        with self._transaction() as conn:
            cursor = conn.execute(_INSERT_SQL, self._build_record_tuple(record))
            return cursor.lastrowid

    def insert(self, record: dict[str, Any]) -> int:
        """Insert a generation record. Returns the record ID."""
        # H-R2: 复用 _build_record_tuple + _INSERT_SQL
        with self._transaction() as conn:
            cursor = conn.execute(_INSERT_SQL, self._build_record_tuple(record))
            return cursor.lastrowid

    def insert_batch(self, records: list[dict[str, Any]]) -> int:
        """Insert multiple records in a single transaction. Returns count inserted.

        H-R5: 分块处理，避免 SQLITE_MAX_VARIABLE_NUMBER 限制。
        """
        if not records:
            return 0
        now = time.time()
        total_inserted = 0
        # H-R5: 分块执行，每块 _CHUNK_SIZE 条
        for chunk_start in range(0, len(records), _CHUNK_SIZE):
            chunk = records[chunk_start : chunk_start + _CHUNK_SIZE]
            params_list = [self._build_record_tuple(r, timestamp=now) for r in chunk]
            with self._transaction() as conn:
                conn.executemany(_INSERT_SQL, params_list)
                total_inserted += len(chunk)
        return total_inserted

    # ------------------------------------------------------------------
    # 查询操作
    # ------------------------------------------------------------------

    def get_records_by_ids(self, ids: list[int]) -> list[dict[str, Any]]:
        """REFACTOR: [S-R7] 公共方法 - 按 id 列表查询历史记录。

        B4: 遵循分层原则，替代 routes/audio.py 中直接调用私有 _execute 的做法。
        使用参数化查询（? 占位符）防止 SQL 注入。

        Args:
            ids: 记录 id 列表（整数）。

        Returns:
            匹配的记录字典列表，字段包含 id/filename/filepath 等。
            若 ids 为空或查询失败，返回空列表。
        """
        if not ids:
            return []
        # H-R5: 批量查询仍受 SQLITE_MAX_VARIABLE_NUMBER 限制，
        # 调用方（routes/audio.py）已通过 _MAX_BATCH_EXPORT_COUNT 限制单次数量
        placeholders = ",".join("?" * len(ids))
        sql = f"SELECT id, filename, filepath FROM generation_history WHERE id IN ({placeholders})"
        try:
            cursor = self._execute(sql, list(ids))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[history_db] 按 id 查询历史记录失败: {e}", exc_info=True)
            return []

    def get_paginated_records(
        self,
        limit: int = 20,
        offset: int = 0,
        search_keyword: str = "",
        time_filter: str = "all",
        duration_filter: str = "all",
        include_hidden: bool = False,
        include_missing: bool = False,
    ) -> dict[str, Any]:
        """Get paginated history records with search and time filter.

        Returns dict with keys: items, total, loaded, hasMore
        """
        # REFACTOR: [D4-1] 校验 limit/offset 上限，防止 OOM
        if limit <= 0 or limit > 1000:
            limit = 20
        if offset < 0:
            offset = 0

        conditions = []
        params: list = []

        if not include_hidden:
            conditions.append("hidden = 0")

        if not include_missing:
            conditions.append("file_missing = 0")

        if search_keyword:
            # REFACTOR: [D4-2] 转义 LIKE 特殊字符，避免意外匹配
            kw_escaped = search_keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            kw_lower = kw_escaped.lower()
            conditions.append("(LOWER(filename) LIKE ? ESCAPE '\\' OR LOWER(text_preview) LIKE ? ESCAPE '\\')")
            params.extend([f"%{kw_lower}%", f"%{kw_lower}%"])

        # Time filter based on created_timestamp
        now = time.time()
        if time_filter == "today":
            conditions.append("created_timestamp > ?")
            params.append(now - _SECONDS_PER_DAY)
        elif time_filter == "week":
            conditions.append("created_timestamp > ?")
            params.append(now - _SECONDS_PER_WEEK)
        elif time_filter == "month":
            conditions.append("created_timestamp > ?")
            params.append(now - _SECONDS_PER_MONTH)

        # Duration filter based on duration_seconds
        if duration_filter == "lt5":
            conditions.append("duration_seconds < 5")
        elif duration_filter == "5to10":
            conditions.append("duration_seconds >= 5 AND duration_seconds < 10")
        elif duration_filter == "gt10":
            conditions.append("duration_seconds >= 10")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Get total count
        cursor = self._execute(f"SELECT COUNT(*) as count FROM generation_history {where_clause}", params)
        total = cursor.fetchone()["count"]

        # Get paginated records
        cursor = self._execute(
            f"""
            SELECT * FROM generation_history
            {where_clause}
            ORDER BY created_timestamp DESC
            LIMIT ? OFFSET ?
        """,
            (*params, limit, offset),
        )

        items = [dict(row) for row in cursor.fetchall()]
        loaded = offset + len(items)
        has_more = loaded < total

        return {
            "items": items,
            "total": total,
            "loaded": loaded,
            "hasMore": has_more,
        }

    # ------------------------------------------------------------------
    # 批量操作 (H-R4 文件与 DB 解耦 + H-R5 分块)
    # ------------------------------------------------------------------

    def delete_multiple_records(self, filenames: list[str], delete_files: bool = False) -> int:
        """Delete multiple records by filename. Optionally delete actual files.

        H-R4: 文件删除移出事务，保证数据一致性。
              先在事务内删除 DB 记录并收集 filepath，事务成功后再删文件。
              避免文件删除成功但 DB 回滚导致文件丢失。
        H-R5: 分块处理 IN 子句，避免 SQLITE_MAX_VARIABLE_NUMBER。
        """
        if not filenames:
            return 0
        filenames = list(dict.fromkeys(filenames))
        filepaths_to_delete: list[str] = []
        count = 0

        # H-R4: 事务内只做 DB 操作，收集待删文件路径
        for chunk_start in range(0, len(filenames), _CHUNK_SIZE):
            chunk = filenames[chunk_start : chunk_start + _CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))
            with self._transaction() as conn:
                if delete_files:
                    cursor = conn.execute(
                        f"SELECT filepath FROM generation_history WHERE filename IN ({placeholders})",
                        chunk,
                    )
                    for row in cursor.fetchall():
                        if row["filepath"]:
                            filepaths_to_delete.append(row["filepath"])
                cursor = conn.execute(
                    f"DELETE FROM generation_history WHERE filename IN ({placeholders})",
                    chunk,
                )
                count += cursor.rowcount

        # H-R4: 事务成功后才删文件；失败不影响 DB 一致性
        if filepaths_to_delete:
            for filepath in filepaths_to_delete:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        logger.debug(f"已删除文件: {filepath}")
                    except OSError as e:
                        logger.error(f"删除文件失败 {filepath}: {e}")
        return count

    def hide_multiple_records(self, filenames: list[str]) -> int:
        """Hide multiple records by filename.

        H-R5: 分块处理 IN 子句。
        """
        if not filenames:
            return 0
        filenames = list(dict.fromkeys(filenames))
        total = 0
        for chunk_start in range(0, len(filenames), _CHUNK_SIZE):
            chunk = filenames[chunk_start : chunk_start + _CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))
            with self._transaction() as conn:
                cursor = conn.execute(
                    f"UPDATE generation_history SET hidden = 1 WHERE filename IN ({placeholders}) AND hidden = 0",
                    chunk,
                )
                total += cursor.rowcount
        return total

    def show_multiple_records(self, filenames: list[str]) -> int:
        """Show (unhide) multiple records by filename.

        H-R5: 分块处理 IN 子句。
        """
        if not filenames:
            return 0
        filenames = list(dict.fromkeys(filenames))
        total = 0
        for chunk_start in range(0, len(filenames), _CHUNK_SIZE):
            chunk = filenames[chunk_start : chunk_start + _CHUNK_SIZE]
            placeholders = ",".join("?" * len(chunk))
            with self._transaction() as conn:
                cursor = conn.execute(
                    f"UPDATE generation_history SET hidden = 0 WHERE filename IN ({placeholders}) AND hidden = 1",
                    chunk,
                )
                total += cursor.rowcount
        return total

    def show_all_records(self) -> int:
        """Show all hidden records."""
        with self._transaction() as conn:
            cursor = conn.execute("UPDATE generation_history SET hidden = 0 WHERE hidden = 1")
            return cursor.rowcount

    def clear_all_records(self, hide_only: bool = True) -> int:
        """Clear all records. If hide_only=True, hide them; otherwise delete them."""
        if hide_only:
            with self._transaction() as conn:
                cursor = conn.execute("UPDATE generation_history SET hidden = 1 WHERE hidden = 0")
                return cursor.rowcount
        else:
            with self._transaction() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM generation_history")
                count = cursor.fetchone()["count"]
                conn.execute("DELETE FROM generation_history")
                return count

    def get_total_count(self, include_hidden: bool = False) -> int:
        """Get total record count."""
        if include_hidden:
            cursor = self._execute("SELECT COUNT(*) as count FROM generation_history")
        else:
            cursor = self._execute("SELECT COUNT(*) as count FROM generation_history WHERE hidden = 0")
        return cursor.fetchone()["count"]

    def query(
        self,
        limit: int = 50,
        offset: int = 0,
        engine: str = None,
        persona_name: str = None,
        search_text: str = None,
        order_by: str = "created_at DESC",
    ) -> list[dict[str, Any]]:
        """Query generation history with filters and pagination."""
        # Validate order_by against whitelist to prevent SQL injection
        _allowed_order_by = {
            "created_at DESC",
            "created_at ASC",
            "file_size_bytes DESC",
            "file_size_bytes ASC",
            "duration_seconds DESC",
            "duration_seconds ASC",
            "engine ASC",
            "engine DESC",
            "created_timestamp DESC",
            "created_timestamp ASC",
        }
        if order_by not in _allowed_order_by:
            order_by = "created_at DESC"

        # REFACTOR: [D4-1] 校验 limit/offset
        if limit <= 0 or limit > 1000:
            limit = 50
        if offset < 0:
            offset = 0

        conditions = []
        params: list = []

        if engine:
            conditions.append("engine = ?")
            params.append(engine)
        if persona_name:
            conditions.append("persona_name = ?")
            params.append(persona_name)
        if search_text:
            # REFACTOR: [D4-2] 转义 LIKE 特殊字符
            escaped = search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("text_preview LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = self._execute(
            f"""
            SELECT * FROM generation_history
            {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """,
            (*params, limit, offset),
        )

        return [dict(row) for row in cursor.fetchall()]

    def count(self, engine: str = None, persona_name: str = None, search_text: str = None) -> int:
        """Count records matching the given filters."""
        conditions = []
        params: list = []

        if engine:
            conditions.append("engine = ?")
            params.append(engine)
        if persona_name:
            conditions.append("persona_name = ?")
            params.append(persona_name)
        if search_text:
            escaped = search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("text_preview LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = self._execute(
            f"""
            SELECT COUNT(*) as count FROM generation_history {where_clause}
        """,
            params,
        )
        return cursor.fetchone()["count"]

    # ------------------------------------------------------------------
    # 文件系统同步
    # ------------------------------------------------------------------

    def sync_from_filesystem(self, output_dir: str = None, since_mtime: float = 0.0):
        """Scan filesystem and sync missing records into the database.

        Only files with mtime > since_mtime are processed. Updates and returns
        the latest mtime seen during this sync (the high-water mark).

        H-R5: 批量插入走 insert_batch 分块。
        """
        import glob
        from datetime import datetime

        from .config import SAVE_DIR

        if output_dir is None:
            output_dir = SAVE_DIR

        # Get existing file paths efficiently
        existing_paths: set = set()
        cursor = self._execute("SELECT filepath FROM generation_history")
        for row in cursor.fetchall():
            existing_paths.add(row["filepath"])

        audio_extensions = {".wav", ".mp3", ".ogg", ".flac"}
        records_to_insert: list = []
        max_mtime = since_mtime

        for ext in audio_extensions:
            pattern = os.path.join(output_dir, f"*{ext}")
            for filepath in glob.glob(pattern):
                if filepath in existing_paths:
                    continue

                try:
                    filename = os.path.basename(filepath)
                    stat = os.stat(filepath)
                    if stat.st_mtime <= since_mtime:
                        continue

                    # Extract info from filename pattern: engine_type_text_timestamp.wav
                    text_preview = filename.rsplit(".", 1)[0][:_TEXT_PREVIEW_MAX_LENGTH]

                    record = {
                        "filename": filename,
                        "filepath": filepath,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "file_size_bytes": stat.st_size,
                        "text_preview": text_preview,
                        "engine": "unknown",
                        "output_format": ext.lstrip("."),
                        "is_success": True,
                        "is_degraded": False,
                        "tags": "",
                        "created_timestamp": stat.st_mtime,
                    }
                    records_to_insert.append(record)
                    if stat.st_mtime > max_mtime:
                        max_mtime = stat.st_mtime
                except Exception as e:
                    logger.debug(f"同步文件失败 {filepath}: {e}")

        # H-R5: insert_batch 内部已分块
        if records_to_insert:
            self.insert_batch(records_to_insert)
            logger.info(f"已从文件系统同步 {len(records_to_insert)} 个文件到历史记录数据库")

        if max_mtime > self.last_sync_mtime:
            self.last_sync_mtime = max_mtime
        return self.last_sync_mtime

    def cleanup_orphan_records(self, output_dir: str = None) -> int:
        """Mark records whose files no longer exist on disk as file_missing=1.

        Args:
            output_dir: Optional output directory (unused, kept for API compatibility).

        Returns:
            Count of orphaned records marked as file_missing.
        """
        cursor = self._execute(
            "SELECT id, filepath FROM generation_history WHERE filepath IS NOT NULL AND filepath != ''"
        )
        rows = cursor.fetchall()
        orphan_ids = []
        for row in rows:
            if not os.path.exists(row["filepath"]):
                orphan_ids.append(row["id"])

        if orphan_ids:
            # H-R5: 分块更新
            for chunk_start in range(0, len(orphan_ids), _CHUNK_SIZE):
                chunk = orphan_ids[chunk_start : chunk_start + _CHUNK_SIZE]
                placeholders = ",".join("?" * len(chunk))
                with self._transaction() as conn:
                    conn.execute(
                        f"UPDATE generation_history SET file_missing = 1 WHERE id IN ({placeholders})",
                        chunk,
                    )
            logger.info(f"已标记 {len(orphan_ids)} 条孤立记录为 file_missing")
        return len(orphan_ids)

    def validate_integrity(self) -> tuple:
        """Run PRAGMA integrity_check on the database.

        Returns:
            Tuple of (is_ok: bool, message: str).
        """
        try:
            cursor = self._execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            message = result[0] if result else "unknown"
            is_ok = message == "ok"
            return (is_ok, message)
        except sqlite3.DatabaseError as e:
            return (False, str(e))

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics about the history."""
        cursor = self._execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT engine) as engine_count,
                COUNT(DISTINCT persona_name) as persona_count,
                AVG(duration_seconds) as avg_duration,
                AVG(file_size_bytes) as avg_file_size
            FROM generation_history
        """)
        row = dict(cursor.fetchone())
        return {
            "total_records": row["total"],
            "unique_engines": row["engine_count"],
            "unique_personas": row["persona_count"],
            "avg_duration_seconds": round(row["avg_duration"] or 0, 2),
            "avg_file_size_bytes": round(row["avg_file_size"] or 0, 0),
        }

    def _migrate_from_json(self):
        """Migrate records from the old JSON-based HistoryManager storage.

        Reads data/history_records.json and inserts all records into SQLite,
        then renames the JSON file to .migrated.
        """
        from .config import PROJECT_ROOT

        json_path = os.path.join(PROJECT_ROOT, "data", "history_records.json")
        migrated_path = json_path + ".migrated"

        if not os.path.exists(json_path):
            return

        # Skip if already migrated
        if os.path.exists(migrated_path):
            return

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)

            if not data:
                # Empty JSON file, just rename
                os.rename(json_path, migrated_path)
                logger.info("空的 history_records.json 文件，已重命名为 .migrated")
                return

            records = []
            for filename, record_data in data.items():
                records.append(
                    {
                        "filename": record_data.get("filename", filename),
                        "filepath": record_data.get("filepath", ""),
                        "created_at": record_data.get("created_at", ""),
                        "file_size_bytes": record_data.get("file_size", 0),
                        "duration_seconds": record_data.get("duration_seconds", 0),
                        "text_preview": record_data.get("text_preview", ""),
                        "engine": record_data.get("engine", "unknown"),
                        "persona_name": record_data.get("persona_name"),
                        "hidden": record_data.get("hidden", False),
                        "created_timestamp": record_data.get("created_timestamp", 0),
                        "is_success": True,
                        "is_degraded": False,
                        "tags": "",
                    }
                )

            count = self.insert_batch(records)
            logger.info(f"已从 history_records.json 迁移 {count} 条记录到 SQLite")

            # Rename the JSON file to mark migration complete
            os.rename(json_path, migrated_path)
            logger.info(f"已将 {json_path} 重命名为 {migrated_path}")

        except Exception as e:
            logger.error(f"从 JSON 迁移失败: {e}")


# --- 单例管理 (H-R3 线程安全) ---
_history_db: HistoryDatabase | None = None
_singleton_lock = threading.Lock()  # H-R3: 保护单例创建


def get_history_db() -> HistoryDatabase:
    """Get the global HistoryDatabase instance.

    H-R3: 用 threading.Lock 保护单例创建，避免多线程并发首次调用创建多个实例。
    """
    global _history_db
    if _history_db is None:
        with _singleton_lock:
            # 双重检查，避免锁内重复创建
            if _history_db is None:
                from .config import SAVE_DIR

                db_dir = os.path.dirname(SAVE_DIR)
                db_path = os.path.join(db_dir, "data", "history.db")
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                _history_db = HistoryDatabase(db_path)
                # Run JSON migration on first initialization
                _history_db._migrate_from_json()
    return _history_db


def create_history_db(output_dir: str) -> HistoryDatabase:
    """Create and return a HistoryDatabase instance.

    工厂函数，用于创建不依赖全局状态的新实例（测试场景）。
    """
    db_path = os.path.join(output_dir, "history.db")
    return HistoryDatabase(db_path)


def close_all_connections() -> None:
    """REFACTOR: [H-R3] 模块级便捷函数，关闭全局单例的所有连接。

    在应用 shutdown 钩子中调用。
    """
    global _history_db
    if _history_db is not None:
        _history_db.close_all()
