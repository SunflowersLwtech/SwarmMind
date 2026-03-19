"""SwarmMind ADK Commander — 4-stage sequential agent pipeline.

Architecture (competition-compliant):
    Agent (Gemini) ──MCP Protocol──▶ MCP Server (port 8001) ──▶ shared GridWorld

All agent ↔ drone communication goes through MCP protocol (mandatory).
The agent discovers available drones and tools at runtime via MCP tool
discovery — no hard-coded drone IDs, satisfying Case Study 3 §4.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams


# ─── Load prompts from YAML ────────────────────────────────────

_prompts_path = Path(__file__).parent / "prompts.yaml"
with open(_prompts_path) as f:
    PROMPTS = yaml.safe_load(f)

# ─── Configuration ─────────────────────────────────────────────
# gemini-2.5-flash is stable for agent loops.
# Do NOT use gemini-3.1-flash-lite — 50% empty response bug (Issue #3525).
AGENT_MODEL = "gemini-2.5-flash"
MCP_URL = "http://127.0.0.1:8001/mcp"
MCP_TIMEOUT = 30


# ─── Pipeline Factory ─────────────────────────────────────────

def build_pipeline(mcp_url: str = MCP_URL) -> SequentialAgent:
    """Create a 4-stage sequential agent connected to fleet via MCP.

    The agent discovers drone tools at runtime through MCP protocol,
    enabling dynamic fleet adaptation without hard-coded drone IDs.
    McpToolset stores connection params at creation time; the actual
    MCP session is established lazily when Runner executes tools.
    """
    conn = StreamableHTTPConnectionParams(url=mcp_url, timeout=MCP_TIMEOUT)
    fleet_tools = McpToolset(connection_params=conn)

    assess_agent = LlmAgent(
        name="assessor", model=AGENT_MODEL,
        instruction=PROMPTS["assessor"]["instruction"],
        tools=[fleet_tools], output_key="assessment",
    )
    plan_agent = LlmAgent(
        name="strategist", model=AGENT_MODEL,
        instruction=PROMPTS["strategist"]["instruction"],
        tools=[fleet_tools], output_key="strategy",
    )
    execute_agent = LlmAgent(
        name="dispatcher", model=AGENT_MODEL,
        instruction=PROMPTS["dispatcher"]["instruction"],
        tools=[fleet_tools], output_key="execution_log",
    )
    report_agent = LlmAgent(
        name="analyst", model=AGENT_MODEL,
        instruction=PROMPTS["analyst"]["instruction"],
        tools=[fleet_tools], output_key="report",
    )

    return SequentialAgent(
        name="swarm_commander",
        sub_agents=[assess_agent, plan_agent, execute_agent, report_agent],
    )


# ─── Backward compat: root_agent for `adk web` ────────────────
# Requires MCP server running:  python -m backend.services.tool_server
root_agent = build_pipeline()
