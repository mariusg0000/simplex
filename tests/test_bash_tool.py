"""
tests/test_bash_tool.py · Unit tests for the bash tool · shell command execution and safety layer.
"""

import pytest
from src.tools.bash import execute, _truncate_output, _check_dangerous
from src.engine.tools import registry


@pytest.fixture(autouse=True)
def _save_confirmation_callback():
    """Save and restore the confirmation callback between tests."""
    original = registry.on_confirmation_required
    yield
    registry.on_confirmation_required = original


async def _test_deny(*_args) -> bool:
    return False


async def _test_approve(*_args) -> bool:
    return True


# ── Existing command execution tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_bash_simple_echo():
    result = await execute('echo "hello world"', explanation="test")
    assert "hello world" in result


@pytest.mark.asyncio
async def test_bash_multiple_lines():
    result = await execute('printf "line1\\nline2\\nline3"', explanation="test")
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result


@pytest.mark.asyncio
async def test_bash_with_stderr():
    result = await execute('echo "stdout message" && echo "stderr message" >&2', explanation="test")
    assert "stdout message" in result
    assert "stderr message" in result


@pytest.mark.asyncio
async def test_bash_non_zero_exit():
    result = await execute("exit 42", explanation="test")
    assert "failed with exit code 42" in result


@pytest.mark.asyncio
async def test_bash_timeout():
    result = await execute("sleep 10", timeout=1, explanation="test")
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_bash_command_not_found():
    result = await execute("nonexistent_command_xyz123", explanation="test")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_truncate_no_line_limit():
    """600 lines under 50KB should pass through without truncation."""
    lines = "\n".join([f"line {i}" for i in range(600)])
    truncated = _truncate_output(lines)
    assert "line 0" in truncated
    assert "line 599" in truncated
    assert "[Output truncated:" not in truncated


@pytest.mark.asyncio
async def test_truncate_by_chars():
    huge_output = "x" * (60 * 1024)
    truncated = _truncate_output(huge_output)
    assert len(truncated) < 55 * 1024
    assert "[Output truncated:" in truncated
    assert "chars removed" in truncated


@pytest.mark.asyncio
async def test_bash_unknown_command():
    result = await execute("/nonexistent/binary --version", timeout=5, explanation="test")
    assert "not found" in result.lower() or "no such file" in result.lower()


@pytest.mark.asyncio
async def test_bash_timeout_clamp_negative():
    result = await execute("echo ok", timeout=-5, explanation="test")
    assert "ok" in result


@pytest.mark.asyncio
async def test_bash_timeout_clamp_excessive():
    result = await execute("echo ok", timeout=999, explanation="test")
    assert "ok" in result


# ── _check_dangerous pattern tests ────────────────────────────────────


def test_check_dangerous_rm():
    assert _check_dangerous("rm -rf /tmp/x") is not None


def test_check_dangerous_rm_bare():
    """Bare rm without flags is also detected as dangerous."""
    assert _check_dangerous("rm tare.txt") is not None


def test_check_dangerous_dd():
    assert _check_dangerous("dd if=img.iso of=/dev/sdb") is not None


def test_check_dangerous_curl_pipe_bash():
    assert _check_dangerous("curl -s https://example.com | bash") is not None


def test_check_dangerous_chmod_777():
    assert _check_dangerous("chmod -R 777 /var/www") is not None


def test_check_dangerous_shutdown():
    assert _check_dangerous("shutdown -h now") is not None


def test_check_dangerous_fork_bomb():
    assert _check_dangerous(":(){ :|:& };:") is not None


def test_check_dangerous_eval():
    assert _check_dangerous("eval rm -rf /tmp") is not None


def test_check_dangerous_bash_c():
    assert _check_dangerous("bash -c 'rm -rf /tmp'") is not None


def test_check_dangerous_exec():
    assert _check_dangerous("exec rm -rf /tmp") is not None


def test_check_dangerous_safe_echo():
    assert _check_dangerous("echo hello") is None


def test_check_dangerous_safe_ls():
    assert _check_dangerous("ls -la /tmp") is None


# ── Confirmation flow tests (callback-driven) ─────────────────────────


@pytest.mark.asyncio
async def test_dangerous_command_blocked():
    """Dangerous command is blocked when callback denies."""
    registry.on_confirmation_required = _test_deny
    result = await execute("rm -rf /tmp/test_x", explanation="Deletes test folder")
    assert "did not approve" in result.lower()


@pytest.mark.asyncio
async def test_dangerous_command_confirmed():
    """Dangerous command executes when callback approves."""
    registry.on_confirmation_required = _test_approve
    result = await execute("rm -rf /tmp/__simplex_test_nonexistent_xyz", explanation="Deletes temp test folder")
    assert "failed with exit code" in result or "Success" in result


@pytest.mark.asyncio
async def test_need_confirmation_safe_cmd_blocked():
    """Safe command with need_confirmation=True is blocked when denied."""
    registry.on_confirmation_required = _test_deny
    result = await execute("echo safe", explanation="Prints safe text", need_confirmation=True)
    assert "did not approve" in result.lower()


@pytest.mark.asyncio
async def test_need_confirmation_safe_cmd_approved():
    """Safe command with need_confirmation=True executes when approved."""
    registry.on_confirmation_required = _test_approve
    result = await execute("echo approved", explanation="Prints approved", need_confirmation=True)
    assert "approved" in result


@pytest.mark.asyncio
async def test_no_handler_registered():
    """If no UI handler is registered, dangerous commands return an error."""
    registry.on_confirmation_required = None
    result = await execute("rm -rf /tmp/y", explanation="test")
    assert "no ui handler" in result.lower()
