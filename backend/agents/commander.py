"""SwarmMind ADK Commander — 4-stage sequential agent pipeline.

Uses Google ADK with McpToolset connecting to the MCP tool server
via Streamable HTTP transport.

Key constraints (from CRITICAL_ISSUES.md):
- Use McpToolset (not MCPToolset — deprecated)
- Use StreamableHTTPConnectionParams (not SSE — deprecated)
- Set timeout=30 (default 5s is too short)
- Use gemini-2.5-flash (not flash-lite — 50% empty response bug)
- Do NOT use streaming with tools (Gemini 3 bug)
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


# ─── MCP Toolset ────────────────────────────────────────────────

_conn_params = StreamableHTTPConnectionParams(
    url="http://127.0.0.1:8001/mcp",
    timeout=30,
)

fleet_tools = McpToolset(connection_params=_conn_params)
fleet_tools.connection_params = _conn_params  # expose for tests

# ─── Agent Model ────────────────────────────────────────────────
# gemini-2.5-flash is stable for agent loops.
# Do NOT use gemini-3.1-flash-lite — 50% empty response bug (Issue #3525).
AGENT_MODEL = "gemini-2.5-flash"


# ─── Stage 1: Assessor ─────────────────────────────────────────

assess_agent = LlmAgent(
    name="assessor",
    model=AGENT_MODEL,
    instruction=PROMPTS["assessor"]["instruction"],
    tools=[fleet_tools],
    output_key="assessment",
)

# ─── Stage 2: Strategist ───────────────────────────────────────

plan_agent = LlmAgent(
    name="strategist",
    model=AGENT_MODEL,
    instruction=PROMPTS["strategist"]["instruction"],
    tools=[fleet_tools],
    output_key="strategy",
)

# ─── Stage 3: Dispatcher ───────────────────────────────────────

execute_agent = LlmAgent(
    name="dispatcher",
    model=AGENT_MODEL,
    instruction=PROMPTS["dispatcher"]["instruction"],
    tools=[fleet_tools],
    output_key="execution_log",
)

# ─── Stage 4: Analyst ──────────────────────────────────────────

report_agent = LlmAgent(
    name="analyst",
    model=AGENT_MODEL,
    instruction=PROMPTS["analyst"]["instruction"],
    tools=[fleet_tools],
    output_key="report",
)

# ─── Root Agent: Sequential Pipeline ───────────────────────────

root_agent = SequentialAgent(
    name="swarm_commander",
    sub_agents=[assess_agent, plan_agent, execute_agent, report_agent],
)
