"""
tests/test_agent_registry.py · Unit tests for AgentRegistry · parsing, schemas, descriptions.
"""

from src.engine.agents import AgentRegistry, _parse_agent_md

SAMPLE_MD = """\
## enabled
enabled

## agent_description
You can delegate document processing tasks to the `process_doc` agent.

## allowed_tools
bash
read_file

## role_prompt
You are a document processing specialist.

## execute_script
print("ok")
"""


def test_parse_agent_md():
    sections = _parse_agent_md(SAMPLE_MD)
    assert sections["enabled"] == "enabled"
    assert "delegate document processing" in sections["agent_description"]
    assert sections["allowed_tools"] == "bash\nread_file"
    assert "document processing specialist" in sections["role_prompt"]
    assert "done_tool" not in sections
    assert sections["execute_script"] == 'print("ok")'


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
You can delegate document processing tasks.

## allowed_tools
bash
read_file

## role_prompt
You are a document processing specialist.

## execute_script
print("ok")
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


def test_agent_registry_discovers_agents():
    """Built-in agents should be discovered."""
    reg = AgentRegistry()
    assert "create_doc" in reg


def test_agent_registry_get_descriptions():
    reg = AgentRegistry()
    desc = reg.get_descriptions()
    assert "create_doc" in desc or "[Agent: create_doc]" in desc


def test_agent_registry_get_schemas():
    reg = AgentRegistry()
    schemas = reg.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "create_doc" in names


def test_agent_registry_disable():
    reg = AgentRegistry()
    reg.disable("create_doc")
    schemas = reg.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "create_doc" not in names
    reg.enable("create_doc")
    schemas = reg.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "create_doc" in names


def test_agent_registry_unknown_call():
    reg = AgentRegistry()
    import asyncio
    result = asyncio.run(reg.call("nonexistent", {"task": "test"}))
    assert "not found" in result
