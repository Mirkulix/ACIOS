"""AICOS Memory Manager: shared and per-agent knowledge persistence."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()

KNOWLEDGE_DIR = Path("data/knowledge")

COMPANY_SCOPE = "company"


class MemoryManager:
    """Thread-safe, JSON-backed knowledge store.

    Two levels of scope:
      - ``"company"`` — shared facts visible to all agents.
      - ``<agent_name>`` — private per-agent memory (conversation summaries,
        learned facts, preferences).
    """

    def __init__(self, data_dir: Path | str = KNOWLEDGE_DIR) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # scope -> key -> value
        self._store: dict[str, dict[str, Any]] = {}
        self.load_from_disk()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, key: str, value: Any, scope: str = COMPANY_SCOPE) -> None:
        """Store a value under *key* in *scope* (company or agent name)."""
        with self._lock:
            bucket = self._store.setdefault(scope, {})
            bucket[key] = {
                "value": value,
                "updated_at": datetime.utcnow().isoformat(),
            }
        console.log(f"[magenta]Memory[/] store: [{scope}] {key}")

    def retrieve(self, key: str, scope: str = COMPANY_SCOPE) -> Any | None:
        """Retrieve a previously stored value, or ``None``."""
        with self._lock:
            bucket = self._store.get(scope, {})
            entry = bucket.get(key)
            return entry["value"] if entry else None

    def search(self, query: str, scope: str | None = None) -> list[dict[str, Any]]:
        """Simple keyword search across stored keys and values.

        If *scope* is ``None`` every scope is searched.  Returns a list of
        ``{"scope": ..., "key": ..., "value": ..., "updated_at": ...}`` dicts
        sorted by recency.
        """
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        with self._lock:
            scopes = [scope] if scope else list(self._store.keys())
            for s in scopes:
                bucket = self._store.get(s, {})
                for key, entry in bucket.items():
                    haystack = f"{key} {json.dumps(entry['value'])}".lower()
                    if query_lower in haystack:
                        results.append({
                            "scope": s,
                            "key": key,
                            "value": entry["value"],
                            "updated_at": entry["updated_at"],
                        })

        results.sort(key=lambda r: r["updated_at"], reverse=True)
        return results

    def list_keys(self, scope: str = COMPANY_SCOPE) -> list[str]:
        """Return all keys stored under *scope*."""
        with self._lock:
            return list(self._store.get(scope, {}).keys())

    def delete(self, key: str, scope: str = COMPANY_SCOPE) -> bool:
        """Delete a key from *scope*. Returns True if the key existed."""
        with self._lock:
            bucket = self._store.get(scope, {})
            if key in bucket:
                del bucket[key]
                return True
            return False

    def clear_scope(self, scope: str) -> None:
        """Remove all entries in a given scope."""
        with self._lock:
            self._store.pop(scope, None)

    # ------------------------------------------------------------------
    # Agent-specific helpers
    # ------------------------------------------------------------------

    def append_conversation(self, agent_name: str, role: str, content: str) -> None:
        """Append a turn to an agent's conversation history."""
        history: list[dict[str, str]] = self.retrieve("conversation_history", scope=agent_name) or []
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })
        # Keep only the last 200 turns to bound memory usage.
        self.store("conversation_history", history[-200:], scope=agent_name)

    def get_conversation(self, agent_name: str) -> list[dict[str, str]]:
        return self.retrieve("conversation_history", scope=agent_name) or []

    def store_fact(self, agent_name: str, fact: str) -> None:
        """Add a learned fact for a specific agent."""
        facts: list[str] = self.retrieve("learned_facts", scope=agent_name) or []
        if fact not in facts:
            facts.append(fact)
            self.store("learned_facts", facts, scope=agent_name)

    def get_facts(self, agent_name: str) -> list[str]:
        return self.retrieve("learned_facts", scope=agent_name) or []

    # ------------------------------------------------------------------
    # Disk persistence
    # ------------------------------------------------------------------

    def save_to_disk(self) -> None:
        """Persist every scope as a separate JSON file."""
        with self._lock:
            for scope, bucket in self._store.items():
                file_path = self._data_dir / f"{_safe_filename(scope)}.json"
                with open(file_path, "w", encoding="utf-8") as fh:
                    json.dump(bucket, fh, indent=2, default=str)
        console.log(f"[magenta]Memory[/] saved {len(self._store)} scope(s) to disk")

    def load_from_disk(self) -> None:
        """Load all JSON files in the data directory into memory."""
        with self._lock:
            for file_path in self._data_dir.glob("*.json"):
                scope = file_path.stem
                try:
                    with open(file_path, "r", encoding="utf-8") as fh:
                        self._store[scope] = json.load(fh)
                except (json.JSONDecodeError, OSError) as exc:
                    console.log(f"[red]Memory[/] failed to load {file_path}: {exc}")
        loaded = len(self._store)
        if loaded:
            console.log(f"[magenta]Memory[/] loaded {loaded} scope(s) from disk")


def _safe_filename(name: str) -> str:
    """Sanitise a scope name so it works as a filename."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
