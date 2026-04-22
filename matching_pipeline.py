"""
Main Matching Pipeline
Orchestrates the entire matching workflow
"""
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from processors import PDFProcessor, ExcelProcessor, Embedder, IntelligentChunker
from matching import KeywordSearcher, HybridMatcher, LLMReranker
from utils.vector_store import VectorStore
from qa.qa_learner import QALearner
from config import (DEFAULT_TOP_N, GUIDANCE_EMBEDDING_WEIGHT, RETRIEVAL_POOL_SIZE,
                     LLM_MODEL, QUERY_EXPANSION_MAX_WORDS, QUERY_EXPANSION_CODE_PATTERN)
import json
import re


class MatchingPipeline:
    """Complete matching pipeline for both use cases"""
    
    def __init__(self, api_key: str):
        """
        Initialize pipeline with OpenAI API key
        
        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        self.llm_client = OpenAI(api_key=api_key)
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
        self._expanded_queries_cache: Dict[str, List[str]] = {}
    
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
    
    @staticmethod
    def _needs_expansion(query: str) -> bool:
        """Return True if a query is short/vague enough to benefit from LLM expansion."""
        word_count = len(query.split())
        if word_count > QUERY_EXPANSION_MAX_WORDS:
            return False
        if re.search(QUERY_EXPANSION_CODE_PATTERN, query):
            return False
        return True

    def process_queries(self, query_excel_path: str, query_column: str,
                       top_n: int = DEFAULT_TOP_N,
                       use_llm_reranking: bool = True,
                       use_query_expansion: bool = True,
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
            use_query_expansion: Whether to expand short/vague queries for better keyword recall
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

        # Query expansion: expand all queries when enabled
        if use_query_expansion:
            print(f"Query expansion: expanding all {len(query_only_texts)} queries…")
            self._expand_queries_batch(query_only_texts)
        else:
            print("Query expansion: disabled by user")

        # --- Phase 1: retrieval + hybrid fusion (CPU-bound, fast) -----------
        retrieval_k = max(RETRIEVAL_POOL_SIZE, top_n * 2)
        hybrid_per_query: List[Dict] = []  # index-aligned with queries

        for i, query_item in enumerate(queries):
            query = query_item["query"]
            try:
                raw_embedding = all_query_embeddings[i] if i < len(all_query_embeddings) else None
                if raw_embedding is None:
                    raise Exception("Query embedding failed (empty or API error).")
                if guidance_embedding is not None:
                    query_embedding = self.embedder.combine_and_normalize(
                        guidance_embedding, raw_embedding, GUIDANCE_EMBEDDING_WEIGHT
                    )
                else:
                    query_embedding = raw_embedding

                semantic_results = self.vector_store.search(query_embedding, top_k=retrieval_k)

                expanded_variants = self._expanded_queries_cache.get(query, [query])
                keyword_results = []
                seen_keyword_ids = set()
                for variant in expanded_variants:
                    for result in self.keyword_searcher.search(variant, top_k=retrieval_k):
                        doc = result['document']
                        doc_id = doc.get('chunk_id') or doc.get('entry_id')
                        if doc_id and doc_id not in seen_keyword_ids:
                            seen_keyword_ids.add(doc_id)
                            keyword_results.append(result)
                keyword_results.sort(key=lambda r: r['bm25_score'], reverse=True)
                keyword_results = keyword_results[:retrieval_k]

                hybrid_results = self.hybrid_matcher.combine_results(
                    semantic_results, keyword_results, top_k=retrieval_k
                )
                hybrid_per_query.append({"ok": True, "hybrid": hybrid_results})
            except Exception as e:
                hybrid_per_query.append({"ok": False, "error": str(e)})

        print(f"  Retrieval done for {len(queries)} queries. Starting reranking…")

        # --- Phase 2: LLM reranking (I/O-bound) — parallelized ------------
        MAX_RERANK_WORKERS = 10

        def _rerank_one(idx: int):
            """Rerank a single query's hybrid results (runs in thread)."""
            query_item = queries[idx]
            query = query_item["query"]
            entry = hybrid_per_query[idx]

            if not entry["ok"]:
                return idx, {
                    "query_id": query_item["query_id"],
                    "query": query,
                    "row_number": query_item["row_number"],
                    "matches": [], "num_matches": 0,
                    "error": entry["error"],
                }

            hybrid_results = entry["hybrid"]
            try:
                if use_llm_reranking and hybrid_results:
                    final_results = self.llm_reranker.rerank(
                        query, hybrid_results, top_k=top_n,
                        use_case=self.use_case,
                        matching_guidance=matching_guidance,
                    )
                else:
                    final_results = hybrid_results[:top_n]

                matches = self._format_matches(final_results)
                return idx, {
                    "query_id": query_item["query_id"],
                    "query": query,
                    "row_number": query_item["row_number"],
                    "matches": matches,
                    "num_matches": len(matches),
                }
            except Exception as e:
                print(f"Error reranking query '{query}': {e}")
                return idx, {
                    "query_id": query_item["query_id"],
                    "query": query,
                    "row_number": query_item["row_number"],
                    "matches": [], "num_matches": 0,
                    "error": str(e),
                }

        results_by_idx: Dict[int, Dict] = {}
        done_count = 0

        with ThreadPoolExecutor(max_workers=MAX_RERANK_WORKERS) as pool:
            futures = {pool.submit(_rerank_one, i): i for i in range(len(queries))}
            for future in as_completed(futures):
                idx, result = future.result()
                results_by_idx[idx] = result
                done_count += 1
                if done_count % 10 == 0:
                    print(f"  Reranked {done_count}/{len(queries)} queries…")

        results = [results_by_idx[i] for i in range(len(queries))]
        print("Query processing complete!")
        return results
    
    def _expand_queries_batch(self, queries: List[str], batch_size: int = 25) -> Dict[str, List[str]]:
        """
        Use the LLM to generate 2-3 reformulations per query for broader
        keyword search coverage.  Results are cached so repeated calls
        for the same query text are free.

        Returns a dict mapping original query text -> list of expanded variants
        (always includes the original as the first element).
        """
        uncached = [q for q in queries if q not in self._expanded_queries_cache]
        if not uncached:
            return self._expanded_queries_cache

        for start in range(0, len(uncached), batch_size):
            batch = uncached[start : start + batch_size]
            numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(batch))

            prompt = (
                "You are a search query expansion assistant. For each numbered query below, "
                "generate 2-3 alternative phrasings that use synonyms, expanded abbreviations, "
                "and more descriptive wording. Keep each variant concise (under 15 words).\n\n"
                f"Queries:\n{numbered}\n\n"
                "Return a JSON object where keys are the query numbers (as strings) and values "
                "are arrays of alternative phrasings. Do NOT include the original query in the alternatives.\n"
                'Example: {"1": ["alt phrasing A", "alt phrasing B"], "2": ["alt C", "alt D", "alt E"]}'
            )

            try:
                response = self.llm_client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": "You expand search queries to improve recall. Return valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                expansions = json.loads(response.choices[0].message.content)

                for i, original in enumerate(batch):
                    variants = expansions.get(str(i + 1), [])
                    if isinstance(variants, list):
                        self._expanded_queries_cache[original] = [original] + [
                            v for v in variants if isinstance(v, str) and v.strip()
                        ]
                    else:
                        self._expanded_queries_cache[original] = [original]

            except Exception as e:
                print(f"Query expansion batch failed ({e}); using original queries.")
                for original in batch:
                    self._expanded_queries_cache[original] = [original]

        return self._expanded_queries_cache

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
