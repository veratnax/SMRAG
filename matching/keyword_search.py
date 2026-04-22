"""
Keyword Search Module
Implements BM25 algorithm for keyword-based matching
"""
from rank_bm25 import BM25Okapi
from typing import List, Dict
import re


# Porter-style suffix rules for lightweight stemming (no external dependency)
_STEP2_SUFFIXES = [
    ("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"),
    ("izer", "ize"), ("iser", "ise"), ("abli", "able"), ("alli", "al"),
    ("entli", "ent"), ("eli", "e"), ("ousli", "ous"), ("ization", "ize"),
    ("isation", "ise"), ("ation", "ate"), ("ator", "ate"), ("alism", "al"),
    ("iveness", "ive"), ("fulness", "ful"), ("ousness", "ous"), ("aliti", "al"),
    ("iviti", "ive"), ("biliti", "ble"),
]

STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "am", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "shall", "should", "may", "might", "must", "can", "could",
    "not", "no", "nor", "so", "if", "then", "than", "that", "this",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who", "whom", "when", "where", "how", "why",
    "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "also", "just", "about",
    "above", "after", "again", "any", "because", "before", "below",
    "between", "during", "into", "out", "over", "through", "under",
    "until", "up", "very", "too", "here", "there",
})


def _simple_stem(word: str) -> str:
    """Lightweight English stemmer — handles common suffixes without nltk."""
    if len(word) <= 3:
        return word

    # Step 1: plural / past-tense
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "i"
    elif word.endswith("sses"):
        word = word[:-2]
    elif word.endswith("ss"):
        pass
    elif word.endswith("s") and not word.endswith("us") and not word.endswith("ss"):
        word = word[:-1]

    if word.endswith("eed"):
        if len(word) > 4:
            word = word[:-1]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]

    # Step 2: derivational suffixes
    for suffix, replacement in _STEP2_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) > 1:
            word = word[: -len(suffix)] + replacement
            break

    # Step 3: common trailing patterns
    for suffix in ("ful", "ness", "ment", "ous", "ive", "ize", "ise", "ent", "ant", "ible", "able"):
        if word.endswith(suffix) and len(word) - len(suffix) > 2:
            word = word[: -len(suffix)]
            break

    return word


class KeywordSearcher:
    """BM25-based keyword search with stopword removal and stemming"""
    
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
        Tokenize text for BM25 with stopword removal and stemming.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of stemmed, filtered tokens
        """
        text = text.lower()
        raw_tokens = re.findall(r'\b\w+\b', text)
        return [_simple_stem(t) for t in raw_tokens if t not in STOPWORDS and len(t) > 1]
    
    def get_statistics(self) -> Dict:
        """Get indexing statistics"""
        return {
            'total_documents': len(self.documents),
            'indexed': self.bm25 is not None,
            'avg_tokens_per_doc': sum(len(doc) for doc in self.tokenized_docs) / len(self.tokenized_docs) if self.tokenized_docs else 0
        }
