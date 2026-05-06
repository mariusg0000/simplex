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

def _search_in_dir_logic(directory: str, pattern: str, visited: Set[str], max_hits: int = 50) -> List[str]:
    """Internal search logic (case-insensitive glob)."""
    matches = []
    directory = str(Path(directory).absolute())
    if directory in visited:
        return []
    
    visited.add(directory)
    pattern_lower = pattern.lower()
    
    try:
        for root, dirs, files in os.walk(directory, topdown=True):
            dirs[:] = [d for d in dirs if not _is_excluded(os.path.join(root, d))]
            
            for filename in files:
                if fnmatch.fnmatch(filename.lower(), pattern_lower):
                    matches.append(os.path.join(root, filename))
                
                if len(matches) >= max_hits:
                    return matches
    except PermissionError:
        pass
    
    return matches

@tool
async def intelligent_file_search(query: str, keywords: List[str], suggested_dir: Optional[str] = None) -> str:
    """
    Search for files strictly within the user-configured working directories.
    
    CRITICAL USAGE:
    - USE ONLY ONE broad keyword (e.g. 'rag').
    - IF YOU GET RESULTS, STOP SEARCHING. Present those results.
    - DO NOT try variations of the same query. The internal Reranker already optimized the list for you.

    PARAMS:
    query: str - A SINGLE, broad keyword.
    keywords: List[str] - Contextual tags.
    suggested_dir: Optional[str] - Ignored (uses persistent working directories).
    """
    # 1. Get configured directories
    work_dirs = storage.prefs.working_directories
    if not work_dirs:
        return "No working directories configured. Please add folders in the Settings menu (gear icon)."

    # 2. Normalize query
    query = query.strip()
    if " " in query and not ("*" in query or "?" in query):
        search_pattern = "*" + "*".join(query.split()) + "*"
    elif "*" not in query and "?" not in query:
        search_pattern = f"*{query}*"
    else:
        search_pattern = query

    print(f"[DEBUG] Strict Search started: pattern='{search_pattern}' in {work_dirs}")
    
    if isinstance(keywords, str):
        keywords = [keywords]

    visited_dirs = set()
    raw_results = []
    
    async def run_search(path: str, limit: int = 50):
        return await to_thread.run_sync(_search_in_dir_logic, path, search_pattern, visited_dirs, limit)

    # 3. Search strictly in each configured directory
    for folder in work_dirs:
        if os.path.exists(folder):
            results = await run_search(folder)
            raw_results.extend(results)

    if raw_results:
        unique_results = list(set(raw_results))
        
        # Sort by modification time (Recent First)
        try:
            unique_results.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
        except:
            pass

        if len(unique_results) == 1:
            print(f"[DEBUG] Only one result found. Skipping Reranker.")
            best_matches = unique_results
        else:
            print(f"[DEBUG] Invoking Reranker Agent on {len(unique_results)} candidates...")
            reranker = RerankerAgent()
            best_matches = await reranker.rerank_files(query, unique_results)
        
        if best_matches:
            return "Found relevant files in your working directories:\n" + "\n".join(best_matches)
    
    return f"No files matching '{query}' were found in your configured working directories."
