"""
Hybrid Matching Module
Combines semantic search (embeddings) and keyword search (BM25)
"""
from typing import List, Dict
from config import SEMANTIC_WEIGHT, KEYWORD_WEIGHT
import numpy as np


class HybridMatcher:
    """Combines semantic and keyword search with weighted scoring"""
    
    def __init__(self, semantic_weight: float = SEMANTIC_WEIGHT, 
                 keyword_weight: float = KEYWORD_WEIGHT):
        """
        Initialize hybrid matcher
        
        Args:
            semantic_weight: Weight for semantic similarity scores
            keyword_weight: Weight for keyword (BM25) scores
        """
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
    
    def combine_results(self, semantic_results: List[Dict], 
                       keyword_results: List[Dict],
                       top_k: int = 10) -> List[Dict]:
        """
        Combine and rank results from semantic and keyword search
        
        Args:
            semantic_results: Results from vector search
            keyword_results: Results from BM25 search
            top_k: Number of final results to return
            
        Returns:
            Combined and ranked results
        """
        # Create a dictionary to store combined scores
        combined_scores = {}
        doc_map = {}
        
        # Process semantic results
        semantic_scores = self._normalize_scores(
            [r['score'] for r in semantic_results]
        )
        
        for i, result in enumerate(semantic_results):
            doc_id = result.get('id')
            if doc_id:
                combined_scores[doc_id] = semantic_scores[i] * self.semantic_weight
                doc_map[doc_id] = result
        
        # Process keyword results
        if keyword_results:
            bm25_scores = self._normalize_scores(
                [r['bm25_score'] for r in keyword_results]
            )
            
            for i, result in enumerate(keyword_results):
                doc = result['document']
                doc_id = doc.get('chunk_id') or doc.get('entry_id')
                
                if doc_id:
                    if doc_id in combined_scores:
                        # Add to existing score
                        combined_scores[doc_id] += bm25_scores[i] * self.keyword_weight
                    else:
                        # New document from keyword search
                        combined_scores[doc_id] = bm25_scores[i] * self.keyword_weight
                        
                        # Create result format matching semantic results
                        doc_map[doc_id] = {
                            'id': doc_id,
                            'text': doc.get('text', ''),
                            'metadata': {k: v for k, v in doc.items() if k != 'text'}
                        }
        
        # Sort by combined score
        sorted_ids = sorted(combined_scores.keys(), 
                          key=lambda x: combined_scores[x], 
                          reverse=True)
        
        # Format final results
        final_results = []
        for doc_id in sorted_ids[:top_k]:
            result = doc_map[doc_id].copy()
            result['combined_score'] = float(combined_scores[doc_id])
            final_results.append(result)
        
        return final_results
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """
        Normalize scores to 0-1 range using min-max normalization
        
        Args:
            scores: List of scores to normalize
            
        Returns:
            Normalized scores
        """
        if not scores:
            return []
        
        scores_array = np.array(scores)
        min_score = scores_array.min()
        max_score = scores_array.max()
        
        # Avoid division by zero
        if max_score == min_score:
            return [1.0] * len(scores)
        
        normalized = (scores_array - min_score) / (max_score - min_score)
        return normalized.tolist()
    
    def get_weights(self) -> Dict:
        """Get current weights"""
        return {
            'semantic_weight': self.semantic_weight,
            'keyword_weight': self.keyword_weight
        }
    
    def set_weights(self, semantic_weight: float, keyword_weight: float) -> None:
        """
        Update weights
        
        Args:
            semantic_weight: New semantic weight
            keyword_weight: New keyword weight
        """
        # Normalize weights to sum to 1
        total = semantic_weight + keyword_weight
        self.semantic_weight = semantic_weight / total
        self.keyword_weight = keyword_weight / total
