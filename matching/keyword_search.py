"""
Keyword Search Module
Implements BM25 algorithm for keyword-based matching
"""
from rank_bm25 import BM25Okapi
from typing import List, Dict
import re


class KeywordSearcher:
    """BM25-based keyword search"""
    
    def __init__(self):
        self.bm25 = None
        self.documents = []
        self.tokenized_docs = []
    
    def index_documents(self, documents: List[Dict]) -> None:
        """
        Index documents for keyword search
        
        Args:
            documents: List of document dictionaries
        """
        self.documents = documents
        
        # Extract and tokenize text from documents
        self.tokenized_docs = []
        for doc in documents:
            text = doc.get('text', '')
            tokens = self._tokenize(text)
            self.tokenized_docs.append(tokens)
        
        # Create BM25 index
        if self.tokenized_docs:
            self.bm25 = BM25Okapi(self.tokenized_docs)
    
    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        Search for documents matching the query
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of matching documents with BM25 scores
        """
        if self.bm25 is None:
            return []
        
        # Tokenize query
        query_tokens = self._tokenize(query)
        
        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        # Format results
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # Only include non-zero scores
                result = {
                    'document': self.documents[idx],
                    'bm25_score': float(scores[idx]),
                    'index': idx
                }
                results.append(result)
        
        return results
    
    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text for BM25
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
        # Convert to lowercase
        text = text.lower()
        
        # Split on non-alphanumeric characters
        tokens = re.findall(r'\b\w+\b', text)
        
        return tokens
    
    def get_statistics(self) -> Dict:
        """Get indexing statistics"""
        return {
            'total_documents': len(self.documents),
            'indexed': self.bm25 is not None,
            'avg_tokens_per_doc': sum(len(doc) for doc in self.tokenized_docs) / len(self.tokenized_docs) if self.tokenized_docs else 0
        }
