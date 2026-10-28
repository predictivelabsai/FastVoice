"""Tiny JSON-file incident status store (admin-editable). Active incidents are
announced in the greeting and given to the LLM as priority context."""

from __future__ import annotations

import json
import threading
from pathlib import Path

STATUSES = ("planned", "active", "inactive", "resolved")
_lock = threading.Lock()


class IncidentStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8")).get("incidents", [])

    def save(self, items: list[dict]) -> None:
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"incidents": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def active(self) -> list[dict]:
        return [i for i in self.load() if i.get("status") == "active"]

    def set_status(self, incident_id: str, status: str) -> dict:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        items = self.load()
        for it in items:
            if it["id"] == incident_id:
                it["status"] = status
                self.save(items)
                return it
        raise KeyError(incident_id)
