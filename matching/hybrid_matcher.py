"""
Hybrid Matching Module
Combines semantic search (embeddings) and keyword search (BM25)
using Reciprocal Rank Fusion (RRF) — a rank-based fusion method that is
robust to score-distribution differences between retrieval methods.
"""
from typing import List, Dict
from config import SEMANTIC_WEIGHT, KEYWORD_WEIGHT

# RRF smoothing constant — standard value from the original RRF paper (Cormack+ 2009).
# Higher k smooths rank differences; 60 is the widely-adopted default.
RRF_K = 60


class HybridMatcher:
    """Combines semantic and keyword search with weighted Reciprocal Rank Fusion"""
    
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
        Combine and rank results from semantic and keyword search using
        weighted Reciprocal Rank Fusion.

        RRF score for a document = sum over each list L of:
            weight_L * (1 / (RRF_K + rank_in_L))

        This is rank-based, so it doesn't depend on the raw score magnitudes
        from either method — eliminating the min-max normalization instability.
        
        Args:
            semantic_results: Results from vector search
            keyword_results: Results from BM25 search
            top_k: Number of final results to return
            
        Returns:
            Combined and ranked results
        """
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict] = {}
        
        # RRF contributions from semantic results (rank is 1-based)
        for rank, result in enumerate(semantic_results, start=1):
            doc_id = result.get('id')
            if not doc_id:
                continue
            rrf_scores[doc_id] = self.semantic_weight / (RRF_K + rank)
            doc_map[doc_id] = result
        
        # RRF contributions from keyword results
        if keyword_results:
            for rank, result in enumerate(keyword_results, start=1):
                doc = result['document']
                doc_id = doc.get('chunk_id') or doc.get('entry_id')
                if not doc_id:
                    continue

                rrf_contribution = self.keyword_weight / (RRF_K + rank)

                if doc_id in rrf_scores:
                    rrf_scores[doc_id] += rrf_contribution
                else:
                    rrf_scores[doc_id] = rrf_contribution
                    doc_map[doc_id] = {
                        'id': doc_id,
                        'text': doc.get('text', ''),
                        'metadata': {k: v for k, v in doc.items() if k != 'text'}
                    }
        
        # Sort by fused RRF score
        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
        
        final_results = []
        for doc_id in sorted_ids[:top_k]:
            result = doc_map[doc_id].copy()
            result['combined_score'] = float(rrf_scores[doc_id])
            final_results.append(result)
        
        return final_results
    
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
        total = semantic_weight + keyword_weight
        self.semantic_weight = semantic_weight / total
        self.keyword_weight = keyword_weight / total
