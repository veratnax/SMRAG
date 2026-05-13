"""
LLM Re-ranking Module
Re-rank search results using a user-selected model (OpenAI / Anthropic / Gemini via LiteLLM).
"""
from typing import List, Dict, Optional
import json

from config import LLM_MODEL
from utils.llm_router import chat_completion, supports_openai_json_mode


class LLMReranker:
    """Re-rank search results using LLM"""

    def __init__(
        self,
        openai_api_key: str,
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
    ):
        self._openai_key = openai_api_key
        self._anthropic_key = anthropic_api_key or ""
        self._google_key = google_api_key or ""
        self.model = LLM_MODEL
        self.few_shot_context = ""

    def set_model(self, model_id: str) -> None:
        self.model = model_id

    def set_few_shot_context(self, context: str) -> None:
        self.few_shot_context = context

    def clear_few_shot_context(self) -> None:
        self.few_shot_context = ""

    def rerank(self, query: str, candidates: List[Dict], top_k: int = 5,
               use_case: str = "general",
               matching_guidance: str = "") -> List[Dict]:
        if not candidates:
            return []

        # Keep prior fixed-mode behavior (up to 10 candidates) while allowing
        # auto mode to pass a larger top_k pool for dynamic match selection.
        cap = min(len(candidates), max(int(top_k), 10))
        candidates = candidates[:cap]

        if use_case == "pdf_kb":
            prompt = self._build_pdf_prompt(query, candidates, matching_guidance)
        else:
            prompt = self._build_excel_prompt(query, candidates, matching_guidance)

        try:
            fmt = {"type": "json_object"} if supports_openai_json_mode(self.model) else None
            result_text = chat_completion(
                self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at assessing relevance between queries and documents. Provide rankings in valid JSON format."},
                    {"role": "user", "content": prompt},
                ],
                openai_key=self._openai_key,
                anthropic_key=self._anthropic_key,
                google_key=self._google_key,
                temperature=0.1,
                response_format=fmt,
            )
            rankings = json.loads(result_text)
            return self._apply_rankings(candidates, rankings, top_k)
        except Exception as e:
            print(f"LLM reranking failed: {str(e)}")
            return candidates[:top_k]

    def _build_pdf_prompt(self, query: str, candidates: List[Dict], matching_guidance: str = "") -> str:
        prompt = ""
        if self.few_shot_context:
            prompt += self.few_shot_context
            prompt += "---\n\n"

        prompt += f"""Given this query from a user:
"{query}"
"""

        if matching_guidance and matching_guidance.strip():
            prompt += f"""
Follow this analyst guidance while ranking:
{matching_guidance.strip()}
"""

        prompt += """
Rank the following document excerpts by relevance. Consider:
- Direct answer to the query
- Technical accuracy
- Completeness of information

Candidates:
"""
        for i, candidate in enumerate(candidates, 1):
            text = candidate.get('text', '')[:500]
            page = candidate.get('metadata', {}).get('page_number', 'N/A')
            prompt += f"\n{i}. [Page {page}] {text}\n"

        prompt += f"""
Return a JSON object with:
- "rankings": list of candidate numbers (1-{len(candidates)}) in order of relevance (most relevant first)
- "relevance_scores": list of scores (0-100) corresponding to each ranking
- "reasoning": brief explanation of the top 3 rankings

Example format:
{{
  "rankings": [3, 1, 2],
  "relevance_scores": [95, 82, 70],
  "reasoning": "Candidate 3 directly answers the query with specific details..."
}}
"""
        return prompt

    def _build_excel_prompt(self, query: str, candidates: List[Dict], matching_guidance: str = "") -> str:
        prompt = ""
        if self.few_shot_context:
            prompt += self.few_shot_context
            prompt += "---\n\n"

        prompt += f"""Given this query/complaint:
"{query}"
"""

        if matching_guidance and matching_guidance.strip():
            prompt += f"""
Follow this analyst guidance while ranking:
{matching_guidance.strip()}
"""

        prompt += """
Match it to the most relevant failure modes or keywords. Consider:
- Symptom overlap
- Root cause alignment
- Technical terminology match

Candidates:
"""
        for i, candidate in enumerate(candidates, 1):
            metadata = candidate.get('metadata', {})
            key = metadata.get('key', 'N/A')
            definition = metadata.get('definition', candidate.get('text', ''))[:300]
            prompt += f"\n{i}. {key}: {definition}\n"

        prompt += f"""
Return a JSON object with:
- "rankings": list of candidate numbers (1-{len(candidates)}) in order of relevance (most relevant first)
- "relevance_scores": list of scores (0-100) corresponding to each ranking
- "reasoning": brief explanation of the top 3 matches

Example format:
{{
  "rankings": [2, 4, 1],
  "relevance_scores": [92, 85, 73],
  "reasoning": "Candidate 2 matches the symptoms described (grinding noise, startup failure)..."
}}
"""
        return prompt

    def _apply_rankings(self, candidates: List[Dict], rankings: Dict,
                       top_k: int) -> List[Dict]:
        try:
            ranked_indices = rankings.get('rankings', [])
            relevance_scores = rankings.get('relevance_scores', [])
            reasoning = rankings.get('reasoning', '')

            reranked = []
            for i, idx in enumerate(ranked_indices[:top_k]):
                candidate_idx = idx - 1

                if 0 <= candidate_idx < len(candidates):
                    candidate = candidates[candidate_idx].copy()
                    candidate['llm_rank'] = i + 1

                    if i < len(relevance_scores):
                        candidate['llm_relevance_score'] = relevance_scores[i] / 100.0

                    if i == 0:
                        candidate['llm_reasoning'] = reasoning

                    reranked.append(candidate)

            return reranked

        except Exception as e:
            print(f"Error applying rankings: {str(e)}")
            return candidates[:top_k]
