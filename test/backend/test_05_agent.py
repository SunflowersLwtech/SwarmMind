"""
Test Suite 05: Google ADK Agent — Structure & MCP Compliance
Tests that the agent pipeline is correctly configured with McpToolset
and satisfies Case Study 3 mandatory MCP protocol requirements.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


def has_google_api_key():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))
    return bool(os.environ.get('GOOGLE_API_KEY'))


class TestAgentStructure:
    """Agent module must export required components."""

    def test_root_agent_importable(self):
        """backend.agents must export root_agent."""
        from backend.agents import root_agent
        assert root_agent is not None

    def test_root_agent_has_name(self):
        from backend.agents import root_agent
        assert hasattr(root_agent, 'name')
        assert isinstance(root_agent.name, str)
        assert root_agent.name == "swarm_commander"

    def test_root_agent_has_sub_agents(self):
        """Root agent must be a SequentialAgent with sub-agents."""
        from backend.agents import root_agent
        has_subs = hasattr(root_agent, 'sub_agents') and len(root_agent.sub_agents) > 0
        assert has_subs, "Root agent must have sub_agents (SequentialAgent pipeline)"

    def test_pipeline_has_4_stages(self):
        """Must have Assess, Plan, Execute, Report stages."""
        from backend.agents import root_agent
        assert len(root_agent.sub_agents) == 4

    def test_stage_names(self):
        """Pipeline stages must have expected names."""
        from backend.agents import root_agent
        names = [a.name for a in root_agent.sub_agents]
        assert names == ["assessor", "strategist", "dispatcher", "analyst"]

    def test_sub_agents_have_tools(self):
        """Each sub-agent must have MCP tools configured."""
        from backend.agents import root_agent
        for agent in root_agent.sub_agents:
            assert hasattr(agent, 'tools') and len(agent.tools) > 0, \
                f"Agent '{agent.name}' has no tools"

    def test_sub_agents_have_instructions(self):
        """Each sub-agent must have a non-empty instruction."""
        from backend.agents import root_agent
        for agent in root_agent.sub_agents:
            if hasattr(agent, 'instruction'):
                assert agent.instruction and len(agent.instruction) > 20, \
                    f"Agent '{agent.name}' has missing/short instruction"

    def test_sub_agents_use_output_key(self):
        """Sub-agents should use output_key for data flow between stages."""
        from backend.agents import root_agent
        keys = [a.output_key for a in root_agent.sub_agents if hasattr(a, 'output_key')]
        assert len(keys) >= 4
        assert "assessment" in keys
        assert "strategy" in keys
        assert "execution_log" in keys
        assert "report" in keys


class TestAgentModel:
    """Agent must use the correct Gemini model."""

    def test_uses_gemini_model(self):
        from backend.agents import root_agent
        for agent in root_agent.sub_agents:
            if hasattr(agent, 'model') and agent.model:
                assert 'gemini' in agent.model.lower(), \
                    f"Agent '{agent.name}' uses non-Gemini model: {agent.model}"

    def test_does_not_use_flash_lite_for_tools(self):
        """Must NOT use flash-lite for tool-calling agents (50% empty response bug)."""
        from backend.agents import root_agent
        for agent in root_agent.sub_agents:
            if hasattr(agent, 'model') and agent.model:
                assert 'lite' not in agent.model.lower(), \
                    f"Agent '{agent.name}' uses flash-lite — known 50% failure rate!"


class TestMCPCompliance:
    """Case Study 3 §4: All agent ↔ drone communication must use MCP."""

    def test_uses_mcp_toolset(self):
        """Each sub-agent must use McpToolset (not direct FunctionTool)."""
        from backend.agents import root_agent
        from google.adk.tools.mcp_tool import McpToolset

        for agent in root_agent.sub_agents:
            has_mcp = any(isinstance(t, McpToolset) for t in agent.tools)
            assert has_mcp, \
                f"Agent '{agent.name}' must use McpToolset, not direct function calls"

    def test_mcp_url_points_to_fleet_server(self):
        """MCP URL must point to the fleet tool server."""
        from backend.agents.commander import MCP_URL
        assert "8001" in MCP_URL, "MCP must connect to port 8001"
        assert "/mcp" in MCP_URL, "MCP endpoint must be /mcp"

    def test_mcp_timeout_adequate(self):
        """MCP timeout must be >= 10s (default 5s is too short for tool chains)."""
        from backend.agents.commander import MCP_TIMEOUT
        assert MCP_TIMEOUT >= 10, f"MCP timeout is {MCP_TIMEOUT}s — too short"

    def test_no_hardcoded_drone_ids_in_commander(self):
        """Commander must not hard-code drone IDs (Case Study 3 §3)."""
        import inspect
        from backend.agents import commander
        source = inspect.getsource(commander)
        for callsign in ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]:
            assert callsign not in source, \
                f"commander.py contains hard-coded drone ID '{callsign}'"


class TestBuildPipeline:
    """build_pipeline factory must create valid MCP-connected pipelines."""

    def test_build_pipeline_returns_sequential_agent(self):
        from backend.agents.commander import build_pipeline
        pipeline = build_pipeline()
        assert pipeline.name == "swarm_commander"
        assert len(pipeline.sub_agents) == 4

    def test_build_pipeline_custom_url(self):
        from backend.agents.commander import build_pipeline
        pipeline = build_pipeline(mcp_url="http://localhost:9999/mcp")
        assert pipeline.name == "swarm_commander"

    def test_build_pipeline_agents_share_toolset(self):
        """All 4 agents should share the same McpToolset instance."""
        from backend.agents.commander import build_pipeline
        from google.adk.tools.mcp_tool import McpToolset
        pipeline = build_pipeline()
        toolsets = []
        for agent in pipeline.sub_agents:
            for tool in agent.tools:
                if isinstance(tool, McpToolset):
                    toolsets.append(id(tool))
        # All should reference the same McpToolset instance
        assert len(set(toolsets)) == 1, "All agents should share one McpToolset"


class TestPromptsConfig:
    """Prompts should be well-structured."""

    def test_prompts_file_exists(self):
        prompts_path = os.path.join(os.path.dirname(__file__), '../../backend/agents/prompts.yaml')
        assert os.path.exists(prompts_path), "prompts.yaml must exist in backend/agents/"

    def test_prompts_yaml_valid(self):
        import yaml
        prompts_path = os.path.join(os.path.dirname(__file__), '../../backend/agents/prompts.yaml')
        if os.path.exists(prompts_path):
            with open(prompts_path) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), "prompts.yaml must be a valid YAML dict"
            assert len(data) >= 4, "prompts.yaml must have at least 4 agent prompts"

    def test_prompts_have_all_stages(self):
        import yaml
        prompts_path = os.path.join(os.path.dirname(__file__), '../../backend/agents/prompts.yaml')
        with open(prompts_path) as f:
            data = yaml.safe_load(f)
        for stage in ["assessor", "strategist", "dispatcher", "analyst"]:
            assert stage in data, f"Missing prompt for '{stage}'"
            assert "instruction" in data[stage], f"Missing instruction for '{stage}'"
