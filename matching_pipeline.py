"""
Main Matching Pipeline
Orchestrates the entire matching workflow
"""
from typing import List, Dict, Optional
from processors import PDFProcessor, ExcelProcessor, Embedder, IntelligentChunker
from matching import KeywordSearcher, HybridMatcher, LLMReranker
from utils.vector_store import VectorStore
from qa.qa_learner import QALearner
from config import DEFAULT_TOP_N, GUIDANCE_EMBEDDING_WEIGHT


class MatchingPipeline:
    """Complete matching pipeline for both use cases"""
    
    def __init__(self, api_key: str):
        """
        Initialize pipeline with OpenAI API key
        
        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        self.embedder = Embedder(api_key)
        self.vector_store = VectorStore()
        self.keyword_searcher = KeywordSearcher()
        self.hybrid_matcher = HybridMatcher()
        self.llm_reranker = LLMReranker(api_key)
        self.qa_learner = QALearner()
        self.intelligent_chunker = IntelligentChunker(api_key)
        
        self.knowledge_base = []
        self.use_case = None
        self.chunking_strategy = None
    
    def setup_pdf_knowledge_base(self, pdf_path: str, use_intelligent_chunking: bool = True,
                                 user_context: Optional[str] = None,
                                 kb_context_prompt: Optional[str] = None) -> Dict:
        """
        Set up PDF knowledge base
        
        Args:
            pdf_path: Path to PDF file
            use_intelligent_chunking: Use LLM-powered adaptive chunking
            user_context: Optional user description of document
            kb_context_prompt: Optional prompt describing KB context for embeddings
            
        Returns:
            Statistics about processing
        """
        self.use_case = "pdf_kb"
        
        if use_intelligent_chunking:
            # Intelligent chunking with LLM analysis
            print("Analyzing PDF structure with LLM...")
            self.chunking_strategy = self.intelligent_chunker.analyze_pdf_structure(
                pdf_path, 
                user_context=user_context
            )
            
            print(f"Detected: {self.chunking_strategy.get('document_type', 'unknown')} document")
            print(f"Strategy: {self.chunking_strategy.get('recommended_strategy', 'fixed_size')}")
            
            print("Chunking PDF with intelligent strategy...")
            chunks = self.intelligent_chunker.chunk_with_strategy(pdf_path, self.chunking_strategy)
            
            stats = self.intelligent_chunker.get_chunking_summary(chunks)
        else:
            # Original simple chunking
            print("Processing PDF with fixed-size chunking...")
            pdf_processor = PDFProcessor()
            chunks = pdf_processor.process_pdf(pdf_path)
            stats = pdf_processor.get_statistics()
            self.chunking_strategy = {'recommended_strategy': 'fixed_size'}
        
        # Generate embeddings
        print(f"Generating embeddings for {len(chunks)} chunks...")
        texts = [self._build_kb_embedding_text(chunk['text'], kb_context_prompt) for chunk in chunks]
        embeddings = self.embedder.embed_batch(texts)
        embeddings_created = len([e for e in embeddings if e is not None])
        embeddings_failed = len(embeddings) - embeddings_created
        if embeddings_created == 0:
            raise Exception(
                "Failed to create embeddings for all PDF chunks. "
                "Try fixed-size chunking or reduce chunk size/context prompt length."
            )
        
        # Store in vector database
        print("Storing in vector database...")
        self.vector_store.create_collection("pdf_knowledge_base")
        self.vector_store.add_documents(chunks, embeddings)
        
        # Index for keyword search
        print("Indexing for keyword search...")
        self.keyword_searcher.index_documents(chunks)
        
        self.knowledge_base = chunks
        
        stats['embeddings_created'] = embeddings_created
        stats['embeddings_failed'] = embeddings_failed
        stats['chunking_strategy'] = self.chunking_strategy
        
        return stats
    
    def setup_excel_knowledge_base(self, excel_path: str, key_column: str, 
                                   value_column: str, 
                                   additional_columns: Optional[List[str]] = None,
                                   kb_context_prompt: Optional[str] = None) -> Dict:
        """
        Set up Excel knowledge base
        
        Args:
            excel_path: Path to Excel file
            key_column: Key column name
            value_column: Value column name
            additional_columns: Optional additional context columns
            kb_context_prompt: Optional prompt describing KB context for embeddings
            
        Returns:
            Statistics about processing
        """
        self.use_case = "excel_kb"
        
        # Process Excel
        print("Processing Excel...")
        excel_processor = ExcelProcessor()
        excel_processor.load_excel(excel_path)
        entries = excel_processor.process_knowledge_base(
            key_column, value_column, additional_columns
        )
        
        # Generate embeddings
        print(f"Generating embeddings for {len(entries)} entries...")
        texts = [self._build_kb_embedding_text(entry['text'], kb_context_prompt) for entry in entries]
        embeddings = self.embedder.embed_batch(texts)
        embeddings_created = len([e for e in embeddings if e is not None])
        embeddings_failed = len(embeddings) - embeddings_created
        if embeddings_created == 0:
            raise Exception(
                "Failed to create embeddings for all Excel KB entries. "
                "Check input size/content and try again."
            )
        
        # Store in vector database
        print("Storing in vector database...")
        self.vector_store.create_collection("excel_knowledge_base")
        self.vector_store.add_documents(entries, embeddings)
        
        # Index for keyword search
        print("Indexing for keyword search...")
        self.keyword_searcher.index_documents(entries)
        
        self.knowledge_base = entries
        
        stats = excel_processor.get_statistics()
        stats['entries_processed'] = len(entries)
        stats['embeddings_created'] = embeddings_created
        stats['embeddings_failed'] = embeddings_failed
        
        return stats
    
    def process_queries(self, query_excel_path: str, query_column: str,
                       top_n: int = DEFAULT_TOP_N,
                       use_llm_reranking: bool = True,
                       query_offset: int = 0,
                       query_limit: Optional[int] = None,
                       matching_guidance: Optional[str] = None) -> List[Dict]:
        """
        Process queries and find matches
        
        Args:
            query_excel_path: Path to query Excel file
            query_column: Query column name
            top_n: Number of matches per query
            use_llm_reranking: Whether to use LLM re-ranking
            query_offset: Starting index for queries (for staged processing)
            query_limit: Maximum number of queries to process (None = all)
            matching_guidance: Optional prompt describing how matching should be evaluated
            
        Returns:
            List of results for each query
        """
        if not self.knowledge_base:
            raise Exception("Knowledge base not set up. Call setup_pdf_knowledge_base or setup_excel_knowledge_base first.")
        
        # Load queries
        print("Loading queries...")
        excel_processor = ExcelProcessor()
        excel_processor.load_excel(query_excel_path)
        queries = excel_processor.process_queries(query_column)
        
        # Apply offset/limit (used for staged processing + QA-first workflow)
        if query_offset < 0:
            query_offset = 0

        if query_offset > len(queries):
            queries = []
        else:
            queries = queries[query_offset:]

        if query_limit is not None:
            if query_limit < 0:
                query_limit = 0
            queries = queries[:query_limit]
        
        print(f"Processing {len(queries)} queries...")
        results = []

        # Optimize: embed guidance once per session; batch-embed all queries (query text only)
        guidance_embedding = None
        if matching_guidance and matching_guidance.strip():
            try:
                print("Embedding matching guidance once for this session...")
                guidance_embedding = self.embedder.embed_text(
                    "Matching guidance: " + matching_guidance.strip()
                )
            except Exception as e:
                print(f"Warning: could not embed guidance ({e}); continuing with query-only embeddings.")

        query_only_texts = [q["query"] for q in queries]
        print(f"Batch-embedding {len(query_only_texts)} queries...")
        all_query_embeddings = self.embedder.embed_batch(query_only_texts)

        for i, query_item in enumerate(queries):
            query = query_item["query"]

            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(queries)} queries...")

            try:
                # Use combined (guidance + query) or query-only embedding for semantic search
                raw_embedding = all_query_embeddings[i] if i < len(all_query_embeddings) else None
                if raw_embedding is None:
                    raise Exception("Query embedding failed (empty or API error).")
                if guidance_embedding is not None:
                    query_embedding = self.embedder.combine_and_normalize(
                        guidance_embedding, raw_embedding, GUIDANCE_EMBEDDING_WEIGHT
                    )
                else:
                    query_embedding = raw_embedding

                # Semantic search
                semantic_results = self.vector_store.search(query_embedding, top_k=top_n * 2)

                # Keyword search
                keyword_results = self.keyword_searcher.search(query, top_k=top_n * 2)

                # Hybrid matching
                hybrid_results = self.hybrid_matcher.combine_results(
                    semantic_results, keyword_results, top_k=top_n * 2
                )

                # LLM re-ranking (optional) — still receives full matching_guidance for ranking
                if use_llm_reranking and len(hybrid_results) > 0:
                    final_results = self.llm_reranker.rerank(
                        query,
                        hybrid_results,
                        top_k=top_n,
                        use_case=self.use_case,
                        matching_guidance=matching_guidance
                    )
                else:
                    final_results = hybrid_results[:top_n]

                # Format matches
                matches = self._format_matches(final_results)

                results.append({
                    "query_id": query_item["query_id"],
                    "query": query,
                    "row_number": query_item["row_number"],
                    "matches": matches,
                    "num_matches": len(matches),
                })

            except Exception as e:
                print(f"Error processing query '{query}': {str(e)}")
                results.append({
                    "query_id": query_item["query_id"],
                    "query": query,
                    "row_number": query_item["row_number"],
                    "matches": [],
                    "num_matches": 0,
                    "error": str(e),
                })
        
        print("Query processing complete!")
        return results
    
    def _format_matches(self, results: List[Dict]) -> List[Dict]:
        """Format match results for output"""
        matches = []
        
        for i, result in enumerate(results, 1):
            metadata = result.get('metadata', {})
            
            match = {
                'rank': i,
                'text': result.get('text', '')[:500],  # Limit text length
                'combined_score': result.get('combined_score', 0),
            }
            
            # Add use-case specific fields
            if self.use_case == "pdf_kb":
                match['page_number'] = metadata.get('page_number', 'N/A')
                match['chunk_id'] = metadata.get('chunk_id', '')
            else:  # excel_kb
                match['key'] = metadata.get('key', '')
                match['definition'] = metadata.get('definition', '')
                match['row_number'] = metadata.get('row_number', 'N/A')
            
            # Add LLM scores if available
            if 'llm_relevance_score' in result:
                match['llm_relevance_score'] = result['llm_relevance_score']
            
            if 'llm_reasoning' in result and i == 1:
                match['llm_reasoning'] = result['llm_reasoning']
            
            matches.append(match)
        
        return matches

    def _build_kb_embedding_text(self, text: str, kb_context_prompt: Optional[str]) -> str:
        """Build embedding input for knowledge-base documents."""
        if kb_context_prompt and kb_context_prompt.strip():
            return f"Knowledge base context: {kb_context_prompt.strip()}\n\nDocument: {text}"
        return text

    def _build_query_embedding_text(self, query: str, matching_guidance: Optional[str]) -> str:
        """Build embedding input for query text."""
        if matching_guidance and matching_guidance.strip():
            return f"Matching guidance: {matching_guidance.strip()}\n\nQuery: {query}"
        return query
    
    def get_statistics(self) -> Dict:
        """Get pipeline statistics"""
        return {
            'use_case': self.use_case,
            'knowledge_base_size': len(self.knowledge_base),
            'vector_store_count': self.vector_store.get_collection_count(),
            'keyword_index': self.keyword_searcher.get_statistics()
        }
    
    def apply_qa_learnings(self, qa_session_id: str) -> Dict:
        """
        Apply learnings from QA feedback to improve matching
        
        Args:
            qa_session_id: QA session identifier
            
        Returns:
            Dictionary with applied changes and analysis
        """
        # Analyze QA feedback
        analysis = self.qa_learner.analyze_qa_session(qa_session_id)
        
        changes_applied = {
            'weights_adjusted': False,
            'few_shot_enabled': False,
            'analysis': analysis
        }
        
        # Apply weight adjustments if suggested
        if analysis['suggested_weights'] and analysis['confidence'] > 0.3:
            weights = analysis['suggested_weights']
            self.hybrid_matcher.set_weights(
                weights['semantic_weight'],
                weights['keyword_weight']
            )
            changes_applied['weights_adjusted'] = True
            changes_applied['new_weights'] = weights
        
        # Apply few-shot learning from accepted matches and rejected corrections
        few_shot_context = self.qa_learner.build_few_shot_context(
            qa_session_id, 
            max_examples=3
        )
        if few_shot_context:
            self.llm_reranker.set_few_shot_context(few_shot_context)
            changes_applied['few_shot_enabled'] = True
            changes_applied['num_examples'] = len(analysis['good_examples']) + len(analysis.get('correction_examples', []))
        
        return changes_applied
