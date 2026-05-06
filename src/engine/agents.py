"""
src/engine/agents.py · Sub-agent architecture · Base classes for specialized internal agents.
"""

from typing import List, Dict, Any, Optional
import litellm
from src.config import settings

class SubAgent:
    """
    WHAT:    Base class for internal specialized agents.
    WHY:     Encapsulates isolated LLM tasks (reranking, analysis, etc.) without polluting chat history.
    HOW:     Uses a private litellm call with a specific system prompt.
    """
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt

    async def run(self, task_input: str, model_override: Optional[str] = None) -> str:
        """
        Executes the sub-agent task.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_input}
        ]
        
        response = await litellm.acompletion(
            model=model_override or settings.model,
            messages=messages,
            api_key=settings.openai_api_key,
            api_base=settings.openai_api_base,
            temperature=0.1 # Low temperature for consistent reasoning/filtering
        )
        
        return response.choices[0].message.content

class RerankerAgent(SubAgent):
    """
    Specialized sub-agent for filtering and ranking a list of data based on context.
    """
    def __init__(self):
        super().__init__(
            name="Reranker",
            system_prompt=(
                "You are an expert File System Analyst. Your task is to look at a list of raw file paths "
                "and select the most relevant ones based on the user's search context.\n"
                "RULES:\n"
                "1. Return a comma-separated list of ONLY the best paths (max 5).\n"
                "2. Prioritize files that look like source documents, code, or data (PDF, DOCX, MD, PY, CSV).\n"
                "3. Ignore temporary, cache, or build-related files if others are available.\n"
                "4. If nothing seems relevant, return 'NONE'.\n"
                "5. Output ONLY the paths, nothing else."
            )
        )

    async def rerank_files(self, query: str, file_paths: List[str]) -> List[str]:
        if not file_paths:
            return []
            
        task_input = f"User is searching for: '{query}'\nRaw results found:\n" + "\n".join(file_paths)
        result = await self.run(task_input)
        
        if "NONE" in result:
            return []
            
        # Parse comma-separated or newline-separated paths
        cleaned_paths = [p.strip().strip("'\"") for p in result.replace("\n", ",").split(",") if p.strip()]
        return cleaned_paths[:5]
