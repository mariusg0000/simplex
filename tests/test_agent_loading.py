"""
tests/test_agent_loading.py · Verify create_pdf.md is loaded correctly.
"""

from src.engine.agents import AgentRegistry


def test_create_pdf_agent_loaded():
    reg = AgentRegistry()
    assert "create_pdf" in reg._agents


def test_create_pdf_agent_enabled():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert agent.enabled is True


def test_create_pdf_agent_description():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert "PDF" in agent.description


def test_create_pdf_allowed_tools():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert "generate_pdf" in agent.allowed_tools
    assert "write_html" in agent.allowed_tools
    assert "read_file" in agent.allowed_tools
    assert "read_document" in agent.allowed_tools
    assert "pdf_done" not in agent.allowed_tools
    assert "bash" not in agent.allowed_tools


def test_create_pdf_done_tool_defaults_to_task_done():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert agent.done_tool == "task_done"


def test_create_pdf_has_execute_script():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert "execute_script" in dir(agent)
    assert agent.execute_script != ""


def test_create_pdf_role_prompt():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert "generate_pdf" in agent.role_prompt
    assert "write_html" in agent.role_prompt
    assert "read_document" in agent.role_prompt
    assert "_AGENT_DONE_" in agent.role_prompt
