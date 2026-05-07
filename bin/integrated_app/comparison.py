# -*- coding: utf-8 -*-
"""A/B audio comparison: generation parameter snapshots and side-by-side playback."""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger("tts_multimodel")


class ComparisonSession:
    """Manages A/B comparison sessions between two generations.
    
    Stores the previous generation result alongside the current one,
    along with complete parameter snapshots for reproducibility.
    """

    def __init__(self, output_dir: str):
        self._output_dir = output_dir
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load_sessions()

    def _load_sessions(self):
        """Load existing comparison sessions from file."""
        sessions_path = os.path.join(self._output_dir, "comparison_sessions.json")
        if os.path.exists(sessions_path):
            try:
                with open(sessions_path, "r", encoding="utf-8") as f:
                    self._sessions = json.load(f)
            except Exception:
                pass

    def _save_sessions(self):
        """Persist comparison sessions."""
        sessions_path = os.path.join(self._output_dir, "comparison_sessions.json")
        try:
            with open(sessions_path, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save comparison sessions: {e}")

    def create_session(
        self,
        session_id: str,
        audio_a: str,
        audio_b: str,
        params_a: Dict[str, Any],
        params_b: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new A/B comparison session.

        Args:
            session_id: Unique identifier for this session.
            audio_a: Path to the first audio file (previous/result A).
            audio_b: Path to the second audio file (new/result B).
            params_a: Generation parameters for audio A.
            params_b: Generation parameters for audio B.
        """
        self.clear_old_sessions(max_age_hours=1)

        MAX_SESSIONS = 100
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions.items(), key=lambda x: x[1].get("created_at", float('inf')))
            del self._sessions[oldest[0]]

        session = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "audio_a": audio_a,
            "audio_b": audio_b,
            "params_a": params_a,
            "params_b": params_b,
            "active": True,
        }
        self._sessions[session_id] = session
        self._save_sessions()
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a comparison session by ID."""
        return self._sessions.get(session_id)

    def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent comparison sessions."""
        sorted_sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.get("created_at", ""),
            reverse=True,
        )
        return sorted_sessions[:limit]

    def clear_old_sessions(self, max_age_hours: int = 24):
        """Clear sessions older than max_age_hours."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for sid, session in self._sessions.items():
            created = session.get("created_at", "")
            if created and datetime.fromisoformat(created) < cutoff:
                to_remove.append(sid)
        
        for sid in to_remove:
            del self._sessions[sid]
        
        if to_remove:
            self._save_sessions()


def format_param_diff(params_a: Dict, params_b: Dict) -> List[Dict[str, Any]]:
    """Compare two parameter sets and return a list of differences.
    
    Returns list of {param, value_a, value_b, changed}.
    """
    all_keys = set(params_a.keys()) | set(params_b.keys())
    diffs = []
    
    for key in sorted(all_keys):
        val_a = params_a.get(key, None)
        val_b = params_b.get(key, None)
        if val_a != val_b:
            diffs.append({
                "param": key,
                "value_a": val_a,
                "value_b": val_b,
                "changed": True,
            })
        else:
            diffs.append({
                "param": key,
                "value_a": val_a,
                "value_b": val_b,
                "changed": False,
            })
    
    return diffs
