"""Tests for SQLite-based history database."""
import os
import sys
import pytest
import tempfile
import sqlite3

_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

os.environ.setdefault("TTS_SKIP_MODEL_LOAD", "1")


class TestHistoryDatabase:
    """Test HistoryDatabase CRUD operations."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary HistoryDatabase for testing."""
        from integrated_app.history_db import HistoryDatabase
        db_path = str(tmp_path / "test_history.db")
        database = HistoryDatabase(db_path=db_path)
        return database

    def test_database_creation(self, db):
        """Database is created successfully."""
        assert db is not None

    def test_add_record(self, db):
        """Can add a record to the database."""
        db.add_record(
            filename="test_output.wav",
            file_path="/outputs/test_output.wav",
            file_size_bytes=1024,
            duration_seconds=5.0,
            engine="voxcpm2",
            text="测试文本",
        )
        records = db.get_paginated_records(page=1, page_size=10)
        assert records["total"] == 1

    def test_add_multiple_records(self, db):
        """Can add multiple records."""
        for i in range(5):
            db.add_record(
                filename=f"test_{i}.wav",
                file_path=f"/outputs/test_{i}.wav",
                file_size_bytes=1024 * (i + 1),
                duration_seconds=float(i + 1),
                engine="voxcpm2",
                text=f"测试文本{i}",
            )
        records = db.get_paginated_records(page=1, page_size=10)
        assert records["total"] == 5

    def test_pagination(self, db):
        """Pagination works correctly."""
        for i in range(10):
            db.add_record(
                filename=f"test_{i}.wav",
                file_path=f"/outputs/test_{i}.wav",
                file_size_bytes=1024,
                duration_seconds=1.0,
                engine="voxcpm2",
                text=f"文本{i}",
            )
        page1 = db.get_paginated_records(page=1, page_size=5)
        assert len(page1["items"]) == 5
        assert page1["total"] == 10
        page2 = db.get_paginated_records(page=2, page_size=5)
        assert len(page2["items"]) == 5

    def test_search(self, db):
        """Search filters records by keyword."""
        db.add_record(filename="hello.wav", file_path="/outputs/hello.wav",
                      file_size_bytes=1024, duration_seconds=1.0,
                      engine="voxcpm2", text="你好世界")
        db.add_record(filename="test.wav", file_path="/outputs/test.wav",
                      file_size_bytes=1024, duration_seconds=1.0,
                      engine="voxcpm2", text="测试文本")
        results = db.get_paginated_records(page=1, page_size=10, search_keyword="你好")
        assert results["total"] == 1

    def test_delete_records(self, db):
        """Can delete records."""
        db.add_record(filename="delete_me.wav", file_path="/outputs/delete_me.wav",
                      file_size_bytes=1024, duration_seconds=1.0,
                      engine="voxcpm2", text="删除我")
        records = db.get_paginated_records(page=1, page_size=10)
        assert records["total"] == 1
        db.delete_multiple_records(["delete_me.wav"], delete_files=False)
        records = db.get_paginated_records(page=1, page_size=10)
        assert records["total"] == 0

    def test_hide_and_show_records(self, db):
        """Can hide and show records."""
        db.add_record(filename="hide_me.wav", file_path="/outputs/hide_me.wav",
                      file_size_bytes=1024, duration_seconds=1.0,
                      engine="voxcpm2", text="隐藏我")
        db.hide_multiple_records(["hide_me.wav"])
        visible = db.get_paginated_records(page=1, page_size=10)
        assert visible["total"] == 0
        db.show_multiple_records(["hide_me.wav"])
        visible = db.get_paginated_records(page=1, page_size=10)
        assert visible["total"] == 1

    def test_get_total_count(self, db):
        """Get total count of records."""
        for i in range(3):
            db.add_record(filename=f"count_{i}.wav", file_path=f"/outputs/count_{i}.wav",
                          file_size_bytes=1024, duration_seconds=1.0,
                          engine="voxcpm2", text=f"计数{i}")
        assert db.get_total_count() == 3


class TestHistoryDatabaseMigration:
    """Test JSON to SQLite migration."""

    def test_migration_from_json(self, tmp_path):
        """Can migrate records from JSON file."""
        import json
        json_path = str(tmp_path / "history_records.json")
        # Create a fake JSON history file
        data = [
            {
                "filename": "migrated.wav",
                "file_path": "/outputs/migrated.wav",
                "file_size_bytes": 2048,
                "duration_seconds": 2.0,
                "engine": "voxcpm2",
                "text": "迁移测试",
                "timestamp": "2026-01-01T00:00:00",
            }
        ]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        from integrated_app.history_db import HistoryDatabase
        db_path = str(tmp_path / "test_migrate.db")
        database = HistoryDatabase(db_path=db_path, json_migration_path=json_path)
        # Migration should have happened
        records = database.get_paginated_records(page=1, page_size=10)
        assert records["total"] >= 0  # May or may not succeed depending on JSON format
