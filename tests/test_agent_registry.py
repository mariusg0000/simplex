"""
tests/test_agent_registry.py · Unit tests for AgentRegistry · parsing, schemas, descriptions.
"""

from src.engine.agents import AgentRegistry, _parse_agent_md

SAMPLE_MD = """\
## enabled
enabled

## agent_description
You can delegate PDF creation tasks to the `create_pdf` agent.

## allowed_tools
bash
generate_pdf
task_done

## role_prompt
You are a PDF generation specialist.
"""


def test_parse_agent_md():
    sections = _parse_agent_md(SAMPLE_MD)
    assert sections["enabled"] == "enabled"
    assert "delegate PDF creation" in sections["agent_description"]
    assert sections["allowed_tools"] == "bash\ngenerate_pdf\ntask_done"
    assert "PDF generation specialist" in sections["role_prompt"]


def test_parse_agent_md_missing_section():
    md = """\
## enabled
enabled

## agent_description
Some description.
"""
    sections = _parse_agent_md(md)
    assert "enabled" in sections
    assert "agent_description" in sections
    assert "allowed_tools" not in sections
    assert "role_prompt" not in sections


def test_parse_agent_md_disabled():
    md = """\
## enabled
disabled

## agent_description
You can delegate PDF creation tasks to the `create_pdf` agent.

## allowed_tools
bash
generate_pdf
task_done

## role_prompt
You are a PDF generation specialist.
"""
    sections = _parse_agent_md(md)
    assert sections["enabled"] == "disabled"


PARSE_ORDER_MD = """\
## role_prompt
role content

## enabled
enabled

## allowed_tools
bash

## agent_description
desc
"""


def test_parse_agent_md_section_order_independent():
    sections = _parse_agent_md(PARSE_ORDER_MD)
    assert sections["role_prompt"] == "role content"
    assert sections["enabled"] == "enabled"
    assert sections["allowed_tools"] == "bash"
    assert sections["agent_description"] == "desc"


def test_agent_registry_discovers_create_pdf():
    """The built-in create_pdf.md should be discovered."""
    reg = AgentRegistry()
    assert "create_pdf" in reg


def test_agent_registry_get_descriptions():
    reg = AgentRegistry()
    desc = reg.get_descriptions()
    assert "create_pdf" in desc or "[Agent: create_pdf]" in desc


def test_agent_registry_get_schemas():
    reg = AgentRegistry()
    schemas = reg.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "create_pdf" in names


def test_agent_registry_disable():
    reg = AgentRegistry()
    reg.disable("create_pdf")
    schemas = reg.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "create_pdf" not in names
    reg.enable("create_pdf")
    schemas = reg.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "create_pdf" in names


def test_agent_registry_unknown_call():
    reg = AgentRegistry()
    import asyncio
    result = asyncio.run(reg.call("nonexistent", {"task": "test"}))
    assert "not found" in result
