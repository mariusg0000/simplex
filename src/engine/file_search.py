"""
src/engine/file_search.py · Intelligent File Search · Implements focused search within configured directories.
"""

import os
import json
import fnmatch
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
from src.engine.tools import tool
from src.storage import storage
from src.engine.agents import RerankerAgent
from anyio import to_thread

TRACKING_FILE = "search_tracking.json"

# System and junk folders to exclude by default
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", 
    ".pytest_cache", ".cache", "bin", "lib", "obj", "build",
    "dist", "AppData", "Local Settings", "System Volume Information"
}

# Root paths that should NOT be searched recursively from
DANGEROUS_ROOTS = {"/", "C:\\", "/mnt", "/media"}

class SearchTracker:
    """Manages the learning database for file locations."""
    def __init__(self, file_path: str = TRACKING_FILE):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except:
            pass

    def record_hit(self, folder_path: str, keywords: List[str]):
        folder_path = str(Path(folder_path).absolute())
        for entry in self.data:
            if entry["folder_path"] == folder_path:
                entry["hit_count"] += 1
                existing_kw = set(entry.get("keywords", []))
                existing_kw.update([kw.lower() for kw in keywords])
                entry["keywords"] = list(existing_kw)
                self.save()
                return

        self.data.append({
            "folder_path": folder_path,
            "hit_count": 1,
            "keywords": [kw.lower() for kw in keywords]
        })
        self.save()

    def get_ranked_locations(self, keywords: List[str]) -> List[str]:
        query_kw = set([kw.lower() for kw in keywords])
        scored_locations = []
        
        for entry in self.data:
            entry_kw = set(entry.get("keywords", []))
            match_count = len(query_kw.intersection(entry_kw))
            if match_count > 0:
                score = (match_count * 10) + entry["hit_count"]
                scored_locations.append((score, entry["folder_path"]))
        
        scored_locations.sort(key=lambda x: x[0], reverse=True)
        return [loc for _, loc in scored_locations]

tracker = SearchTracker()

def _is_excluded(path: str) -> bool:
    name = os.path.basename(path)
    return name in EXCLUDE_DIRS

def _search_in_dir_logic(directory: str, search_units: List[List[str]], visited: Set[str], max_hits: int = 200) -> List[str]:
    """Internal search logic (matches ALL keywords in ANY search unit)."""
    matches = []
    directory = str(Path(directory).absolute())
    if directory in visited:
        return []
    
    visited.add(directory)
    
    try:
        # Increase performance by using a faster walk or limit check
        for root, dirs, files in os.walk(directory, topdown=True):
            dirs[:] = [d for d in dirs if not _is_excluded(os.path.join(root, d))]
            
            # Prioritize folders for faster discovery of archives/projects
            for name in dirs:
                full_path = os.path.join(root, name)
                path_lower = full_path.lower()
                for unit in search_units:
                    if all(kw.lower() in path_lower for kw in unit):
                        matches.append(full_path)
                        break
                if len(matches) >= max_hits: return matches

            for name in files:
                full_path = os.path.join(root, name)
                path_lower = full_path.lower()
                for unit in search_units:
                    if all(kw.lower() in path_lower for kw in unit):
                        matches.append(full_path)
                        break
                if len(matches) >= max_hits: return matches
    except PermissionError:
        pass
    
    return matches

@tool
async def file_search(query: str, keywords: List[str] = None) -> str:
    """
    Search for files and folders strictly within the user-configured working directories.
    Matches ALL keywords in the full path (AND logic).

    PARAMS:
    query: str - The main search term (can be a filename).
    keywords: List[str] - Up to 6 keywords to match in the path.
    """
    # 1. Get configured directories
    work_dirs = storage.prefs.working_directories
    if not work_dirs:
        return "No working directories configured. Please add folders in the Settings menu."

    # 2. Prepare the keyword list (query + keywords)
    search_keywords = []
    if query:
        search_keywords.extend(query.lower().split())
    if keywords:
        if isinstance(keywords, str):
            search_keywords.extend(keywords.lower().split())
        else:
            search_keywords.extend([kw.lower() for kw in keywords])
    
    # Deduplicate and limit to 6
    search_keywords = list(set(search_keywords))[:6]
    
    print(f"[DEBUG] Search started with keywords: {search_keywords}")

    visited_dirs = set()
    raw_results = []
    
    # We use a single search unit containing all keywords (AND logic)
    search_units = [search_keywords]
    
    async def run_search(path: str, units: List[List[str]], limit: int = 200):
        return await to_thread.run_sync(_search_in_dir_logic, path, units, visited_dirs, limit)

    # 3. Search in each configured directory
    for folder in work_dirs:
        if os.path.exists(folder):
            results = await run_search(folder, search_units)
            raw_results.extend(results)

    if raw_results:
        unique_results = list(set(raw_results))
        
        # Sort by modification time
        try:
            unique_results.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
        except:
            pass

        # Use Reranker for the final selection (max 10)
        print(f"[DEBUG] Invoking Reranker on {len(unique_results)} candidates...")
        reranker = RerankerAgent()
        best_matches = await reranker.rerank_files(query, unique_results)
        
        if best_matches:
            return "Found relevant files/folders:\n" + "\n".join(best_matches)
    
    return f"No results for {search_keywords} found. Please try different keywords."

@tool
async def list_directory(path: str) -> str:
    """
    List all files and sub-directories inside a given folder path.
    Use this to see what's inside a folder found by file_search.

    PARAMS:
    path: str - The absolute path to the directory to list.
    """
    import os
    from datetime import datetime
    
    print(f"[DEBUG] list_directory call received for path: {path}")
    target_path = Path(path).absolute()
    
    # Security: Ensure path is within working directories
    work_dirs = [Path(d).absolute() for d in storage.prefs.working_directories]
    print(f"[DEBUG] Validating {target_path} against {work_dirs}")
    is_safe = False
    for wd in work_dirs:
        if target_path == wd or target_path.is_relative_to(wd):
            is_safe = True
            break
    
    if not is_safe:
        print(f"[DEBUG] list_directory Access Denied: {target_path} not in {work_dirs}")
        return f"Access Denied: Path '{path}' is outside your configured working directories."

    print(f"[DEBUG] list_directory executing for: {target_path}")

    if not target_path.exists():
        return f"Error: Path '{path}' does not exist."
    
    if not target_path.is_dir():
        return f"Error: Path '{path}' is a file, not a directory. Use read_document_content to read it."

    try:
        output = [f"Contents of {target_path}:\n"]
        items = sorted(os.listdir(target_path))
        
        if not items:
            return f"Directory '{path}' is empty."

        for item in items:
            if item.startswith('.') and item not in {'.env'}:
                continue
                
            full_item_path = target_path / item
            try:
                stats = full_item_path.stat()
                mtime = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M')
                
                if full_item_path.is_dir():
                    output.append(f"[DIR]  {item}/")
                else:
                    size_kb = stats.st_size / 1024
                    output.append(f"[FILE] {item} ({size_kb:.1f} KB) - Modified: {mtime}")
            except Exception:
                output.append(f"[?]    {item} (Permission Denied)")
                
        return "\n".join(output)
    except Exception as e:
        return f"Error listing directory: {str(e)}"
