# -*- coding: utf-8 -*-
"""
历史记录管理模块
实现历史记录的持久化存储、隐藏/显示机制
"""

import os
import json
import time
import logging
import glob
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from .config import SAVE_DIR, PROJECT_ROOT

logger = logging.getLogger("tts_multimodel")

# 历史记录存储文件路径
HISTORY_STORAGE_FILE = os.path.join(PROJECT_ROOT, "data", "history_records.json")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


@dataclass
class HistoryRecord:
    """历史记录数据结构"""
    filename: str
    filepath: str
    created_at: str
    file_size: int
    duration_seconds: float = 0.0
    text_preview: str = ""
    engine: str = "unknown"
    persona_name: Optional[str] = None
    hidden: bool = False
    created_timestamp: float = 0.0


class HistoryManager:
    """历史记录管理类"""
    
    def __init__(self):
        self._ensure_data_dir()
        self._records: Dict[str, HistoryRecord] = {}
        self._load_records()
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
    
    def _load_records(self):
        """从文件加载历史记录"""
        if os.path.exists(HISTORY_STORAGE_FILE):
            try:
                with open(HISTORY_STORAGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for filename, record_data in data.items():
                        self._records[filename] = HistoryRecord(**record_data)
                logger.info(f"Loaded {len(self._records)} history records from storage")
            except Exception as e:
                logger.error(f"Failed to load history records: {e}")
                self._records = {}
        else:
            logger.info("No history storage file found, initializing empty")
            self._records = {}
    
    def _save_records(self):
        """保存记录到文件"""
        try:
            data = {fn: asdict(rec) for fn, rec in self._records.items()}
            with open(HISTORY_STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved {len(self._records)} history records to storage")
        except Exception as e:
            logger.error(f"Failed to save history records: {e}")
    
    def add_record(self, filename: str, filepath: str, created_at: str, 
                   file_size: int, text_preview: str = "", engine: str = "unknown",
                   persona_name: Optional[str] = None, duration_seconds: float = 0.0):
        """添加一条新的历史记录"""
        timestamp = time.time()
        record = HistoryRecord(
            filename=filename,
            filepath=filepath,
            created_at=created_at,
            file_size=file_size,
            duration_seconds=duration_seconds,
            text_preview=text_preview,
            engine=engine,
            persona_name=persona_name,
            hidden=False,
            created_timestamp=timestamp
        )
        self._records[filename] = record
        self._save_records()
        logger.debug(f"Added history record: {filename}")
        return record
    
    def get_all_records(self, include_hidden: bool = False) -> List[HistoryRecord]:
        """获取所有历史记录"""
        records = list(self._records.values())
        if not include_hidden:
            records = [r for r in records if not r.hidden]
        # 按时间倒序排序
        records.sort(key=lambda x: x.created_timestamp, reverse=True)
        return records
    
    def hide_record(self, filename: str) -> bool:
        """隐藏一条记录（不删除文件）"""
        if filename in self._records:
            self._records[filename].hidden = True
            self._save_records()
            logger.debug(f"Hid history record: {filename}")
            return True
        return False
    
    def hide_multiple_records(self, filenames: List[str]) -> int:
        """隐藏多条记录"""
        count = 0
        for filename in filenames:
            if self.hide_record(filename):
                count += 1
        return count
    
    def show_record(self, filename: str) -> bool:
        """恢复显示一条记录"""
        if filename in self._records:
            self._records[filename].hidden = False
            self._save_records()
            logger.debug(f"Showed history record: {filename}")
            return True
        return False
    
    def show_multiple_records(self, filenames: List[str]) -> int:
        """批量恢复显示记录"""
        count = 0
        for filename in filenames:
            if self.show_record(filename):
                count += 1
        return count
    
    def show_all_records(self) -> int:
        """恢复显示所有被隐藏的记录"""
        count = 0
        for filename in self._records:
            if self._records[filename].hidden:
                self._records[filename].hidden = False
                count += 1
        if count > 0:
            self._save_records()
            logger.debug(f"Showed all {count} hidden history records")
        return count
    
    def delete_record(self, filename: str, delete_file: bool = False) -> bool:
        """彻底删除记录（可选删除实际文件）"""
        if filename in self._records:
            record = self._records[filename]
            if delete_file and os.path.exists(record.filepath):
                try:
                    os.remove(record.filepath)
                    logger.debug(f"Deleted file: {record.filepath}")
                except Exception as e:
                    logger.error(f"Failed to delete file {record.filepath}: {e}")
            
            del self._records[filename]
            self._save_records()
            logger.debug(f"Deleted history record: {filename}")
            return True
        return False
    
    def delete_multiple_records(self, filenames: List[str], delete_files: bool = False) -> int:
        """批量删除记录"""
        count = 0
        for filename in filenames:
            if self.delete_record(filename, delete_file=delete_files):
                count += 1
        return count
    
    def clear_all_records(self, hide_only: bool = True) -> int:
        """清除所有记录（默认只隐藏）"""
        if hide_only:
            count = 0
            for filename in self._records:
                self._records[filename].hidden = True
                count += 1
            self._save_records()
            logger.debug(f"Hid all {count} history records")
            return count
        else:
            count = len(self._records)
            self._records = {}
            self._save_records()
            logger.debug(f"Cleared all history records")
            return count
    
    def sync_from_filesystem(self):
        """从文件系统同步历史记录（添加缺失的记录）"""
        from .config import _AUDIO_EXTS
        from .utils import get_generation_history_enhanced
        
        # 获取当前文件系统中的记录
        current_files = []
        for ext in _AUDIO_EXTS:
            pattern = os.path.join(SAVE_DIR, f"*{ext}")
            current_files.extend(os.path.basename(f) for f in list(glob.glob(pattern)))
        
        # 添加缺失的记录
        added_count = 0
        existing_filenames = set(self._records.keys())
        
        for file_record in get_generation_history_enhanced():
            if file_record.get("basename") not in existing_filenames:
                basename = file_record.get("basename", "")
                filepath = file_record.get("path", "")
                created_at = file_record.get("time", "")
                file_size = 0
                if filepath and os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                
                self.add_record(
                    filename=basename,
                    filepath=filepath,
                    created_at=created_at,
                    file_size=file_size,
                    text_preview=basename,
                    duration_seconds=file_record.get("duration", 0)
                )
                added_count += 1
        
        logger.info(f"Synced {added_count} new records from filesystem")
        return added_count
    
    def get_paginated_records(self, limit: int = 20, offset: int = 0, 
                              search_keyword: str = "", time_filter: str = "all",
                              include_hidden: bool = False) -> Dict[str, Any]:
        """获取分页历史记录"""
        all_records = self.get_all_records(include_hidden=include_hidden)
        
        # 应用搜索过滤
        filtered_records = all_records
        if search_keyword:
            kw_lower = search_keyword.lower()
            filtered_records = [
                r for r in filtered_records 
                if kw_lower in r.filename.lower() or kw_lower in r.text_preview.lower()
            ]
        
        # 应用时间过滤
        now = time.time()
        if time_filter == "today":
            filtered_records = [
                r for r in filtered_records 
                if now - r.created_timestamp < 86400
            ]
        elif time_filter == "week":
            filtered_records = [
                r for r in filtered_records 
                if now - r.created_timestamp < 604800
            ]
        elif time_filter == "month":
            filtered_records = [
                r for r in filtered_records 
                if now - r.created_timestamp < 2592000
            ]
        
        # 分页
        total = len(filtered_records)
        end = offset + limit
        page_records = filtered_records[offset:end]
        loaded = offset + len(page_records)
        has_more = loaded < total
        
        return {
            "items": page_records,
            "total": total,
            "loaded": loaded,
            "hasMore": has_more
        }
    
    def get_total_count(self, include_hidden: bool = False) -> int:
        """获取记录总数"""
        if include_hidden:
            return len(self._records)
        return sum(1 for r in self._records.values() if not r.hidden)


# 全局单例实例
_history_manager: Optional[HistoryManager] = None


def get_history_manager() -> HistoryManager:
    """获取历史记录管理器实例"""
    global _history_manager
    if _history_manager is None:
        _history_manager = HistoryManager()
    return _history_manager



