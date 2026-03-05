"""AICOS CRM Integration: SQLite-backed contact and deal management."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL DEFAULT '',
    company     TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL REFERENCES contacts(id),
    title       TEXT NOT NULL,
    value       REAL NOT NULL DEFAULT 0,
    stage       TEXT NOT NULL DEFAULT 'lead',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

VALID_STAGES = (
    "lead",
    "qualified",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
)


class CRMIntegration(BaseIntegration):
    """Built-in CRM backed by a local SQLite database.

    Config keys::

        db_path: str  (default "data/crm.db")
    """

    name = "crm"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._db_path = Path(self.config.get("db_path", "data/crm.db"))
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        self._connected = True
        logger.info("CRM connected (db=%s)", self._db_path)

    async def disconnect(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
        self._connected = False
        logger.info("CRM disconnected.")

    # ------------------------------------------------------------------
    # Execute dispatcher
    # ------------------------------------------------------------------

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        actions: dict[str, Any] = {
            "add_contact": self.add_contact,
            "get_contacts": self.get_contacts,
            "add_deal": self.add_deal,
            "update_deal_stage": self.update_deal_stage,
            "get_pipeline": self.get_pipeline,
            "get_deals_by_contact": self.get_deals_by_contact,
            "search_contacts": self.search_contacts,
        }
        handler = actions.get(action)
        if handler is None:
            raise ValueError(f"Unknown CRM action: {action!r}. Available: {list(actions)}")
        return await handler(**params)

    # ------------------------------------------------------------------
    # Contact operations
    # ------------------------------------------------------------------

    async def add_contact(
        self,
        name: str,
        email: str = "",
        company: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Insert a new contact and return its record."""
        assert self._db is not None
        cursor = await self._db.execute(
            "INSERT INTO contacts (name, email, company, notes) VALUES (?, ?, ?, ?)",
            (name, email, company, notes),
        )
        await self._db.commit()
        contact_id = cursor.lastrowid
        logger.info("CRM: added contact #%d %s", contact_id, name)
        return {"id": contact_id, "name": name, "email": email, "company": company, "notes": notes}

    async def get_contacts(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Return a paginated list of contacts."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM contacts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return {"contacts": [dict(r) for r in rows]}

    async def search_contacts(self, query: str) -> dict[str, Any]:
        """Search contacts by name, email, or company."""
        assert self._db is not None
        like = f"%{query}%"
        cursor = await self._db.execute(
            "SELECT * FROM contacts WHERE name LIKE ? OR email LIKE ? OR company LIKE ? ORDER BY created_at DESC",
            (like, like, like),
        )
        rows = await cursor.fetchall()
        return {"contacts": [dict(r) for r in rows]}

    # ------------------------------------------------------------------
    # Deal operations
    # ------------------------------------------------------------------

    async def add_deal(
        self,
        contact_id: int,
        title: str,
        value: float = 0,
        stage: str = "lead",
    ) -> dict[str, Any]:
        """Create a new deal linked to a contact."""
        assert self._db is not None
        if stage not in VALID_STAGES:
            raise ValueError(f"Invalid stage: {stage!r}. Must be one of {VALID_STAGES}")
        cursor = await self._db.execute(
            "INSERT INTO deals (contact_id, title, value, stage) VALUES (?, ?, ?, ?)",
            (contact_id, title, value, stage),
        )
        await self._db.commit()
        deal_id = cursor.lastrowid
        logger.info("CRM: added deal #%d '%s' ($%.2f) stage=%s", deal_id, title, value, stage)
        return {"id": deal_id, "contact_id": contact_id, "title": title, "value": value, "stage": stage}

    async def update_deal_stage(self, deal_id: int, stage: str) -> dict[str, Any]:
        """Move a deal to a new pipeline stage."""
        assert self._db is not None
        if stage not in VALID_STAGES:
            raise ValueError(f"Invalid stage: {stage!r}. Must be one of {VALID_STAGES}")
        now = datetime.utcnow().isoformat()
        await self._db.execute(
            "UPDATE deals SET stage = ?, updated_at = ? WHERE id = ?",
            (stage, now, deal_id),
        )
        await self._db.commit()
        logger.info("CRM: deal #%d moved to stage=%s", deal_id, stage)
        return {"deal_id": deal_id, "stage": stage, "updated_at": now}

    async def get_pipeline(self) -> dict[str, Any]:
        """Return all deals grouped by pipeline stage."""
        assert self._db is not None
        pipeline: dict[str, list[dict[str, Any]]] = {s: [] for s in VALID_STAGES}

        cursor = await self._db.execute(
            """
            SELECT d.*, c.name AS contact_name, c.company AS contact_company
            FROM deals d
            LEFT JOIN contacts c ON c.id = d.contact_id
            ORDER BY d.updated_at DESC
            """
        )
        rows = await cursor.fetchall()
        for row in rows:
            record = dict(row)
            stage = record.get("stage", "lead")
            if stage in pipeline:
                pipeline[stage].append(record)

        total_value = sum(r.get("value", 0) for r in (dict(row) for row in rows))
        return {"pipeline": pipeline, "total_value": total_value, "total_deals": len(rows)}

    async def get_deals_by_contact(self, contact_id: int) -> dict[str, Any]:
        """Return all deals for a specific contact."""
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM deals WHERE contact_id = ? ORDER BY updated_at DESC",
            (contact_id,),
        )
        rows = await cursor.fetchall()
        return {"deals": [dict(r) for r in rows]}
