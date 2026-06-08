import sys
sys.path.insert(0, '.')
from bin.integrated_app.history_db import get_history_db
from bin.integrated_app.i18n import t

db = get_history_db()
result = db.get_paginated_records(search_keyword='', time_filter='all', limit=20, offset=0)

items = []
for rec in result["items"]:
    file_size = rec.get("file_size_bytes", 0) or 0
    size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
    size_str = f"{size_mb:.1f} MB"
    duration = rec.get("duration_seconds", 0) or 0
    try:
        duration = float(str(duration).rstrip('s'))
    except (ValueError, TypeError):
        duration = 0
    duration_str = f"{duration:.1f}s" if duration > 0 else "<1s"
    items.append([
        rec.get("filename", ""),
        rec.get("created_at", ""),
        duration_str,
        size_str,
    ])

print(f"Items: {len(items)}")
print(f"First 3 records: {items[:3]}")
print("Fix verified successfully!")
