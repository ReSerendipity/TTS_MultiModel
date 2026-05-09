# -*- coding: utf-8 -*-
"""SQLite-based history index for fast querying of generation records."""

import os
import sqlite3
import logging
import threading
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger("tts_multimodel")


class HistoryDatabase:
    """SQLite-based history index for efficient querying of generation records.
    
    Replaces slow glob-based filesystem scanning with indexed database queries.
    
    Performance features:
    - Thread-local connection pooling (avoids per-query connection overhead)
    - WAL mode for concurrent read/write access
    - Optimized PRAGMAs for query performance
    - Missing index on (engine, created_at) for filtered queries
    - Batch insert for filesystem sync
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._thread_local = threading.local()
        self._ensure_table()
        self._optimize_pragmas()
        self._ensure_indexes()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local cached connection. Creates one on first access per thread."""
        conn = getattr(self._thread_local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB page cache
            conn.execute("PRAGMA temp_store=MEMORY")
            self._thread_local.connection = conn
        return conn

    def close(self):
        """Close the thread-local connection if open."""
        conn = getattr(self._thread_local, "connection", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._thread_local.connection = None

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
                    tags TEXT DEFAULT ''
                )
            """)

    def _ensure_indexes(self):
        """Create missing indexes for common query patterns."""
        indexes = [
            ("idx_history_created_at", "generation_history(created_at DESC)"),
            ("idx_history_engine", "generation_history(engine)"),
            ("idx_history_persona", "generation_history(persona_name)"),
            ("idx_history_engine_created", "generation_history(engine, created_at DESC)"),
            ("idx_history_persona_created", "generation_history(persona_name, created_at DESC)"),
            ("idx_history_is_success", "generation_history(is_success)"),
            ("idx_history_filepath", "generation_history(filepath)"),
        ]
        with self._transaction() as conn:
            for name, columns in indexes:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {columns}")

    def _optimize_pragmas(self):
        """Set performance-oriented PRAGMAs for the database."""
        conn = self._get_connection()
        pragmas = {
            "journal_mode": "WAL",          # Better concurrent read/write performance
            "synchronous": "NORMAL",        # Good balance of safety and speed
            "cache_size": -64000,           # 64MB page cache (negative = KB)
            "temp_store": "MEMORY",         # Temp tables in memory
            "mmap_size": 268435456,         # 256MB memory-mapped I/O
            "optimize": 0,                  # Run deferred optimization
        }
        for pragma, value in pragmas.items():
            try:
                if isinstance(value, int) and value != 0:
                    conn.execute(f"PRAGMA {pragma}={value}")
                elif isinstance(value, str):
                    conn.execute(f"PRAGMA {pragma}={value}")
                elif value == 0:
                    conn.execute(f"PRAGMA {pragma}")
            except Exception:
                logger.debug(f"Failed to set PRAGMA {pragma}={value}")

    def insert(self, record: Dict[str, Any]) -> int:
        """Insert a generation record. Returns the record ID."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO generation_history 
                (filename, filepath, created_at, file_size_bytes, duration_seconds,
                 text_preview, engine, model_type, model_size, lang, persona_name,
                 output_format, temperature, seed, speed, is_success, error_msg, is_degraded, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
            ))
            return cursor.lastrowid

    def insert_batch(self, records: List[Dict[str, Any]]) -> int:
        """Insert multiple records in a single transaction. Returns count inserted."""
        if not records:
            return 0
        with self._transaction() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO generation_history 
                (filename, filepath, created_at, file_size_bytes, duration_seconds,
                 text_preview, engine, model_type, model_size, lang, persona_name,
                 output_format, temperature, seed, speed, is_success, error_msg, is_degraded, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r.get("filename", ""),
                    r.get("filepath", ""),
                    r.get("created_at", ""),
                    r.get("file_size_bytes", 0),
                    r.get("duration_seconds"),
                    r.get("text_preview", ""),
                    r.get("engine", "unknown"),
                    r.get("model_type"),
                    r.get("model_size"),
                    r.get("lang", "zh"),
                    r.get("persona_name"),
                    r.get("output_format", "wav"),
                    r.get("temperature", 0.9),
                    r.get("seed", 42),
                    r.get("speed", 1.0),
                    1 if r.get("is_success", True) else 0,
                    r.get("error_msg"),
                    1 if r.get("is_degraded", False) else 0,
                    r.get("tags", ""),
                )
                for r in records
            ])
            return len(records)

    def query(self, limit: int = 50, offset: int = 0, engine: str = None,
              persona_name: str = None, search_text: str = None,
              order_by: str = "created_at DESC") -> List[Dict[str, Any]]:
        """Query generation history with filters and pagination."""
        # Validate order_by against whitelist to prevent SQL injection
        _allowed_order_by = {
            "created_at DESC", "created_at ASC",
            "file_size_bytes DESC", "file_size_bytes ASC",
            "duration_seconds DESC", "duration_seconds ASC",
            "engine ASC", "engine DESC",
        }
        if order_by not in _allowed_order_by:
            order_by = "created_at DESC"

        conditions = []
        params: list = []

        if engine:
            conditions.append("engine = ?")
            params.append(engine)
        if persona_name:
            conditions.append("persona_name = ?")
            params.append(persona_name)
        if search_text:
            conditions.append("text_preview LIKE ?")
            params.append(f"%{search_text}%")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        cursor = self._execute(f"""
            SELECT * FROM generation_history
            {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """, (*params, limit, offset))
        
        return [dict(row) for row in cursor.fetchall()]

    def count(self, engine: str = None, persona_name: str = None,
              search_text: str = None) -> int:
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
            conditions.append("text_preview LIKE ?")
            params.append(f"%{search_text}%")

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        cursor = self._execute(f"""
            SELECT COUNT(*) as count FROM generation_history {where_clause}
        """, params)
        return cursor.fetchone()["count"]

    def sync_from_filesystem(self, output_dir: str):
        """Scan filesystem and sync missing records into the database.
        
        This is a one-time migration operation to populate the database
        from existing audio files.
        
        Optimizations:
        - Uses batch insert instead of per-file transactions
        - Pre-computes existing paths set for O(1) lookups
        """
        import glob
        from datetime import datetime

        # Get existing file paths efficiently
        existing_paths: set = set()
        cursor = self._execute("SELECT filepath FROM generation_history")
        for row in cursor.fetchall():
            existing_paths.add(row["filepath"])

        audio_extensions = {".wav", ".mp3", ".ogg", ".flac"}
        records_to_insert: list = []

        for ext in audio_extensions:
            pattern = os.path.join(output_dir, f"*{ext}")
            for filepath in glob.glob(pattern):
                if filepath in existing_paths:
                    continue

                try:
                    filename = os.path.basename(filepath)
                    stat = os.stat(filepath)
                    
                    # Extract info from filename pattern: engine_type_text_timestamp.wav
                    # This is a best-effort extraction
                    text_preview = filename.rsplit(".", 1)[0][:100]
                    
                    record = {
                        "filename": filename,
                        "filepath": filepath,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "file_size_bytes": stat.st_size,
                        "text_preview": text_preview,
                        "engine": "unknown",
                        "output_format": ext.lstrip("."),
                        "is_success": True,
                        "is_degraded": False,
                        "tags": "",
                    }
                    records_to_insert.append(record)
                except Exception as e:
                    logger.debug(f"Failed to sync file {filepath}: {e}")

        # Batch insert all records in a single transaction
        if records_to_insert:
            self.insert_batch(records_to_insert)
            logger.info(
                f"Synced {len(records_to_insert)} files from filesystem to history database"
            )
        return len(records_to_insert)

    def get_stats(self) -> Dict[str, Any]:
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


def create_history_db(output_dir: str) -> HistoryDatabase:
    """Create and return a HistoryDatabase instance."""
    db_path = os.path.join(output_dir, "history.db")
    return HistoryDatabase(db_path)
