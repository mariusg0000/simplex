"""
src/engine/file_management.py · File Operations · Handles safe file manipulation with rolling backups.

REGULI BACKUP (Sistem de Siguranță):
1. LOCAȚIE: Toate backup-urile se salvează în folderul ascuns ~/.backups/
2. STRUCTURĂ: Se copiază CALEA ABSOLUTĂ COMPLETĂ a fișierului (Ex: /mnt/DATA/test.txt devine ~/.backups/mnt/DATA/test.txt.v1)
3. ROTAȚIE: Se păstrează 3 versiuni (.v1, .v2, .v3). .v1 este întotdeauna cea mai nouă.
4. AUTOMATIZARE: Backup-ul se face automat înainte de orice scriere, modificare (patch) sau ștergere. (NOTĂ: Operația de append este exceptată).
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.engine.tools import tool
from src.storage import storage

log = logging.getLogger("simplex.engine.file_management")

BACKUP_ROOT = Path.home() / ".backups"

def _is_safe_path(path: str) -> bool:
    """Checks if the path is within the configured working directories."""
    target_path = Path(path).absolute()
    work_dirs = [Path(d).absolute() for d in storage.prefs.working_directories]
    
    for wd in work_dirs:
        if target_path == wd or target_path.is_relative_to(wd):
            return True
    return False

def _create_backup(target_path: Path) -> Optional[str]:
    """
    WHAT:    Creează un backup rotativ (v1, v2, v3) înainte de a modifica sau șterge un fișier.
    WHY:     Pentru a permite recuperarea datelor în caz de greșeală.
    HOW:     1. Transformă calea în una absolută.
             2. Recreează TOATĂ ierarhia de foldere în ~/.backups/ (ex: /mnt/DATA/... -> ~/.backups/mnt/DATA/...).
             3. Rotește versiunile: șterge .v3, mută .v2 la .v3, mută .v1 la .v2.
             4. Copiază fișierul actual ca .v1.
    PARAMS:  target_path: Path — Calea către fișierul original.
    RETURNS: Optional[str] — Calea către noul backup .v1 creat.
    """
    if not target_path.exists():
        return None

    # Ensure we have an absolute path
    abs_path = target_path.absolute()
    
    # Strip the leading root (/) to make it a relative path we can join
    # On Linux, abs_path.parts[1:] gives us the directories/file without the leading /
    rel_path = Path(*abs_path.parts[1:])
    
    backup_base = BACKUP_ROOT / rel_path
    backup_base.parent.mkdir(parents=True, exist_ok=True)

    # Rotation: v3 (oldest) is deleted, v2 -> v3, v1 -> v2, Current -> v1
    v1 = Path(str(backup_base) + ".v1")
    v2 = Path(str(backup_base) + ".v2")
    v3 = Path(str(backup_base) + ".v3")

    # Correct rotation sequence to preserve history
    if v3.exists(): v3.unlink()
    if v2.exists(): v2.rename(v3)
    if v1.exists(): v1.rename(v2)
    
    shutil.copy2(abs_path, v1)
    log.debug("Backup created: %s", v1)
    return str(v1)

@tool
async def read_file(path: str) -> str:
    """
    Read the content of a text-based file.
    
    PARAMS:
    path: str - Absolute path to the file.
    """
    if not _is_safe_path(path):
        return f"Access Denied: Path '{path}' is outside working directories."
    
    target = Path(path)
    if not target.is_file():
        return f"Error: '{path}' is not a file."

    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {str(e)}"

@tool
async def write_file(path: str, content: str) -> str:
    """
    Create or overwrite a file with new content. Automatically creates a backup if file exists.
    
    PARAMS:
    path: str - Absolute path to the file.
    content: str - The text content to write.
    """
    if not _is_safe_path(path):
        return f"Access Denied: Path '{path}' is outside working directories."

    target = Path(path)
    backup_info = ""
    if target.exists():
        bk_path = _create_backup(target)
        backup_info = f" Backup created at: {bk_path}"
    
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(content, encoding="utf-8")
        return f"Success: File '{path}' written.{backup_info}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

@tool
async def append_to_file(path: str, content: str) -> str:
    """
    Add content to the end of an existing file.
    
    PARAMS:
    path: str - Absolute path to the file.
    content: str - The text content to append.
    """
    if not _is_safe_path(path):
        return f"Access Denied: Path '{path}' is outside working directories."

    target = Path(path)
    try:
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Success: Content appended to '{path}'."
    except Exception as e:
        return f"Error appending to file: {str(e)}"

@tool
async def patch_file(path: str, old_text: str, new_text: str) -> str:
    """
    Replace specific text within a file (surgical modification). Automatically creates a backup.
    
    PARAMS:
    path: str - Absolute path to the file.
    old_text: str - The exact text to find.
    new_text: str - The text to replace it with.
    """
    if not _is_safe_path(path):
        return f"Access Denied: Path '{path}' is outside working directories."

    target = Path(path)
    if not target.exists():
        return f"Error: File '{path}' does not exist."

    bk_path = _create_backup(target)
    
    try:
        content = target.read_text(encoding="utf-8")
        if old_text not in content:
            return f"Error: Text to replace not found in '{path}'."
        
        new_content = content.replace(old_text, new_text)
        target.write_text(new_content, encoding="utf-8")
        return f"Success: File '{path}' patched. Backup created at: {bk_path}"
    except Exception as e:
        return f"Error patching file: {str(e)}"

@tool
async def delete_file(path: str) -> str:
    """
    Delete a file. A backup is ALWAYS created in ~/.backups before deletion.
    
    PARAMS:
    path: str - Absolute path to the file to delete.
    """
    if not _is_safe_path(path):
        return f"Access Denied: Path '{path}' is outside working directories."

    target = Path(path)
    if not target.exists():
        return f"Error: File '{path}' does not exist."

    bk_path = _create_backup(target)
    
    try:
        target.unlink()
        return f"Success: File '{path}' deleted. Backup created at: {bk_path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"
