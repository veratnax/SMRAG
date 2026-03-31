"""
Vector Store Module
Handles vector storage and retrieval using ChromaDB
"""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
import os
from config import VECTOR_STORE_PATH, COLLECTION_NAME


class VectorStore:
    """Manage vector storage and retrieval"""
    
    def __init__(self, persist_directory: str = VECTOR_STORE_PATH):
        """
        Initialize vector store
        
        Args:
            persist_directory: Directory to persist the database
        """
        # Create directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        self.collection = None
        self.collection_name = COLLECTION_NAME
    
    def create_collection(self, collection_name: Optional[str] = None) -> None:
        """
        Create or get a collection
        
        Args:
            collection_name: Name of the collection (uses default if None)
        """
        if collection_name:
            self.collection_name = collection_name
        
        # Delete existing collection if it exists (fresh start)
        try:
            self.client.delete_collection(name=self.collection_name)
        except:
            pass
        
        # Create new collection
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )
    
    def add_documents(self, documents: List[Dict], embeddings: List[List[float]]) -> None:
        """
        Add documents with embeddings to the collection
        
        Args:
            documents: List of document dictionaries with metadata
            embeddings: List of embedding vectors
        """
        if self.collection is None:
            raise Exception("No collection created. Call create_collection first.")
        
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents must match number of embeddings")
        
        # Prepare data for ChromaDB
        ids = []
        texts = []
        metadatas = []
        valid_embeddings = []
        
        for i, (doc, emb) in enumerate(zip(documents, embeddings)):
            if emb is None:  # Skip documents with failed embeddings
                continue
            
            # Generate unique ID
            doc_id = doc.get('chunk_id') or doc.get('entry_id') or f"doc_{i}"
            ids.append(doc_id)
            
            # Extract text
            texts.append(doc.get('text', ''))
            
            # Prepare metadata (ChromaDB only accepts simple types)
            metadata = {}
            for key, value in doc.items():
                if key not in ['text', 'embedding']:
                    # Convert to string or number
                    if isinstance(value, (str, int, float, bool)):
                        metadata[key] = value
                    else:
                        metadata[key] = str(value)
            
            metadatas.append(metadata)
            valid_embeddings.append(emb)
        
        # Add to collection in batches
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            self.collection.add(
                ids=ids[i:i+batch_size],
                embeddings=valid_embeddings[i:i+batch_size],
                documents=texts[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size]
            )
    
    def search(self, query_embedding: List[float], top_k: int = 10) -> List[Dict]:
        """
        Search for similar documents
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of matching documents with scores
        """
        if self.collection is None:
            raise Exception("No collection created. Call create_collection first.")
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        matches = []
        for i in range(len(results['ids'][0])):
            match = {
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'distance': results['distances'][0][i],
                'score': 1 - results['distances'][0][i],  # Convert distance to similarity
                'metadata': results['metadatas'][0][i]
            }
            matches.append(match)
        
        return matches
    
    def get_collection_count(self) -> int:
        """Get number of documents in collection"""
        if self.collection is None:
            return 0
        return self.collection.count()
    
    def reset(self) -> None:
        """Reset the vector store"""
        try:
            self.client.delete_collection(name=self.collection_name)
        except:
            pass
        self.collection = None
