"""MissionBlackBox — structured JSON logging for agent reasoning traces."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogEntry:
    timestamp: float
    phase: str       # assess | plan | execute | report
    agent: str       # agent name
    action: str      # tool_call | reasoning | result | error
    detail: str
    data: dict | None = None

    def to_dict(self) -> dict:
        return {
            "t": round(self.timestamp, 3),
            "timestamp": round(self.timestamp, 3),
            "phase": self.phase,
            "agent": self.agent,
            "action": self.action,
            "detail": self.detail,
            "data": self.data,
        }


class MissionBlackBox:
    """Structured mission logging for CoT display and post-mission review.

    Unlike SurvAI's ReasoningLogger (plain text to file), this uses:
    - Structured JSON entries with phase/agent/action classification
    - In-memory ring buffer (no disk I/O during mission)
    - Serializable for WebSocket broadcast
    """

    def __init__(self, max_entries: int = 500):
        self.entries: list[LogEntry] = []
        self.max_entries = max_entries
        self._start_time = time.time()

    def log(
        self,
        phase_or_agent: str,
        agent_or_message: str,
        action: str | None = None,
        detail: str | None = None,
        data: dict | None = None,
    ) -> LogEntry:
        """Record a log entry.

        Supports two calling conventions:
        - 2-arg: log(agent, message)
        - 5-arg: log(phase, agent, action, detail, data)
        """
        if action is None:
            # 2-arg form: log(agent, message)
            entry = LogEntry(
                timestamp=time.time() - self._start_time,
                phase="general",
                agent=phase_or_agent,
                action="log",
                detail=agent_or_message,
                data=None,
            )
        else:
            # 5-arg form: log(phase, agent, action, detail, data)
            entry = LogEntry(
                timestamp=time.time() - self._start_time,
                phase=phase_or_agent,
                agent=agent_or_message,
                action=action,
                detail=detail or "",
                data=data,
            )
        self.entries.append(entry)

        # Ring buffer: drop oldest if over limit
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

        return entry

    def tool_call(self, agent: str, tool_name: str, args: dict | None = None) -> None:
        self.log("execute", agent, "tool_call", f"Called {tool_name}", args)

    def tool_result(self, agent: str, tool_name: str, result: Any) -> None:
        detail = str(result)[:200] if result else "empty"
        self.log("execute", agent, "result", f"{tool_name} → {detail}")

    def reasoning(self, agent: str, phase: str, thought: str) -> None:
        self.log(phase, agent, "reasoning", thought)

    def error(self, agent: str, message: str, data: dict | None = None) -> None:
        self.log("execute", agent, "error", message, data)

    def get_recent(self, n: int = 50) -> list[dict]:
        """Return last N entries as dicts."""
        return [e.to_dict() for e in self.entries[-n:]]

    def get_entries(self) -> list[dict]:
        """Return all entries as dicts (preserves insertion order)."""
        return [e.to_dict() for e in self.entries]

    def get_summary(self) -> list[dict]:
        """Return summary of entries (delegates to get_entries)."""
        return self.get_entries()

    def get_all(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]

    def clear(self) -> None:
        self.entries.clear()
        self._start_time = time.time()


# Global singleton
blackbox = MissionBlackBox()
