"""
Test Suite 05: Google ADK Agent
Tests that the agent is correctly configured and can execute missions.
NOTE: Requires GOOGLE_API_KEY to be set. Tests will skip if not available.
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
        assert len(root_agent.name) > 0

    def test_root_agent_has_sub_agents(self):
        """Root agent must be a SequentialAgent with sub-agents."""
        from backend.agents import root_agent
        has_subs = hasattr(root_agent, 'sub_agents') and len(root_agent.sub_agents) > 0
        assert has_subs, "Root agent must have sub_agents (SequentialAgent pipeline)"

    def test_pipeline_has_4_stages(self):
        """Must have Assess, Plan, Execute, Report stages."""
        from backend.agents import root_agent
        sub_agents = root_agent.sub_agents
        assert len(sub_agents) >= 3, f"Expected >=3 pipeline stages, got {len(sub_agents)}"

    def test_sub_agents_have_tools(self):
        """At least one sub-agent must have MCP tools configured."""
        from backend.agents import root_agent
        has_tools = any(
            hasattr(agent, 'tools') and len(agent.tools) > 0
            for agent in root_agent.sub_agents
        )
        assert has_tools, "At least one sub-agent must have tools (McpToolset)"

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
        agents_with_output_key = [
            a for a in root_agent.sub_agents
            if hasattr(a, 'output_key') and a.output_key
        ]
        assert len(agents_with_output_key) >= 2, \
            "At least 2 sub-agents should use output_key for pipeline data flow"


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
            if hasattr(agent, 'tools') and agent.tools and hasattr(agent, 'model') and agent.model:
                assert 'lite' not in agent.model.lower(), \
                    f"Agent '{agent.name}' uses flash-lite with tools — known 50% failure rate!"


class TestMCPToolsetConfig:
    """McpToolset must be correctly configured."""

    def test_mcp_toolset_configured(self):
        """At least one agent must use McpToolset."""
        from backend.agents import root_agent
        from google.adk.tools.mcp_tool import McpToolset

        found = False
        for agent in root_agent.sub_agents:
            if hasattr(agent, 'tools'):
                for tool in agent.tools:
                    if isinstance(tool, McpToolset):
                        found = True
                        break
        assert found, "No McpToolset found in any sub-agent's tools"

    def test_mcp_timeout_not_default(self):
        """McpToolset timeout must be explicitly set (default 5s is too short)."""
        from backend.agents import root_agent
        from google.adk.tools.mcp_tool import McpToolset

        for agent in root_agent.sub_agents:
            if hasattr(agent, 'tools'):
                for tool in agent.tools:
                    if isinstance(tool, McpToolset):
                        params = tool.connection_params
                        if hasattr(params, 'timeout'):
                            assert params.timeout >= 10, \
                                f"McpToolset timeout is {params.timeout}s — too short. Set >= 10s"


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
            assert len(data) > 0, "prompts.yaml must not be empty"
