# -*- coding: utf-8 -*-
"""SQLite-based history index for fast querying of generation records."""

import os
import json
import sqlite3
import logging
import threading
import time
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger("tts_multimodel")


class HistoryDatabase:
    """SQLite-based history index for efficient querying of generation records.
    
    Replaces slow glob-based filesystem scanning and JSON-based HistoryManager
    with indexed database queries.
    
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
        self._migrate_add_hidden_column()
        self._migrate_add_created_timestamp_column()
        self._migrate_add_file_missing_column()
        self._optimize_pragmas()
        self._ensure_indexes()

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
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=-64000")  # 64MB page cache
                conn.execute("PRAGMA temp_store=MEMORY")
            except sqlite3.DatabaseError:
                logger.warning(f"Database corrupted: {self._db_path}, attempting auto-rebuild")
                # Close the failed connection if it was partially created
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                # Rename corrupted file and create a fresh database
                corrupted_path = f"{self._db_path}.corrupted"
                try:
                    if os.path.exists(self._db_path):
                        # Avoid overwriting existing .corrupted file
                        if os.path.exists(corrupted_path):
                            import shutil
                            corrupted_path = f"{self._db_path}.corrupted.{int(time.time())}"
                        os.rename(self._db_path, corrupted_path)
                        logger.warning(f"Renamed corrupted database to: {corrupted_path}")
                except OSError as e:
                    logger.error(f"Failed to rename corrupted database: {e}")
                # Create fresh connection
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=-64000")
                conn.execute("PRAGMA temp_store=MEMORY")
                # Re-run table and index creation for the fresh database
                self._ensure_table()
                self._ensure_indexes()
                logger.info("Successfully rebuilt database after corruption")
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
            logger.info("Migrated database: added 'hidden' column")

    def _migrate_add_created_timestamp_column(self):
        """Add 'created_timestamp' column if it doesn't exist (migration for existing DBs)."""
        try:
            cursor = self._execute("SELECT created_timestamp FROM generation_history LIMIT 1")
            cursor.fetchall()
        except sqlite3.OperationalError:
            with self._transaction() as conn:
                conn.execute("ALTER TABLE generation_history ADD COLUMN created_timestamp REAL NOT NULL DEFAULT 0")
            logger.info("Migrated database: added 'created_timestamp' column")

    def _migrate_add_file_missing_column(self):
        """Add 'file_missing' column if it doesn't exist (migration for existing DBs)."""
        try:
            cursor = self._execute("SELECT file_missing FROM generation_history LIMIT 1")
            cursor.fetchall()
        except sqlite3.OperationalError:
            with self._transaction() as conn:
                conn.execute("ALTER TABLE generation_history ADD COLUMN file_missing INTEGER NOT NULL DEFAULT 0")
            logger.info("Migrated database: added 'file_missing' column")

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
            ("idx_history_hidden", "generation_history(hidden)"),
            ("idx_history_created_timestamp", "generation_history(created_timestamp DESC)"),
            ("idx_history_file_missing", "generation_history(file_missing)"),
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

    def add_record(self, filename: str, filepath: str, created_at: str,
                   file_size: int, text_preview: str = "", engine: str = "unknown",
                   persona_name: Optional[str] = None, duration_seconds: float = 0.0) -> int:
        """Add a new history record. Returns the record ID."""
        timestamp = time.time()
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO generation_history 
                (filename, filepath, created_at, file_size_bytes, duration_seconds,
                 text_preview, engine, persona_name, hidden, created_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                filename,
                filepath,
                created_at,
                file_size,
                duration_seconds,
                text_preview,
                engine,
                persona_name,
                timestamp,
            ))
            return cursor.lastrowid

    def insert(self, record: Dict[str, Any]) -> int:
        """Insert a generation record. Returns the record ID."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO generation_history 
                (filename, filepath, created_at, file_size_bytes, duration_seconds,
                 text_preview, engine, model_type, model_size, lang, persona_name,
                 output_format, temperature, seed, speed, is_success, error_msg, is_degraded, tags,
                 hidden, created_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                1 if record.get("hidden", False) else 0,
                record.get("created_timestamp", time.time()),
            ))
            return cursor.lastrowid

    def insert_batch(self, records: List[Dict[str, Any]]) -> int:
        """Insert multiple records in a single transaction. Returns count inserted."""
        if not records:
            return 0
        now = time.time()
        with self._transaction() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO generation_history 
                (filename, filepath, created_at, file_size_bytes, duration_seconds,
                 text_preview, engine, model_type, model_size, lang, persona_name,
                 output_format, temperature, seed, speed, is_success, error_msg, is_degraded, tags,
                 hidden, created_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    1 if r.get("hidden", False) else 0,
                    r.get("created_timestamp", now),
                )
                for r in records
            ])
            return len(records)

    def get_paginated_records(self, limit: int = 20, offset: int = 0,
                              search_keyword: str = "", time_filter: str = "all",
                              include_hidden: bool = False,
                              include_missing: bool = False) -> Dict[str, Any]:
        """Get paginated history records with search and time filter.
        
        Returns dict with keys: items, total, loaded, hasMore
        where items is a list of dicts with keys: filename, created_at, file_size_bytes,
        duration_seconds, text_preview, engine, persona_name, hidden, created_timestamp
        """
        conditions = []
        params: list = []

        if not include_hidden:
            conditions.append("hidden = 0")

        if not include_missing:
            conditions.append("file_missing = 0")

        if search_keyword:
            kw_lower = search_keyword.lower()
            conditions.append("(LOWER(filename) LIKE ? OR LOWER(text_preview) LIKE ?)")
            params.extend([f"%{kw_lower}%", f"%{kw_lower}%"])

        # Time filter based on created_timestamp
        now = time.time()
        if time_filter == "today":
            conditions.append("created_timestamp > ?")
            params.append(now - 86400)
        elif time_filter == "week":
            conditions.append("created_timestamp > ?")
            params.append(now - 604800)
        elif time_filter == "month":
            conditions.append("created_timestamp > ?")
            params.append(now - 2592000)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Get total count
        cursor = self._execute(
            f"SELECT COUNT(*) as count FROM generation_history {where_clause}", params
        )
        total = cursor.fetchone()["count"]

        # Get paginated records
        cursor = self._execute(f"""
            SELECT * FROM generation_history
            {where_clause}
            ORDER BY created_timestamp DESC
            LIMIT ? OFFSET ?
        """, (*params, limit, offset))

        items = [dict(row) for row in cursor.fetchall()]
        loaded = offset + len(items)
        has_more = loaded < total

        return {
            "items": items,
            "total": total,
            "loaded": loaded,
            "hasMore": has_more,
        }

    def delete_multiple_records(self, filenames: List[str], delete_files: bool = False) -> int:
        """Delete multiple records by filename. Optionally delete actual files."""
        if not filenames:
            return 0
        count = 0
        with self._transaction() as conn:
            for filename in filenames:
                # Get filepath for file deletion
                if delete_files:
                    cursor = conn.execute(
                        "SELECT filepath FROM generation_history WHERE filename = ?",
                        (filename,)
                    )
                    row = cursor.fetchone()
                    if row and os.path.exists(row["filepath"]):
                        try:
                            os.remove(row["filepath"])
                            logger.debug(f"Deleted file: {row['filepath']}")
                        except Exception as e:
                            logger.error(f"Failed to delete file {row['filepath']}: {e}")

                cursor = conn.execute(
                    "DELETE FROM generation_history WHERE filename = ?", (filename,)
                )
                count += cursor.rowcount
        return count

    def hide_multiple_records(self, filenames: List[str]) -> int:
        """Hide multiple records by filename."""
        if not filenames:
            return 0
        count = 0
        with self._transaction() as conn:
            for filename in filenames:
                cursor = conn.execute(
                    "UPDATE generation_history SET hidden = 1 WHERE filename = ? AND hidden = 0",
                    (filename,)
                )
                count += cursor.rowcount
        return count

    def show_multiple_records(self, filenames: List[str]) -> int:
        """Show (unhide) multiple records by filename."""
        if not filenames:
            return 0
        count = 0
        with self._transaction() as conn:
            for filename in filenames:
                cursor = conn.execute(
                    "UPDATE generation_history SET hidden = 0 WHERE filename = ? AND hidden = 1",
                    (filename,)
                )
                count += cursor.rowcount
        return count

    def show_all_records(self) -> int:
        """Show all hidden records."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE generation_history SET hidden = 0 WHERE hidden = 1"
            )
            return cursor.rowcount

    def clear_all_records(self, hide_only: bool = True) -> int:
        """Clear all records. If hide_only=True, hide them; otherwise delete them."""
        if hide_only:
            with self._transaction() as conn:
                cursor = conn.execute(
                    "UPDATE generation_history SET hidden = 1 WHERE hidden = 0"
                )
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
            "created_timestamp DESC", "created_timestamp ASC",
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

    def sync_from_filesystem(self, output_dir: str = None):
        """Scan filesystem and sync missing records into the database.
        
        This is a one-time migration operation to populate the database
        from existing audio files.
        
        Optimizations:
        - Uses batch insert instead of per-file transactions
        - Pre-computes existing paths set for O(1) lookups
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
                        "created_timestamp": stat.st_mtime,
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
            with self._transaction() as conn:
                conn.executemany(
                    "UPDATE generation_history SET file_missing = 1 WHERE id = ?",
                    [(id_,) for id_ in orphan_ids]
                )
            logger.info(f"Marked {len(orphan_ids)} orphaned records as file_missing")
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
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not data:
                # Empty JSON file, just rename
                os.rename(json_path, migrated_path)
                logger.info("Empty history_records.json found, renamed to .migrated")
                return

            records = []
            for filename, record_data in data.items():
                records.append({
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
                })

            count = self.insert_batch(records)
            logger.info(f"Migrated {count} records from history_records.json to SQLite")

            # Rename the JSON file to mark migration complete
            os.rename(json_path, migrated_path)
            logger.info(f"Renamed {json_path} to {migrated_path}")

        except Exception as e:
            logger.error(f"Failed to migrate from JSON: {e}")


# Global singleton instance
_history_db: Optional[HistoryDatabase] = None


def get_history_db() -> HistoryDatabase:
    """Get the global HistoryDatabase instance."""
    global _history_db
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
    """Create and return a HistoryDatabase instance."""
    db_path = os.path.join(output_dir, "history.db")
    return HistoryDatabase(db_path)
