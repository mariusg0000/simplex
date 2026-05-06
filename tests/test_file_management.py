"""
tests/test_file_management.py · Unit tests for file management tools · Verifies CRUD + backup.
"""

import pytest
from pathlib import Path
from src.engine.file_management import (
    read_file, write_file, append_to_file, patch_file, delete_file,
    _create_backup, _is_safe_path
)


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Sets up a mock working directory for safe path checks."""
    wd = tmp_path / "safe"
    wd.mkdir()
    from src.storage import storage
    original_dirs = list(storage.prefs.working_directories)
    storage.prefs.working_directories = [str(wd)]
    yield wd
    storage.prefs.working_directories = original_dirs


@pytest.mark.asyncio
async def test_read_file(work_dir):
    """Happy path: read an existing file."""
    f = work_dir / "test.txt"
    f.write_text("hello world")
    result = await read_file(str(f))
    assert "hello world" in result


@pytest.mark.asyncio
async def test_read_file_access_denied(tmp_path):
    """Reading outside working dirs is denied."""
    f = tmp_path / "outside.txt"
    f.write_text("secret")
    result = await read_file(str(f))
    assert "Access Denied" in result


@pytest.mark.asyncio
async def test_write_file_new(work_dir):
    """Create a new file."""
    f = work_dir / "new.txt"
    result = await write_file(str(f), "fresh content")
    assert "Success" in result
    assert f.read_text() == "fresh content"


@pytest.mark.asyncio
async def test_write_file_overwrite_with_backup(work_dir):
    """Overwriting creates a backup."""
    f = work_dir / "overwrite.txt"
    f.write_text("original")
    result = await write_file(str(f), "updated")
    assert "Success" in result
    assert "Backup created" in result
    assert f.read_text() == "updated"


@pytest.mark.asyncio
async def test_append_to_file(work_dir):
    """Append adds content at the end."""
    f = work_dir / "append.txt"
    f.write_text("line1\n")
    result = await append_to_file(str(f), "line2\n")
    assert "Success" in result
    assert f.read_text() == "line1\nline2\n"


@pytest.mark.asyncio
async def test_patch_file(work_dir):
    """Surgical text replacement works."""
    f = work_dir / "patch.txt"
    f.write_text("Hello Alice, how are you?")
    result = await patch_file(str(f), "Alice", "Bob")
    assert "Success" in result
    assert "Hello Bob" in f.read_text()


@pytest.mark.asyncio
async def test_patch_text_not_found(work_dir):
    """Patching fails gracefully when text not found."""
    f = work_dir / "nope.txt"
    f.write_text("nothing here")
    result = await patch_file(str(f), "missing", "replacement")
    assert "Error" in result


@pytest.mark.asyncio
async def test_delete_file_with_backup(work_dir):
    """Delete creates backup and removes file."""
    f = work_dir / "bye.txt"
    f.write_text("goodbye")
    result = await delete_file(str(f))
    assert "Success" in result
    assert "Backup created" in result
    assert not f.exists()


def test_is_safe_path_outside(work_dir, tmp_path):
    """Paths outside working dirs are not safe."""
    assert not _is_safe_path(str(tmp_path / "evil.txt"))


def test_is_safe_path_inside(work_dir):
    """Paths inside working dirs are safe."""
    assert _is_safe_path(str(work_dir / "ok.txt"))


def test_create_backup_rotation(work_dir):
    """Backup rotates v1->v2, v2->v3, new->v1."""
    f = work_dir / "rotate.txt"
    f.write_text("v0-original")

    bk1 = _create_backup(f)
    assert bk1 is not None
    assert Path(bk1).exists()
    assert Path(bk1).read_text() == "v0-original"

    f.write_text("v0-updated")
    bk2 = _create_backup(f)
    assert Path(bk2).read_text() == "v0-updated"

    # v1 should still exist (original was rotated to v2)
    assert Path(bk1).exists()
