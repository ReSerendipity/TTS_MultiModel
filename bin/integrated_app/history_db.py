# -*- coding: utf-8 -*-
"""SQLite-based history index for fast querying of generation records."""

import os
import sqlite3
import logging
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger("tts_multimodel")


class HistoryDatabase:
    """SQLite-based history index for efficient querying of generation records.
    
    Replaces slow glob-based filesystem scanning with indexed database queries.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._ensure_table()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_table(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_created_at 
                ON generation_history(created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_engine 
                ON generation_history(engine)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_persona 
                ON generation_history(persona_name)
            """)

    def insert(self, record: Dict[str, Any]) -> int:
        """Insert a generation record. Returns the record ID."""
        with self._connection() as conn:
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
        params = []

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
        
        with self._connection() as conn:
            cursor = conn.execute(f"""
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
        params = []

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
        
        with self._connection() as conn:
            cursor = conn.execute(f"""
                SELECT COUNT(*) as count FROM generation_history {where_clause}
            """, params)
            return cursor.fetchone()["count"]

    def sync_from_filesystem(self, output_dir: str):
        """Scan filesystem and sync missing records into the database.
        
        This is a one-time migration operation to populate the database
        from existing audio files.
        """
        import glob
        import re

        existing_paths = set()
        with self._connection() as conn:
            for row in conn.execute("SELECT filepath FROM generation_history"):
                existing_paths.add(row["filepath"])

        audio_extensions = {".wav", ".mp3", ".ogg", ".flac"}
        count = 0

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
                        "created_at": "",  # Would need to extract from filename or use mtime
                        "file_size_bytes": stat.st_size,
                        "text_preview": text_preview,
                        "engine": "unknown",
                        "output_format": ext.lstrip("."),
                    }
                    self.insert(record)
                    count += 1
                except Exception as e:
                    logger.debug(f"Failed to sync file {filepath}: {e}")

        if count > 0:
            logger.info(f"Synced {count} files from filesystem to history database")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics about the history."""
        with self._connection() as conn:
            cursor = conn.execute("""
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
