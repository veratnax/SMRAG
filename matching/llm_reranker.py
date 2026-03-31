"""
LLM Re-ranking Module
Uses GPT-4 to re-rank search results based on relevance
"""
from openai import OpenAI
from typing import List, Dict
from config import LLM_MODEL
import json


class LLMReranker:
    """Re-rank search results using LLM"""
    
    def __init__(self, api_key: str):
        """
        Initialize reranker with OpenAI API key
        
        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)
        self.model = LLM_MODEL
        self.few_shot_context = ""  # Store few-shot examples
    
    def set_few_shot_context(self, context: str) -> None:
        """
        Set few-shot learning context from QA feedback
        
        Args:
            context: Formatted string with good query-match examples
        """
        self.few_shot_context = context
    
    def clear_few_shot_context(self) -> None:
        """Clear few-shot learning context"""
        self.few_shot_context = ""
    
    def rerank(self, query: str, candidates: List[Dict], top_k: int = 5,
               use_case: str = "general",
               matching_guidance: str = "") -> List[Dict]:
        """
        Re-rank candidates using LLM
        
        Args:
            query: Original query
            candidates: List of candidate matches
            top_k: Number of results to return
            use_case: Type of matching ("pdf_kb" or "excel_kb")
            matching_guidance: Optional user instructions for ranking logic
            
        Returns:
            Re-ranked results with relevance scores
        """
        if not candidates:
            return []
        
        # Limit candidates to avoid token limits
        candidates = candidates[:min(len(candidates), 10)]
        
        # Build prompt based on use case
        if use_case == "pdf_kb":
            prompt = self._build_pdf_prompt(query, candidates, matching_guidance)
        else:
            prompt = self._build_excel_prompt(query, candidates, matching_guidance)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at assessing relevance between queries and documents. Provide rankings in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result_text = response.choices[0].message.content
            rankings = json.loads(result_text)
            
            # Apply rankings
            reranked = self._apply_rankings(candidates, rankings, top_k)
            
            return reranked
            
        except Exception as e:
            print(f"LLM reranking failed: {str(e)}")
            # Fallback: return original candidates
            return candidates[:top_k]
    
    def _build_pdf_prompt(self, query: str, candidates: List[Dict], matching_guidance: str = "") -> str:
        """Build prompt for PDF knowledge base matching"""
        prompt = ""
        
        # Add few-shot context if available
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
            text = candidate.get('text', '')[:500]  # Limit text length
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
        """Build prompt for Excel knowledge base (keyword/failure) matching"""
        prompt = ""
        
        # Add few-shot context if available
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
        """
        Apply LLM rankings to candidates
        
        Args:
            candidates: Original candidates
            rankings: Rankings from LLM
            top_k: Number of results to return
            
        Returns:
            Reranked candidates
        """
        try:
            ranked_indices = rankings.get('rankings', [])
            relevance_scores = rankings.get('relevance_scores', [])
            reasoning = rankings.get('reasoning', '')
            
            reranked = []
            for i, idx in enumerate(ranked_indices[:top_k]):
                # Convert 1-indexed to 0-indexed
                candidate_idx = idx - 1
                
                if 0 <= candidate_idx < len(candidates):
                    candidate = candidates[candidate_idx].copy()
                    candidate['llm_rank'] = i + 1
                    
                    if i < len(relevance_scores):
                        candidate['llm_relevance_score'] = relevance_scores[i] / 100.0
                    
                    if i == 0:  # Add reasoning to top result
                        candidate['llm_reasoning'] = reasoning
                    
                    reranked.append(candidate)
            
            return reranked
            
        except Exception as e:
            print(f"Error applying rankings: {str(e)}")
            return candidates[:top_k]
