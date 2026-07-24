# -*- coding: utf-8 -*-
"""生成版本管理与崩溃恢复模块 (Chapter 10)。

提供三大核心能力：
1. GenerationVersionManager — 生成历史版本链追踪（original -> version-2 -> take-N）
2. CrashRecoveryManager — 启动时崩溃状态检测与恢复
3. LoRAHotSwapper — LoRA 权重热切换（无需全量模型重载）

设计要点：
- SQLite 持久化复用 history_db.py 的连接管理模式（线程本地 + 全局 set 追踪）
- 崩溃状态使用简单 JSON 文件，避免与主数据库耦合
- LoRA 热切换基于 VoxCPM buffer-based scaling 的 fill_() 原地修改
- 所有日志统一使用 logging.getLogger("tts_multimodel")
"""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("tts_multimodel")

# --- 常量 ---
_CRASH_STATE_FILE = "crash_recovery_state.json"
_VERSION_DB_NAME = "generation_versions.db"
_VRAM_USAGE_PERCENT_THRESHOLD = 90  # 显存熔断阈值（百分比）

# SQLite PRAGMA 配置（与 history_db.py 保持一致）
_PRAGMA_CONFIG = {
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    "cache_size": -32000,
    "temp_store": "MEMORY",
    "busy_timeout": 5000,
}


# ======================================================================
# 数据类
# ======================================================================


@dataclass
class GenerationRecord:
    """单次生成记录的数据类。

    Attributes:
        id: 生成记录唯一标识（UUID 字符串）。
        parent_id: 父版本 ID，首次生成时为 None。
        audio_path: 生成音频文件的绝对路径。
        text: 输入文本。
        params: 生成参数字典（cfg/timesteps/seed 等）。
        engine: 使用的引擎名称（如 "voxcpm2" / "indextts2"）。
        timestamp: 记录创建时间（Unix 时间戳）。
        version_label: 版本标签（如 "original" / "version-2" / "take-3"）。
    """

    id: str = ""
    parent_id: str | None = None
    audio_path: str = ""
    text: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    engine: str = ""
    timestamp: float = 0.0
    version_label: str = "original"

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典。"""
        result = asdict(self)
        result["params"] = dict(result.get("params", {}))
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerationRecord":
        """从字典构建 GenerationRecord 实例。"""
        return cls(
            id=data.get("id", ""),
            parent_id=data.get("parent_id"),
            audio_path=data.get("audio_path", ""),
            text=data.get("text", ""),
            params=data.get("params", {}),
            engine=data.get("engine", ""),
            timestamp=data.get("timestamp", 0.0),
            version_label=data.get("version_label", "original"),
        )


@dataclass
class CrashGenerationState:
    """崩溃恢复用的生成中间状态。

    Attributes:
        task_id: 生成任务 ID。
        state: 当前状态（"running" / "completed" / "failed"）。
        audio_path: 目标音频输出路径（可能为部分文件）。
        engine: 使用的引擎名称。
        started_at: 任务开始时间戳。
        params: 生成参数。
    """

    task_id: str = ""
    state: str = "running"
    audio_path: str = ""
    engine: str = ""
    started_at: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)


# ======================================================================
# GenerationVersionManager — 生成版本链追踪
# ======================================================================


class GenerationVersionManager:
    """生成历史版本链追踪管理器。

    追踪同一源文本的多次生成，形成版本链：
        original -> version-2 -> version-3 -> ... -> take-N

    使用 SQLite 持久化，复用 history_db.py 的线程本地连接模式。

    Usage::

        vm = GenerationVersionManager(db_dir="/path/to/data")
        gen_id = vm.save_generation(
            audio_path="/out/audio.wav",
            text="你好世界",
            params={"cfg": 2.0},
            engine="voxcpm2",
        )
        chain = vm.get_version_chain(gen_id)
        latest = vm.get_latest(gen_id)
    """

    def __init__(self, db_dir: str):
        """初始化版本管理器。

        Args:
            db_dir: 数据库文件所在目录。
        """
        self._db_dir = db_dir
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, _VERSION_DB_NAME)
        self._thread_local = threading.local()
        self._all_connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.Lock()
        self._ensure_table()
        self._ensure_indexes()

    # ------------------------------------------------------------------
    # 连接管理（与 history_db.py 模式一致）
    # ------------------------------------------------------------------

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """统一应用 PRAGMA 配置。"""
        for pragma, value in _PRAGMA_CONFIG.items():
            try:
                conn.execute(f"PRAGMA {pragma}={value}")
            except sqlite3.DatabaseError as e:
                logger.debug(f"设置 PRAGMA {pragma}={value} 失败: {e}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地缓存连接。"""
        conn = getattr(self._thread_local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            self._apply_pragmas(conn)
            with self._connections_lock:
                self._all_connections.add(conn)
            self._thread_local.connection = conn
        return conn

    def close(self) -> None:
        """关闭当前线程的连接。"""
        conn = getattr(self._thread_local, "connection", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            with self._connections_lock:
                self._all_connections.discard(conn)
            self._thread_local.connection = None

    def close_all(self) -> None:
        """关闭所有线程的连接。"""
        with self._connections_lock:
            for conn in list(self._all_connections):
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_connections.clear()
        self._thread_local.connection = None
        logger.info("[GenerationVersionManager] 已关闭所有线程连接")

    @contextmanager
    def _transaction(self):
        """事务上下文管理器。"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _execute(self, sql: str, params=()):
        """执行查询（只读操作）。"""
        conn = self._get_connection()
        return conn.execute(sql, params)

    # ------------------------------------------------------------------
    # Schema 与索引
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """创建 generation_versions 表。"""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_versions (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    audio_path TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL DEFAULT '',
                    params_json TEXT NOT NULL DEFAULT '{}',
                    engine TEXT NOT NULL DEFAULT '',
                    timestamp REAL NOT NULL DEFAULT 0,
                    version_label TEXT NOT NULL DEFAULT 'original'
                )
            """)

    def _ensure_indexes(self) -> None:
        """创建常用查询索引。"""
        indexes = [
            ("idx_gv_parent_id", "generation_versions(parent_id)"),
            ("idx_gv_engine", "generation_versions(engine)"),
            ("idx_gv_timestamp", "generation_versions(timestamp DESC)"),
        ]
        with self._transaction() as conn:
            for name, columns in indexes:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {columns}")

    # ------------------------------------------------------------------
    # 版本标签构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_version_label(parent_id: str | None, existing_count: int) -> str:
        """根据父版本和已有版本数量构建版本标签。

        Args:
            parent_id: 父版本 ID（首次生成时为 None）。
            existing_count: 同一链中已有版本数量。

        Returns:
            版本标签字符串。
        """
        if parent_id is None:
            return "original"
        version_num = existing_count + 1
        if version_num <= 10:
            return f"version-{version_num}"
        return f"take-{version_num}"

    def _count_chain_versions(self, root_id: str) -> int:
        """统计以 root_id 为根的版本链中所有记录数。"""
        cursor = self._execute(
            "SELECT COUNT(*) as cnt FROM generation_versions WHERE id = ? OR parent_id = ?",
            (root_id, root_id),
        )
        row = cursor.fetchone()
        return row["cnt"] if row else 0

    def _find_root_id(self, generation_id: str) -> str:
        """沿 parent_id 向上回溯找到版本链的根 ID。"""
        current_id = generation_id
        visited: set[str] = set()
        while True:
            if current_id in visited:
                logger.warning(f"[GenerationVersionManager] 检测到循环引用: {current_id}")
                break
            visited.add(current_id)
            cursor = self._execute(
                "SELECT parent_id FROM generation_versions WHERE id = ?",
                (current_id,),
            )
            row = cursor.fetchone()
            if row is None or row["parent_id"] is None:
                break
            current_id = row["parent_id"]
        return current_id

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def save_generation(
        self,
        audio_path: str,
        text: str,
        params: dict[str, Any],
        engine: str,
        parent_id: str | None = None,
    ) -> str:
        """保存生成记录并返回生成 ID。

        当 parent_id 为 None 时，创建版本链的起始节点（label="original"）。
        当 parent_id 指向已有记录时，创建该链的新版本节点。

        Args:
            audio_path: 生成音频文件的路径。
            text: 输入文本。
            params: 生成参数字典。
            engine: 引擎名称。
            parent_id: 父版本 ID，首次生成时为 None。

        Returns:
            新创建的生成记录 ID（UUID 字符串）。
        """
        gen_id = str(uuid.uuid4())
        timestamp = time.time()

        if parent_id is None:
            version_label = "original"
        else:
            root_id = self._find_root_id(parent_id)
            existing_count = self._count_chain_versions(root_id)
            version_label = self._build_version_label(parent_id, existing_count)

        params_json = json.dumps(params, ensure_ascii=False)

        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO generation_versions
                   (id, parent_id, audio_path, text, params_json, engine, timestamp, version_label)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (gen_id, parent_id, audio_path, text, params_json, engine, timestamp, version_label),
            )

        logger.info(
            f"[GenerationVersionManager] 已保存生成记录: id={gen_id[:8]}..., "
            f"label={version_label}, engine={engine}"
        )
        return gen_id

    def get_version_chain(self, generation_id: str) -> list[GenerationRecord]:
        """获取指定生成记录所在版本链的完整列表。

        从链的根节点开始，按 timestamp 排序返回所有版本。

        Args:
            generation_id: 生成记录 ID（链中任意一个即可）。

        Returns:
            从根到最新的 GenerationRecord 列表。空列表表示未找到记录。
        """
        root_id = self._find_root_id(generation_id)

        # 递归收集所有后代节点
        chain_ids: set[str] = {root_id}
        frontier = [root_id]
        while frontier:
            next_frontier = []
            placeholders = ",".join("?" * len(frontier))
            cursor = self._execute(
                f"SELECT id FROM generation_versions WHERE parent_id IN ({placeholders})",
                frontier,
            )
            for row in cursor.fetchall():
                if row["id"] not in chain_ids:
                    chain_ids.add(row["id"])
                    next_frontier.append(row["id"])
            frontier = next_frontier

        # 按 timestamp 排序读取完整记录
        placeholders = ",".join("?" * len(chain_ids))
        cursor = self._execute(
            f"""SELECT id, parent_id, audio_path, text, params_json, engine, timestamp, version_label
                FROM generation_versions
                WHERE id IN ({placeholders})
                ORDER BY timestamp ASC""",
            list(chain_ids),
        )

        records = []
        for row in cursor.fetchall():
            record = GenerationRecord(
                id=row["id"],
                parent_id=row["parent_id"],
                audio_path=row["audio_path"],
                text=row["text"],
                params=json.loads(row["params_json"]) if row["params_json"] else {},
                engine=row["engine"],
                timestamp=row["timestamp"],
                version_label=row["version_label"],
            )
            records.append(record)

        return records

    def get_latest(self, generation_id: str) -> GenerationRecord | None:
        """获取指定生成记录所在版本链的最新版本。

        Args:
            generation_id: 生成记录 ID（链中任意一个即可）。

        Returns:
            最新版本的 GenerationRecord，若链为空则返回 None。
        """
        chain = self.get_version_chain(generation_id)
        return chain[-1] if chain else None

    def get_record(self, generation_id: str) -> GenerationRecord | None:
        """获取单个生成记录。

        Args:
            generation_id: 生成记录 ID。

        Returns:
            对应的 GenerationRecord，若不存在则返回 None。
        """
        cursor = self._execute(
            """SELECT id, parent_id, audio_path, text, params_json, engine, timestamp, version_label
               FROM generation_versions WHERE id = ?""",
            (generation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return GenerationRecord(
            id=row["id"],
            parent_id=row["parent_id"],
            audio_path=row["audio_path"],
            text=row["text"],
            params=json.loads(row["params_json"]) if row["params_json"] else {},
            engine=row["engine"],
            timestamp=row["timestamp"],
            version_label=row["version_label"],
        )

    def delete_chain(self, generation_id: str, delete_files: bool = False) -> int:
        """删除指定生成记录所在版本链的全部记录。

        Args:
            generation_id: 链中任意一个生成记录 ID。
            delete_files: 是否同时删除磁盘上的音频文件。

        Returns:
            删除的记录数量。
        """
        chain = self.get_version_chain(generation_id)
        if not chain:
            return 0

        ids = [r.id for r in chain]
        file_paths = [r.audio_path for r in chain if r.audio_path] if delete_files else []

        placeholders = ",".join("?" * len(ids))
        with self._transaction() as conn:
            conn.execute(
                f"DELETE FROM generation_versions WHERE id IN ({placeholders})", ids
            )

        # 事务成功后删除文件
        if file_paths:
            for fp in file_paths:
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except OSError as e:
                        logger.error(f"[GenerationVersionManager] 删除文件失败 {fp}: {e}")

        logger.info(
            f"[GenerationVersionManager] 已删除版本链: {len(ids)} 条记录"
        )
        return len(ids)


# ======================================================================
# CrashRecoveryManager — 崩溃恢复管理器
# ======================================================================


class CrashRecoveryManager:
    """崩溃恢复管理器。

    在应用启动时检测上次会话中未完成的生成任务，
    将其标记为 "failed" 并清理残留的部分文件。

    崩溃状态使用简单的 JSON 文件持久化（与主数据库解耦，
    避免数据库事务未提交时丢失状态）。

    Usage::

        crm = CrashRecoveryManager(state_dir="/path/to/data")
        crm.check_and_recover()  # 启动时调用
        crm.save_generation_state("task-123", state)  # 生成前保存
        crm.clear_generation_state("task-123")  # 完成后清理
    """

    def __init__(self, state_dir: str):
        """初始化崩溃恢复管理器。

        Args:
            state_dir: 崩溃状态文件所在目录。
        """
        self._state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self._state_file = os.path.join(state_dir, _CRASH_STATE_FILE)
        self._lock = threading.Lock()

    def _read_state(self) -> dict[str, Any]:
        """读取崩溃状态文件。

        Returns:
            状态字典，键为 task_id，值为 CrashGenerationState 的字典表示。
            文件不存在或解析失败时返回空字典。
        """
        if not os.path.exists(self._state_file):
            return {}
        try:
            with open(self._state_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[CrashRecoveryManager] 读取崩溃状态文件失败: {e}")
            return {}

    def _write_state(self, state: dict[str, Any]) -> None:
        """写入崩溃状态文件。

        Args:
            state: 完整的状态字典。
        """
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"[CrashRecoveryManager] 写入崩溃状态文件失败: {e}")

    def save_generation_state(
        self,
        task_id: str,
        audio_path: str = "",
        engine: str = "",
        params: dict[str, Any] | None = None,
    ) -> None:
        """保存正在进行的生成任务状态。

        在生成开始前调用，记录任务信息以便崩溃后恢复。

        Args:
            task_id: 生成任务 ID。
            audio_path: 目标音频输出路径。
            engine: 使用的引擎名称。
            params: 生成参数。
        """
        state_entry = CrashGenerationState(
            task_id=task_id,
            state="running",
            audio_path=audio_path,
            engine=engine,
            started_at=time.time(),
            params=params or {},
        )

        with self._lock:
            state = self._read_state()
            state[task_id] = asdict(state_entry)
            self._write_state(state)

        logger.debug(f"[CrashRecoveryManager] 已保存生成状态: task_id={task_id}")

    def clear_generation_state(self, task_id: str) -> None:
        """清除已完成的生成任务状态。

        在生成成功完成后调用，从崩溃状态文件中移除该任务。

        Args:
            task_id: 生成任务 ID。
        """
        with self._lock:
            state = self._read_state()
            if task_id in state:
                del state[task_id]
                self._write_state(state)
                logger.debug(f"[CrashRecoveryManager] 已清除生成状态: task_id={task_id}")

    def mark_generation_failed(self, task_id: str) -> None:
        """将生成任务标记为失败。

        Args:
            task_id: 生成任务 ID。
        """
        with self._lock:
            state = self._read_state()
            if task_id in state:
                state[task_id]["state"] = "failed"
                self._write_state(state)
                logger.info(f"[CrashRecoveryManager] 已标记任务为失败: task_id={task_id}")

    def check_and_recover(self) -> list[str]:
        """启动时检测并恢复未完成的生成状态。

        扫描崩溃状态文件中所有 state="running" 的任务，
        将其标记为 "failed"，清理部分文件，并从状态文件中移除。

        Returns:
            恢复的任务 ID 列表。
        """
        recovered: list[str] = []

        with self._lock:
            state = self._read_state()
            if not state:
                return recovered

            tasks_to_recover = [
                tid for tid, entry in state.items()
                if isinstance(entry, dict) and entry.get("state") == "running"
            ]

            for task_id in tasks_to_recover:
                entry = state[task_id]
                audio_path = entry.get("audio_path", "")
                engine = entry.get("engine", "")
                started_at = entry.get("started_at", 0)

                # 清理部分文件
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                        logger.info(
                            f"[CrashRecoveryManager] 已清理部分文件: {audio_path}"
                        )
                    except OSError as e:
                        logger.error(
                            f"[CrashRecoveryManager] 清理部分文件失败 {audio_path}: {e}"
                        )

                elapsed = time.time() - started_at if started_at else 0
                logger.warning(
                    f"[CrashRecoveryManager] 检测到崩溃任务: task_id={task_id}, "
                    f"engine={engine}, 已运行 {elapsed:.1f}s，已标记为失败并清理"
                )

                # 从状态文件中移除
                del state[task_id]
                recovered.append(task_id)

            if tasks_to_recover:
                self._write_state(state)

        if recovered:
            logger.info(
                f"[CrashRecoveryManager] 崩溃恢复完成: 共恢复 {len(recovered)} 个任务"
            )

        return recovered


# ======================================================================
# LoRAHotSwapper — LoRA 权重热切换
# ======================================================================


class LoRAHotSwapper:
    """LoRA 权重热切换管理器。

    允许在不完全重载模型的情况下，启用/禁用/切换 LoRA 权重。
    基于 VoxCPM buffer-based scaling 模式：
    - 使用 fill_() 进行原地缩放因子修改，减少显存分配
    - 维护活跃 LoRA 名称和可用 LoRA 列表

    Usage::

        swapper = LoRAHotSwapper()
        available = swapper.list_available_loras()
        ok = swapper.swap_lora("my_voice_lora")
        active = swapper.get_active_lora()
    """

    def __init__(self):
        self._active_lora: str | None = None
        self._lock = threading.Lock()

    def _get_lora_dir(self) -> str:
        """获取 LoRA 目录路径（延迟导入 config）。"""
        from .config import LORA_DIR
        return LORA_DIR

    def _get_model(self):
        """获取当前 VoxCPM2 模型实例（延迟导入 registry）。"""
        from .model_registry import registry
        return registry.voxcpm_model

    def swap_lora(self, lora_name: str) -> bool:
        """切换到指定的 LoRA 权重。

        执行流程：
        1. 检查模型是否已加载
        2. 若当前有活跃 LoRA，先卸载
        3. 加载目标 LoRA
        4. 更新活跃状态

        基于 VoxCPM buffer-based scaling：load_lora 内部使用 fill_()
        进行缩放因子原地修改，避免额外显存分配。

        Args:
            lora_name: LoRA 名称（对应 lora/ 目录下的子目录名）。

        Returns:
            True 表示切换成功，False 表示切换失败。
        """
        with self._lock:
            model = self._get_model()
            if model is None:
                logger.warning("[LoRAHotSwapper] 模型未加载，无法切换 LoRA")
                return False

            lora_dir = self._get_lora_dir()
            lora_path = os.path.join(lora_dir, lora_name)

            if not os.path.exists(lora_path):
                logger.error(f"[LoRAHotSwapper] LoRA 路径不存在: {lora_path}")
                return False

            try:
                # 若当前有活跃 LoRA 且与目标不同，先卸载
                if self._active_lora is not None and self._active_lora != lora_name:
                    logger.info(
                        f"[LoRAHotSwapper] 卸载当前 LoRA: {self._active_lora}"
                    )
                    try:
                        model.unload_lora()
                    except Exception as e:
                        logger.warning(f"[LoRAHotSwapper] LoRA 卸载失败: {e}")
                    self._active_lora = None

                # 加载目标 LoRA
                logger.info(f"[LoRAHotSwapper] 正在加载 LoRA: {lora_name}")
                success = model.load_lora(lora_path)
                if success:
                    self._active_lora = lora_name
                    logger.info(f"[LoRAHotSwapper] LoRA 切换成功: {lora_name}")
                else:
                    self._active_lora = None
                    logger.warning(f"[LoRAHotSwapper] LoRA 加载返回失败: {lora_name}")
                return bool(success)

            except Exception as e:
                logger.error(f"[LoRAHotSwapper] LoRA 切换异常: {e}")
                self._active_lora = None
                return False

    def get_active_lora(self) -> str | None:
        """获取当前活跃的 LoRA 名称。

        Returns:
            活跃 LoRA 名称，无活跃 LoRA 时返回 None。
        """
        with self._lock:
            return self._active_lora

    def list_available_loras(self) -> list[str]:
        """列出所有可用的 LoRA 权重。

        扫描 lora/ 目录下的子目录，仅返回包含至少一个权重文件
        （.safetensors / .bin / .pt / .pth）的目录名。

        Returns:
            可用 LoRA 名称列表（按字母排序）。
        """
        lora_dir = self._get_lora_dir()
        if not os.path.isdir(lora_dir):
            return []

        weight_exts = {".safetensors", ".bin", ".pt", ".pth"}
        available: list[str] = []

        for name in sorted(os.listdir(lora_dir)):
            lora_path = os.path.join(lora_dir, name)
            if not os.path.isdir(lora_path):
                continue
            try:
                for fname in os.listdir(lora_path):
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in weight_exts:
                        available.append(name)
                        break
            except OSError:
                continue

        return available

    def disable_lora(self) -> bool:
        """禁用当前 LoRA 但不卸载权重（保留在内存中）。

        基于 VoxCPM buffer-based scaling 的 set_lora_enabled(False)：
        将缩放因子 fill_() 为 0，等效于禁用 LoRA 层，
        而不实际释放显存。后续可通过 enable_lora() 快速恢复。

        Returns:
            True 表示禁用成功，False 表示失败。
        """
        with self._lock:
            if self._active_lora is None:
                logger.debug("[LoRAHotSwapper] 当前无活跃 LoRA，无需禁用")
                return True

            try:
                model = self._get_model()
                if model is None:
                    return False
                model.set_lora_enabled(False)
                logger.info(f"[LoRAHotSwapper] 已禁用 LoRA: {self._active_lora}")
                return True
            except Exception as e:
                logger.error(f"[LoRAHotSwapper] 禁用 LoRA 失败: {e}")
                return False

    def enable_lora(self) -> bool:
        """重新启用之前禁用的 LoRA。

        基于 VoxCPM buffer-based scaling 的 set_lora_enabled(True)：
        恢复缩放因子，无需重新加载权重。

        Returns:
            True 表示启用成功，False 表示失败。
        """
        with self._lock:
            if self._active_lora is None:
                logger.warning("[LoRAHotSwapper] 当前无活跃 LoRA，无法启用")
                return False

            try:
                model = self._get_model()
                if model is None:
                    return False
                model.set_lora_enabled(True)
                logger.info(f"[LoRAHotSwapper] 已启用 LoRA: {self._active_lora}")
                return True
            except Exception as e:
                logger.error(f"[LoRAHotSwapper] 启用 LoRA 失败: {e}")
                return False


# ======================================================================
# 模块级单例
# ======================================================================

_version_manager: GenerationVersionManager | None = None
_crash_recovery: CrashRecoveryManager | None = None
_lora_swapper: LoRAHotSwapper | None = None
_singleton_lock = threading.Lock()


def get_version_manager() -> GenerationVersionManager:
    """获取全局 GenerationVersionManager 单例。"""
    global _version_manager
    if _version_manager is None:
        with _singleton_lock:
            if _version_manager is None:
                from .config import ROOT_DIR
                db_dir = os.path.join(ROOT_DIR, "data")
                os.makedirs(db_dir, exist_ok=True)
                _version_manager = GenerationVersionManager(db_dir)
    return _version_manager


def get_crash_recovery() -> CrashRecoveryManager:
    """获取全局 CrashRecoveryManager 单例。"""
    global _crash_recovery
    if _crash_recovery is None:
        with _singleton_lock:
            if _crash_recovery is None:
                from .config import ROOT_DIR
                state_dir = os.path.join(ROOT_DIR, "data")
                os.makedirs(state_dir, exist_ok=True)
                _crash_recovery = CrashRecoveryManager(state_dir)
    return _crash_recovery


def get_lora_swapper() -> LoRAHotSwapper:
    """获取全局 LoRAHotSwapper 单例。"""
    global _lora_swapper
    if _lora_swapper is None:
        with _singleton_lock:
            if _lora_swapper is None:
                _lora_swapper = LoRAHotSwapper()
    return _lora_swapper


def close_all_version_connections() -> None:
    """关闭全局版本管理器的所有连接（应用 shutdown 时调用）。"""
    global _version_manager
    if _version_manager is not None:
        _version_manager.close_all()
