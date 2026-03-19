"""AgentRunner — drives ADK SequentialAgent and streams CoT to frontend.

The agent communicates with drones exclusively through MCP protocol.
This module only reads world state for situational briefing — all
drone commands flow through:  Agent → McpToolset → MCP Server → GridWorld
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Awaitable, Callable

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from backend.agents.commander import build_pipeline, MCP_URL
from backend.core.grid_world import GridWorld
from backend.utils.blackbox import blackbox

logger = logging.getLogger("swarmmind.agent")

# Session rotation: prevent unbounded context window growth.
# After N cycles, create a fresh session so the LLM doesn't degrade
# from accumulating ~2000 tokens/cycle in conversation history.
SESSION_MAX_CYCLES = 15


def _extract_result_text(response) -> str:
    """Extract readable text from MCP tool response.

    MCP responses are typically: {'content': [{'type': 'text', 'text': '...'}]}
    This extracts the inner text and truncates to 300 chars.
    """
    try:
        if isinstance(response, dict):
            content = response.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text", "")
                if text:
                    return text[:300]
        return str(response)[:300]
    except Exception:
        return str(response)[:300]


class AgentRunner:
    """Runs the 4-stage ADK pipeline and broadcasts events via WebSocket.

    Parameters
    ----------
    world : GridWorld
        Read-only reference for building situational briefings.
        The agent does NOT mutate world directly — all commands go through MCP.
    broadcast_fn : async callable
        WebSocket broadcast function for CoT streaming.
    mcp_url : str
        MCP server endpoint (default: http://127.0.0.1:8001/mcp).
    """

    def __init__(
        self,
        world: GridWorld,
        broadcast_fn: Callable[[dict], Awaitable[None]],
        mcp_url: str = MCP_URL,
    ):
        self.world = world
        self._broadcast = broadcast_fn
        self._running = False
        self._cancelled = False
        self._cycle = 0
        self._agent = build_pipeline(mcp_url)
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self._agent,
            app_name="swarmmind",
            session_service=self._session_service,
        )
        self._session_id: str | None = None
        self._backoff_until: int = 0  # Skip cycles until this cycle number (rate limit)

    def cancel(self) -> None:
        """Mark runner as cancelled. In-flight run_cycle() will exit early."""
        self._cancelled = True

    def try_start(self) -> bool:
        """Atomic compare-and-swap: returns True only if we won the race.

        Safe in single-threaded asyncio — no await between check and set.
        """
        if self._running:
            return False
        self._running = True
        return True

    async def run_cycle(self) -> None:
        """Execute one full agent pipeline cycle."""
        if self._cancelled:
            self._running = False
            return

        self._cycle += 1

        # Rate-limit backoff: skip this cycle if we were recently throttled
        if self._cycle < self._backoff_until:
            logger.info(f"Skipping cycle {self._cycle} (rate-limit backoff until {self._backoff_until})")
            self._running = False
            return
        cycle = self._cycle

        try:
            # Session rotation: prevent context window bloat (runs even if cycle fails)
            if self._session_id and self._cycle % SESSION_MAX_CYCLES == 0:
                logger.info(f"Rotating session after {SESSION_MAX_CYCLES} cycles")
                self._session_id = None

            # Verify credentials: either API key or Vertex AI ADC
            has_api_key = os.environ.get("GOOGLE_API_KEY")
            has_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
            if not has_api_key and not has_vertex:
                raise RuntimeError("No Gemini credentials — set GOOGLE_API_KEY or GOOGLE_GENAI_USE_VERTEXAI=TRUE")

            # Broadcast thinking status
            await self._broadcast({
                "type": "agent_status",
                "payload": {"status": "thinking", "cycle": cycle},
            })

            # Build situational briefing (read-only world access)
            progress = self.world.get_search_progress()
            fleet = self.world.get_fleet_status()
            briefing = (
                f"Cycle {cycle} | Tick {self.world.tick} | "
                f"Coverage {progress.coverage_pct:.1f}% | "
                f"Objectives {progress.objectives_found}/{progress.objectives_total} | "
                f"Fleet: {fleet.active}/{fleet.total} active, avg power {fleet.avg_power:.0f}%"
            )

            blackbox.log("system", f"Agent cycle {cycle} started: {briefing}")

            # Create or reuse session
            if self._session_id is None:
                session = await self._session_service.create_session(
                    app_name="swarmmind", user_id="simulation",
                )
                self._session_id = session.id

            from google.genai import types

            user_content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=briefing)],
            )

            # Stream events from the agent pipeline (retry on rate limit)
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    async for event in self._runner.run_async(
                        user_id="simulation",
                        session_id=self._session_id,
                        new_message=user_content,
                    ):
                        await self._process_event(event, cycle)
                    break  # Success — exit retry loop
                except Exception as retry_err:
                    if attempt < max_retries and ("429" in str(retry_err) or "RESOURCE_EXHAUSTED" in str(retry_err)):
                        wait = 5 * (attempt + 1)
                        logger.warning(f"Rate limited (attempt {attempt+1}), retrying in {wait}s...")
                        blackbox.log("system", f"Rate limited — waiting {wait}s before retry")
                        await asyncio.sleep(wait)
                        # Fresh session to avoid stale context
                        self._session_id = None
                        session = await self._session_service.create_session(
                            app_name="swarmmind", user_id="simulation",
                        )
                        self._session_id = session.id
                    else:
                        raise  # Non-retryable or exhausted retries

            # Cycle complete
            blackbox.log("system", f"Agent cycle {cycle} completed")
            await self._broadcast({
                "type": "agent_status",
                "payload": {"status": "idle", "cycle": cycle},
            })

        except Exception as e:
            err_str = str(e)
            logger.error(f"Agent cycle {cycle} failed: {err_str}", exc_info=True)
            blackbox.error("system", err_str)

            # Rate limit: back off by skipping next cycles
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                self._backoff_until = self._cycle + 3  # Skip 3 cycles
                logger.warning(f"Rate limited — backing off until cycle {self._backoff_until}")

            await self._broadcast({
                "type": "agent_status",
                "payload": {
                    "status": "error",
                    "cycle": cycle,
                    "message": err_str[:200],
                },
            })

        finally:
            self._running = False

    async def _process_event(self, event, cycle: int) -> None:
        """Extract reasoning, tool_call, and tool_result from ADK events."""
        agent_name = getattr(event, "author", "unknown")

        if not hasattr(event, "content") or not event.content:
            return
        if not hasattr(event.content, "parts") or not event.content.parts:
            return

        for part in event.content.parts:
            # Reasoning text
            if hasattr(part, "text") and part.text:
                blackbox.reasoning(agent_name, agent_name, part.text[:500])
                await self._broadcast({
                    "type": "agent_log",
                    "payload": {
                        "phase": agent_name,
                        "agent": agent_name,
                        "action": "reasoning",
                        "detail": part.text[:500],
                        "cycle": cycle,
                        "timestamp": time.time(),
                    },
                })

            # Tool call
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                args = dict(fc.args) if fc.args else {}
                blackbox.tool_call(agent_name, fc.name, args)
                await self._broadcast({
                    "type": "agent_log",
                    "payload": {
                        "phase": agent_name,
                        "agent": agent_name,
                        "action": "tool_call",
                        "detail": f"{fc.name}({args})",
                        "cycle": cycle,
                        "timestamp": time.time(),
                    },
                })

            # Tool result
            if hasattr(part, "function_response") and part.function_response:
                fr = part.function_response
                result_str = _extract_result_text(fr.response)
                blackbox.tool_result(agent_name, fr.name, result_str)
                await self._broadcast({
                    "type": "agent_log",
                    "payload": {
                        "phase": agent_name,
                        "agent": agent_name,
                        "action": "tool_result",
                        "detail": f"{fr.name} → {result_str}",
                        "cycle": cycle,
                        "timestamp": time.time(),
                    },
                })
