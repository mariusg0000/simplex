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
    assert "bash" in agent.allowed_tools
    assert "generate_pdf" in agent.allowed_tools
    assert "task_done" in agent.allowed_tools


def test_create_pdf_role_prompt():
    reg = AgentRegistry()
    agent = reg._agents["create_pdf"]
    assert "generate_pdf" in agent.role_prompt
