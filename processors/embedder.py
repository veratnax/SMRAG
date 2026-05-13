"""
Embedder Module
Handles text embedding using OpenAI API
"""
from openai import OpenAI
from typing import List, Dict
import numpy as np
from config import EMBEDDING_MODEL
import time
import re


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
            safe_texts = [t.encode('utf-8', errors='replace').decode('utf-8') for t in batch_texts]
            response = self.client.embeddings.create(
                model=self.model,
                input=safe_texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            err_text = str(e)
            lower_err = err_text.lower()
            is_size_error = any(token in lower_err for token in [
                "max_tokens_per_request",
                "maximum input length",
                "maximum context length",
                "invalid 'input",
                "too many tokens",
            ]) or ("requested" in lower_err and "max" in lower_err)
            
            if is_size_error and len(batch_texts) > 1 and depth < max_depth:
                mid = len(batch_texts) // 2
                left = self._embed_with_retry(batch_texts[:mid], depth + 1, max_depth)
                right = self._embed_with_retry(batch_texts[mid:], depth + 1, max_depth)
                return left + right

            # Single oversized text fallback: split into semantic-ish chunks and
            # ensemble the chunk embeddings into one query embedding.
            if is_size_error and len(batch_texts) == 1 and depth < max_depth:
                text = batch_texts[0]
                chunked = self._split_text_for_embedding(text, max_chunks=5, target_chars=4500)
                if len(chunked) > 1:
                    print(
                        f"Embedding input too long; splitting into {len(chunked)} chunks "
                        "and ensembling embeddings."
                    )
                    chunk_embeddings = self._embed_with_retry(chunked, depth + 1, max_depth)
                    valid = [np.array(e, dtype=float) for e in chunk_embeddings if e is not None]
                    if valid:
                        combined = np.mean(valid, axis=0)
                        norm = np.linalg.norm(combined)
                        if norm > 0:
                            combined = combined / norm
                        return [combined.tolist()]
            
            print(f"Error in embedding batch (size={len(batch_texts)}): {err_text}")
            return [None] * len(batch_texts)

    @staticmethod
    def _split_text_for_embedding(text: str, max_chunks: int = 5, target_chars: int = 4500) -> List[str]:
        """
        Split oversized text into 2-5 chunks, trying paragraph boundaries first.
        Falls back to fixed-size windows if needed.
        """
        clean = " ".join((text or "").split())
        if not clean:
            return []
        if len(clean) <= target_chars:
            return [clean]

        # First-pass: paragraph-ish split on punctuation + capitalization.
        parts = []
        current = []
        current_len = 0
        sentences = re.split(r'(?<=[\.\!\?])\s+(?=[A-Z0-9])', clean)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            add_len = len(sent) + (1 if current else 0)
            if current and current_len + add_len > target_chars:
                parts.append(" ".join(current))
                current = [sent]
                current_len = len(sent)
            else:
                current.append(sent)
                current_len += add_len
        if current:
            parts.append(" ".join(current))

        # Fallback to fixed windows if sentence splitting didn't reduce enough.
        if len(parts) == 1 and len(parts[0]) > target_chars:
            parts = []
            start = 0
            step = max(1000, int(target_chars * 0.85))
            while start < len(clean):
                parts.append(clean[start:start + target_chars])
                start += step

        # Keep bounded chunk count by merging tail chunks.
        if len(parts) > max_chunks:
            merged = parts[:max_chunks - 1]
            merged.append(" ".join(parts[max_chunks - 1:]))
            parts = merged

        return [p for p in parts if p.strip()]
    
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
