"""AICOS Communication Bus: async message passing between agents."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from core.models import Message, MessageType

if TYPE_CHECKING:
    pass

console = Console()

LOG_DIR = Path("data/logs")


class CommunicationBus:
    """Async message bus that routes messages between AI agents.

    Each agent has its own asyncio.Queue inbox.  Every message is also
    appended to a global conversation log that is periodically flushed to
    disk so that the full communication history survives restarts.
    """

    def __init__(self, log_dir: Path | str = LOG_DIR) -> None:
        self._inboxes: dict[str, asyncio.Queue[Message]] = {}
        self._conversation_log: list[Message] = []
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._registered_agents: set[str] = set()

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_name: str) -> None:
        """Create an inbox queue for *agent_name* if it doesn't exist."""
        if agent_name not in self._inboxes:
            self._inboxes[agent_name] = asyncio.Queue()
            self._registered_agents.add(agent_name)
            console.log(f"[cyan]CommBus[/] registered agent: {agent_name}")

    def unregister_agent(self, agent_name: str) -> None:
        self._inboxes.pop(agent_name, None)
        self._registered_agents.discard(agent_name)

    @property
    def agents(self) -> set[str]:
        return set(self._registered_agents)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(self, from_agent: str, to_agent: str, content: str, **meta: object) -> Message:
        """Send a direct message from one agent to another."""
        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=MessageType.DIRECT,
            metadata=dict(meta),
        )
        await self._deliver(msg, targets=[to_agent])
        return msg

    async def broadcast(self, from_agent: str, content: str, **meta: object) -> Message:
        """Broadcast a message to every registered agent (except sender)."""
        msg = Message(
            from_agent=from_agent,
            to_agent="*",
            content=content,
            message_type=MessageType.BROADCAST,
            metadata=dict(meta),
        )
        targets = [a for a in self._registered_agents if a != from_agent]
        await self._deliver(msg, targets=targets)
        return msg

    async def escalate(self, from_agent: str, content: str, **meta: object) -> Message:
        """Escalate a message to the CEO agent."""
        ceo_names = [a for a in self._registered_agents if "ceo" in a.lower()]
        target = ceo_names[0] if ceo_names else next(iter(self._registered_agents), from_agent)

        msg = Message(
            from_agent=from_agent,
            to_agent=target,
            content=content,
            message_type=MessageType.ESCALATION,
            metadata=dict(meta),
        )
        await self._deliver(msg, targets=[target])
        return msg

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def get_inbox(self, agent_name: str) -> list[Message]:
        """Return all pending messages for *agent_name* (non-blocking drain)."""
        queue = self._inboxes.get(agent_name)
        if queue is None:
            return []
        messages: list[Message] = []
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    async def wait_for_message(self, agent_name: str, timeout: float | None = None) -> Message | None:
        """Block until a message arrives in *agent_name*'s inbox (or timeout)."""
        queue = self._inboxes.get(agent_name)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return None

    def get_conversation_log(self) -> list[Message]:
        """Return the full communication history."""
        return list(self._conversation_log)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _deliver(self, msg: Message, targets: list[str]) -> None:
        """Put *msg* into each target's inbox and log it."""
        self._conversation_log.append(msg)

        for target in targets:
            queue = self._inboxes.get(target)
            if queue is not None:
                await queue.put(msg)

        self._log_message(msg)
        self._print_message(msg)

    def _log_message(self, msg: Message) -> None:
        """Append a JSON line to today's log file."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"comms_{today}.jsonl"
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(msg.model_dump_json() + "\n")

    @staticmethod
    def _print_message(msg: Message) -> None:
        style = {
            MessageType.DIRECT: "green",
            MessageType.BROADCAST: "yellow",
            MessageType.ESCALATION: "bold red",
        }.get(msg.message_type, "white")
        direction = f"{msg.from_agent} -> {msg.to_agent}"
        console.log(f"[{style}][{msg.message_type.upper()}][/{style}] {direction}: {msg.content[:120]}")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save_log_snapshot(self, path: Path | str | None = None) -> Path:
        """Dump the full conversation log as a JSON file."""
        dest = Path(path) if path else self._log_dir / "conversation_snapshot.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump([m.model_dump(mode="json") for m in self._conversation_log], fh, indent=2, default=str)
        return dest
