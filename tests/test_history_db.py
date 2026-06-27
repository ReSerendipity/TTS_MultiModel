"""Tests for SQLite-based history database."""
import os
import sys

import pytest

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
            filepath="/outputs/test_output.wav",
            created_at="2026-01-01T00:00:00",
            file_size=1024,
            duration_seconds=5.0,
            engine="voxcpm2",
            text_preview="测试文本",
        )
        records = db.get_paginated_records(limit=10, offset=0)
        assert records["total"] == 1

    def test_add_multiple_records(self, db):
        """Can add multiple records."""
        for i in range(5):
            db.add_record(
                filename=f"test_{i}.wav",
                filepath=f"/outputs/test_{i}.wav",
                created_at="2026-01-01T00:00:00",
                file_size=1024 * (i + 1),
                duration_seconds=float(i + 1),
                engine="voxcpm2",
                text_preview=f"测试文本{i}",
            )
        records = db.get_paginated_records(limit=10, offset=0)
        assert records["total"] == 5

    def test_pagination(self, db):
        """Pagination works correctly."""
        for i in range(10):
            db.add_record(
                filename=f"test_{i}.wav",
                filepath=f"/outputs/test_{i}.wav",
                created_at="2026-01-01T00:00:00",
                file_size=1024,
                duration_seconds=1.0,
                engine="voxcpm2",
                text_preview=f"文本{i}",
            )
        page1 = db.get_paginated_records(limit=5, offset=0)
        assert len(page1["items"]) == 5
        assert page1["total"] == 10
        page2 = db.get_paginated_records(limit=5, offset=5)
        assert len(page2["items"]) == 5

    def test_search(self, db):
        """Search filters records by keyword."""
        db.add_record(filename="hello.wav", filepath="/outputs/hello.wav",
                      created_at="2026-01-01T00:00:00",
                      file_size=1024, duration_seconds=1.0,
                      engine="voxcpm2", text_preview="你好世界")
        db.add_record(filename="test.wav", filepath="/outputs/test.wav",
                      created_at="2026-01-01T00:00:00",
                      file_size=1024, duration_seconds=1.0,
                      engine="voxcpm2", text_preview="测试文本")
        results = db.get_paginated_records(limit=10, offset=0, search_keyword="你好")
        assert results["total"] == 1

    def test_delete_records(self, db):
        """Can delete records."""
        db.add_record(filename="delete_me.wav", filepath="/outputs/delete_me.wav",
                      created_at="2026-01-01T00:00:00",
                      file_size=1024, duration_seconds=1.0,
                      engine="voxcpm2", text_preview="删除我")
        records = db.get_paginated_records(limit=10, offset=0)
        assert records["total"] == 1
        db.delete_multiple_records(["delete_me.wav"], delete_files=False)
        records = db.get_paginated_records(limit=10, offset=0)
        assert records["total"] == 0

    def test_hide_and_show_records(self, db):
        """Can hide and show records."""
        db.add_record(filename="hide_me.wav", filepath="/outputs/hide_me.wav",
                      created_at="2026-01-01T00:00:00",
                      file_size=1024, duration_seconds=1.0,
                      engine="voxcpm2", text_preview="隐藏我")
        db.hide_multiple_records(["hide_me.wav"])
        visible = db.get_paginated_records(limit=10, offset=0)
        assert visible["total"] == 0
        db.show_multiple_records(["hide_me.wav"])
        visible = db.get_paginated_records(limit=10, offset=0)
        assert visible["total"] == 1

    def test_get_total_count(self, db):
        """Get total count of records."""
        for i in range(3):
            db.add_record(filename=f"count_{i}.wav", filepath=f"/outputs/count_{i}.wav",
                          created_at="2026-01-01T00:00:00",
                          file_size=1024, duration_seconds=1.0,
                          engine="voxcpm2", text_preview=f"计数{i}")
        assert db.get_total_count() == 3

    def test_batch_delete_100_records(self, db):
        """Batch delete 100 records with a single IN (...) query."""
        filenames = []
        for i in range(100):
            name = f"batch_{i}.wav"
            filenames.append(name)
            db.add_record(
                filename=name,
                filepath=f"/outputs/{name}",
                created_at="2026-01-01T00:00:00",
                file_size=1024,
                duration_seconds=1.0,
                engine="voxcpm2",
                text_preview=f"批量{i}",
            )
        assert db.get_total_count() == 100
        deleted = db.delete_multiple_records(filenames, delete_files=False)
        assert deleted == 100
        assert db.get_total_count() == 0

    def test_batch_hide_and_show_records(self, db):
        """Batch hide and show multiple records via IN (...) query."""
        filenames = [f"batch_hide_{i}.wav" for i in range(10)]
        for name in filenames:
            db.add_record(
                filename=name,
                filepath=f"/outputs/{name}",
                created_at="2026-01-01T00:00:00",
                file_size=1024,
                duration_seconds=1.0,
                engine="voxcpm2",
                text_preview="批量隐藏",
            )
        hidden = db.hide_multiple_records(filenames)
        assert hidden == 10
        assert db.get_total_count() == 0
        shown = db.show_multiple_records(filenames)
        assert shown == 10
        assert db.get_total_count() == 10

    def test_insert_and_query(self, db):
        """insert() stores a full record and query() retrieves it."""
        record_id = db.insert({
            "filename": "inserted.wav",
            "filepath": "/outputs/inserted.wav",
            "created_at": "2026-01-01T00:00:00",
            "file_size_bytes": 4096,
            "duration_seconds": 3.5,
            "text_preview": "插入测试",
            "engine": "indextts2",
            "persona_name": "test_persona",
        })
        assert record_id > 0
        rows = db.query(engine="indextts2", search_text="插入")
        assert len(rows) == 1
        assert rows[0]["filename"] == "inserted.wav"

    def test_count_and_stats(self, db):
        """count() and get_stats() return aggregate information."""
        for i in range(3):
            db.add_record(
                filename=f"stat_{i}.wav",
                filepath=f"/outputs/stat_{i}.wav",
                created_at="2026-01-01T00:00:00",
                file_size=1024,
                duration_seconds=2.0,
                engine="voxcpm2",
                text_preview=f"统计{i}",
            )
        assert db.count(engine="voxcpm2") == 3
        stats = db.get_stats()
        assert stats["total_records"] == 3
        assert stats["unique_engines"] == 1

    def test_validate_integrity(self, db):
        """PRAGMA integrity_check reports the database as ok."""
        is_ok, message = db.validate_integrity()
        assert is_ok is True
        assert message == "ok"


class TestHistoryDatabaseMigration:
    """Test JSON to SQLite migration."""

    def test_migration_from_json(self, tmp_path):
        """Can migrate records from JSON file via insert_batch."""
        import json
        json_path = str(tmp_path / "history_records.json")
        # Create a fake JSON history file
        data = [
            {
                "filename": "migrated.wav",
                "filepath": "/outputs/migrated.wav",
                "file_size_bytes": 2048,
                "duration_seconds": 2.0,
                "engine": "voxcpm2",
                "text_preview": "迁移测试",
                "created_at": "2026-01-01T00:00:00",
            }
        ]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        from integrated_app.history_db import HistoryDatabase
        db_path = str(tmp_path / "test_migrate.db")
        database = HistoryDatabase(db_path=db_path)
        # Simulate JSON migration by loading and inserting records
        with open(json_path, encoding="utf-8") as f:
            records = json.load(f)
        database.insert_batch(records)
        # Migration should have happened
        result = database.get_paginated_records(limit=10, offset=0)
        assert result["total"] == 1
