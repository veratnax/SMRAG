"""
Embedder Module
Handles text embedding using OpenAI API
"""
from openai import OpenAI
from typing import List, Dict
import numpy as np
from config import EMBEDDING_MODEL
import time


class Embedder:
    """Generate embeddings using OpenAI API"""
    
    def __init__(self, api_key: str):
        """
        Initialize embedder with OpenAI API key
        
        Args:
            api_key: OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)
        self.model = EMBEDDING_MODEL
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            # Handle empty text
            if not text or not text.strip():
                raise ValueError("Cannot embed empty text")
            
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            raise Exception(f"Error generating embedding: {str(e)}")
    
    def embed_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process in one API call
            
        Returns:
            List of embedding vectors
        """
        full_embeddings = [None] * len(texts)
        
        # Filter out empty texts and track indices
        valid_items = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_items.append((i, text))
        
        if not valid_items:
            return full_embeddings
        
        # Token-safe batching limits
        max_tokens_per_request = 250000  # Keep margin below API limit
        max_items_per_request = max(1, batch_size)
        
        batches = []
        current_batch = []
        current_tokens = 0
        
        for idx, text in valid_items:
            est_tokens = self._estimate_tokens(text)
            
            # Oversized single item goes alone and relies on recursive fallback
            if est_tokens >= max_tokens_per_request and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            if (
                current_batch
                and (len(current_batch) >= max_items_per_request or current_tokens + est_tokens > max_tokens_per_request)
            ):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            current_batch.append((idx, text))
            current_tokens += est_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        for batch_num, batch in enumerate(batches, 1):
            batch_indices = [idx for idx, _ in batch]
            batch_texts = [text for _, text in batch]
            
            batch_embeddings = self._embed_with_retry(batch_texts)
            
            if len(batch_embeddings) != len(batch_indices):
                print(f"Embedding size mismatch in batch {batch_num}; marking batch as failed.")
                batch_embeddings = [None] * len(batch_indices)
            
            for idx, emb in zip(batch_indices, batch_embeddings):
                full_embeddings[idx] = emb
            
            if batch_num < len(batches):
                time.sleep(0.1)
        
        return full_embeddings

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate used for request budgeting."""
        words = len(text.split())
        return max(1, int(words * 1.35) + 20)

    def _embed_with_retry(self, batch_texts: List[str], depth: int = 0, max_depth: int = 8) -> List[List[float]]:
        """Embed a batch and split recursively if request size limits are hit."""
        if not batch_texts:
            return []
        
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=batch_texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            err_text = str(e)
            is_size_error = "max_tokens_per_request" in err_text or "Requested" in err_text and "max" in err_text
            
            if is_size_error and len(batch_texts) > 1 and depth < max_depth:
                mid = len(batch_texts) // 2
                left = self._embed_with_retry(batch_texts[:mid], depth + 1, max_depth)
                right = self._embed_with_retry(batch_texts[mid:], depth + 1, max_depth)
                return left + right
            
            print(f"Error in embedding batch (size={len(batch_texts)}): {err_text}")
            return [None] * len(batch_texts)
    
    def cosine_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0 to 1)
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))

    def combine_and_normalize(self, guidance_embedding: List[float], query_embedding: List[float],
                              guidance_weight: float = 0.3) -> List[float]:
        """
        Combine guidance and query embeddings with a weight, then L2-normalize.
        Used when guidance is embedded once per session and combined with each query embedding.

        Args:
            guidance_embedding: Vector from embedding the guidance text once
            query_embedding: Vector from embedding the query text only
            guidance_weight: Weight for guidance (0-1); rest is query. Default 0.3.

        Returns:
            Normalized combined vector as list (for vector search).
        """
        g = np.array(guidance_embedding, dtype=float)
        q = np.array(query_embedding, dtype=float)
        if g.shape != q.shape:
            return query_embedding
        combined = guidance_weight * g + (1.0 - guidance_weight) * q
        norm = np.linalg.norm(combined)
        if norm == 0:
            return query_embedding
        return (combined / norm).tolist()
