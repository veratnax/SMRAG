"""
Main Matching Pipeline
Orchestrates the entire matching workflow
"""
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from processors import PDFProcessor, ExcelProcessor, Embedder, IntelligentChunker
from matching import KeywordSearcher, HybridMatcher, LLMReranker
from utils.vector_store import VectorStore
from qa.qa_learner import QALearner
from config import (DEFAULT_TOP_N, GUIDANCE_EMBEDDING_WEIGHT, RETRIEVAL_POOL_SIZE,
                     LLM_MODEL)
from utils.llm_router import chat_completion, supports_openai_json_mode
import json


class MatchingPipeline:
    """Complete matching pipeline for both use cases"""
    
    def __init__(
        self,
        api_key: str,
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
    ):
        """
        Initialize pipeline with API keys (OpenAI required for embeddings).

        Args:
            api_key: OpenAI API key
            anthropic_api_key: Optional, for Claude chat models
            google_api_key: Optional, for Gemini chat models
        """
        self.api_key = api_key
        self._anthropic_key = anthropic_api_key or ""
        self._google_key = google_api_key or ""
        self.embedder = Embedder(api_key)
        self.vector_store = VectorStore()
        self.keyword_searcher = KeywordSearcher()
        self.hybrid_matcher = HybridMatcher()
        self.llm_reranker = LLMReranker(api_key, anthropic_api_key, google_api_key)
        self.qa_learner = QALearner()
        self.intelligent_chunker = IntelligentChunker(api_key)

        self.query_llm_model = LLM_MODEL
        self.knowledge_base = []
        self.use_case = None
        self.chunking_strategy = None
        self._expanded_queries_cache: Dict[str, List[str]] = {}

    def set_query_llm_model(self, model_id: Optional[str]) -> None:
        resolved = (model_id or "").strip() or LLM_MODEL
        if resolved != self.query_llm_model:
            self._expanded_queries_cache.clear()
        self.query_llm_model = resolved
        self.llm_reranker.set_model(self.query_llm_model)
    
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
                       use_query_expansion: bool = True,
                       query_offset: int = 0,
                       query_limit: Optional[int] = None,
                       matching_guidance: Optional[str] = None,
                       primary_key_column: Optional[str] = None,
                       progress_callback: Optional[Callable[[str, int, int], None]] = None,
                       llm_model: Optional[str] = None,
                       match_count_mode: str = "fixed",
                       min_llm_score: float = 0.70,
                       min_combined_score: float = 0.0,
                       relative_ratio: float = 0.75,
                       gap_stop_delta: float = 0.12,
                       tag_column: Optional[str] = None,
                       tag_separator: Optional[str] = None,
                       ) -> List[Dict]:
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
            primary_key_column: Optional sheet column to carry as stable row ID in results/exports
            progress_callback: Optional ``(stage, done, total)`` — stage is ``"retrieval"`` or ``"rerank"``
            llm_model: Optional model id for expansion + reranking (defaults to session model)
            match_count_mode: ``"fixed"`` for exact top_n, ``"auto"`` for variable 0..top_n
            min_llm_score: Auto-mode minimum LLM relevance score (0..1)
            min_combined_score: Auto-mode minimum combined score when LLM score is unavailable
            relative_ratio: Auto-mode cutoff relative to the best score (0..1)
            gap_stop_delta: Auto-mode stop when score drop from previous rank exceeds this value
            tag_column: Tag column name used only in ``tag_driven`` mode
            tag_separator: Separator used to split tags in ``tag_driven`` mode

        Returns:
            List of results for each query
        """
        if not self.knowledge_base:
            raise Exception("Knowledge base not set up. Call setup_pdf_knowledge_base or setup_excel_knowledge_base first.")

        if llm_model:
            self.set_query_llm_model(llm_model)

        mode = (match_count_mode or "fixed").strip().lower()
        if mode not in {"fixed", "auto", "tag_driven"}:
            mode = "fixed"
        if mode == "tag_driven":
            if not (tag_column or "").strip():
                raise Exception("Tag column is required in tag-driven mode.")
            if not (tag_separator or ""):
                raise Exception("Tag separator is required in tag-driven mode.")
        min_llm_score = max(0.0, min(1.0, float(min_llm_score)))
        relative_ratio = max(0.0, min(1.0, float(relative_ratio)))
        min_combined_score = float(min_combined_score)
        gap_stop_delta = max(0.0, float(gap_stop_delta))

        def _report(stage: str, done: int, total: int) -> None:
            if progress_callback and total > 0:
                progress_callback(stage, done, total)

        # Load queries
        print("Loading queries...")
        excel_processor = ExcelProcessor()
        excel_processor.load_excel(query_excel_path)
        queries = excel_processor.process_queries(
            query_column,
            primary_key_column=primary_key_column,
            tag_column=tag_column if mode == "tag_driven" else None,
            tag_separator=tag_separator if mode == "tag_driven" else None,
        )
        
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

        if mode == "tag_driven":
            return self._process_tag_driven_queries(
                queries=queries,
                top_n=top_n,
                use_llm_reranking=use_llm_reranking,
                use_query_expansion=use_query_expansion,
                matching_guidance=matching_guidance,
                progress_callback=progress_callback,
            )

        nq = len(queries)
        _report("retrieval", 0, nq)
        print(f"Processing {nq} queries...")
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
                retrieval_warning = None
                raw_embedding = all_query_embeddings[i] if i < len(all_query_embeddings) else None
                if raw_embedding is None:
                    semantic_results = []
                    retrieval_warning = (
                        "Query embedding failed; used keyword-only retrieval fallback."
                    )
                else:
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
                hybrid_per_query.append({
                    "ok": True,
                    "hybrid": hybrid_results,
                    "warning": retrieval_warning,
                })
            except Exception as e:
                hybrid_per_query.append({"ok": False, "error": str(e)})
            _report("retrieval", i + 1, nq)

        print(f"  Retrieval done for {len(queries)} queries. Starting reranking…")
        _report("rerank", 0, nq)

        # --- Phase 2: LLM reranking (I/O-bound) — parallelized ------------
        MAX_RERANK_WORKERS = 10

        def _row_meta(query_item: Dict) -> Dict:
            meta = {
                "query_id": query_item["query_id"],
                "query": query_item["query"],
                "row_number": query_item["row_number"],
            }
            if "primary_key" in query_item:
                meta["primary_key"] = query_item["primary_key"]
            return meta

        def _rerank_one(idx: int):
            """Rerank a single query's hybrid results (runs in thread)."""
            query_item = queries[idx]
            query = query_item["query"]
            entry = hybrid_per_query[idx]

            if not entry["ok"]:
                return idx, {
                    **_row_meta(query_item),
                    "matches": [], "num_matches": 0,
                    "error": entry["error"],
                }

            hybrid_results = entry["hybrid"]
            retrieval_warning = entry.get("warning")
            try:
                if use_llm_reranking and hybrid_results:
                    rerank_top_k = len(hybrid_results) if mode == "auto" else top_n
                    final_results = self.llm_reranker.rerank(
                        query, hybrid_results, top_k=rerank_top_k,
                        use_case=self.use_case,
                        matching_guidance=matching_guidance,
                    )
                else:
                    final_results = hybrid_results if mode == "auto" else hybrid_results[:top_n]

                final_results = self._select_match_count(
                    final_results,
                    top_n=top_n,
                    mode=mode,
                    min_llm_score=min_llm_score,
                    min_combined_score=min_combined_score,
                    relative_ratio=relative_ratio,
                    gap_stop_delta=gap_stop_delta,
                )
                matches = self._format_matches(final_results)
                return idx, {
                    **_row_meta(query_item),
                    "matches": matches,
                    "num_matches": len(matches),
                    "warning": retrieval_warning,
                }
            except Exception as e:
                print(f"Error reranking query '{query}': {e}")
                return idx, {
                    **_row_meta(query_item),
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
                _report("rerank", done_count, nq)
                if done_count % 10 == 0:
                    print(f"  Reranked {done_count}/{len(queries)} queries…")

        results = [results_by_idx[i] for i in range(len(queries))]
        print("Query processing complete!")
        return results

    def _process_tag_driven_queries(
        self,
        *,
        queries: List[Dict],
        top_n: int,
        use_llm_reranking: bool,
        use_query_expansion: bool,
        matching_guidance: Optional[str],
        progress_callback: Optional[Callable[[str, int, int], None]],
    ) -> List[Dict]:
        """Tag-driven mode: one best match per tag, in original tag order."""
        def _report(stage: str, done: int, total: int) -> None:
            if progress_callback and total > 0:
                progress_callback(stage, done, total)

        def _row_meta(query_item: Dict) -> Dict:
            meta = {
                "query_id": query_item["query_id"],
                "query": query_item["query"],
                "row_number": query_item["row_number"],
            }
            if "primary_key" in query_item:
                meta["primary_key"] = query_item["primary_key"]
            return meta

        nq = len(queries)
        _report("retrieval", 0, nq)
        print(f"Processing {nq} queries in tag-driven mode...")

        guidance_embedding = None
        if matching_guidance and matching_guidance.strip():
            try:
                guidance_embedding = self.embedder.embed_text(
                    "Matching guidance: " + matching_guidance.strip()
                )
            except Exception as e:
                print(f"Warning: could not embed guidance ({e}); continuing with query-only embeddings.")

        retrieval_k = max(RETRIEVAL_POOL_SIZE, top_n * 2)
        per_query_payload: List[Dict] = []
        all_combined_queries: List[str] = []

        for q in queries:
            tags = q.get("query_tags", []) or []
            if tags:
                for tag in tags:
                    all_combined_queries.append(f"{q['query']} {tag}".strip())

        if use_query_expansion and all_combined_queries:
            self._expand_queries_batch(all_combined_queries)

        for i, query_item in enumerate(queries):
            tags = query_item.get("query_tags", []) or []
            tag_entries: List[Dict] = []
            warnings: List[str] = []

            for tag_idx, tag_value in enumerate(tags, start=1):
                combined_query = f"{query_item['query']} {tag_value}".strip()
                retrieval_warning = None
                raw_embedding = None
                try:
                    raw_embedding = self.embedder.embed_text(combined_query)
                except Exception:
                    raw_embedding = None

                if raw_embedding is None:
                    semantic_results = []
                    retrieval_warning = (
                        f"Embedding failed for tag '{tag_value}'; used keyword-only retrieval fallback."
                    )
                else:
                    if guidance_embedding is not None:
                        query_embedding = self.embedder.combine_and_normalize(
                            guidance_embedding, raw_embedding, GUIDANCE_EMBEDDING_WEIGHT
                        )
                    else:
                        query_embedding = raw_embedding
                    semantic_results = self.vector_store.search(query_embedding, top_k=retrieval_k)

                expanded_variants = self._expanded_queries_cache.get(combined_query, [combined_query])
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
                tag_entries.append({
                    "tag_index": tag_idx,
                    "tag_value": tag_value,
                    "combined_query": combined_query,
                    "hybrid": hybrid_results,
                })
                if retrieval_warning:
                    warnings.append(retrieval_warning)

            per_query_payload.append({
                "query_item": query_item,
                "tag_entries": tag_entries,
                "warning": " | ".join(warnings) if warnings else None,
            })
            _report("retrieval", i + 1, nq)

        _report("rerank", 0, nq)
        results: List[Dict] = []
        for i, payload in enumerate(per_query_payload):
            query_item = payload["query_item"]
            tag_entries = payload["tag_entries"]

            if not tag_entries:
                results.append({
                    **_row_meta(query_item),
                    "matches": [],
                    "num_matches": 0,
                    "warning": "No valid tags found for this row; returned 0 matches.",
                })
                _report("rerank", i + 1, nq)
                continue

            collected: List[Dict] = []
            for entry in tag_entries:
                try:
                    if use_llm_reranking and entry["hybrid"]:
                        chosen = self.llm_reranker.rerank(
                            entry["combined_query"],
                            entry["hybrid"],
                            top_k=1,
                            use_case=self.use_case,
                            matching_guidance=matching_guidance,
                        )
                    else:
                        chosen = entry["hybrid"][:1]
                    formatted = self._format_matches(chosen)
                    if formatted:
                        match = formatted[0]
                        match["rank"] = len(collected) + 1
                        match["tag_index"] = entry["tag_index"]
                        match["tag_value"] = entry["tag_value"]
                        collected.append(match)
                except Exception as e:
                    print(f"Tag-driven rerank error for query '{query_item['query']}': {e}")

            results.append({
                **_row_meta(query_item),
                "matches": collected,
                "num_matches": len(collected),
                "warning": payload.get("warning"),
            })
            _report("rerank", i + 1, nq)

        print("Tag-driven query processing complete!")
        return results

    def _select_match_count(
        self,
        ranked_results: List[Dict],
        *,
        top_n: int,
        mode: str,
        min_llm_score: float,
        min_combined_score: float,
        relative_ratio: float,
        gap_stop_delta: float,
    ) -> List[Dict]:
        """Pick final results using fixed-count or auto-count mode."""
        if top_n <= 0:
            return []
        if mode != "auto":
            return ranked_results[:top_n]
        if not ranked_results:
            return []
        pool = ranked_results

        def _score_for_auto(item: Dict) -> float:
            llm_score = item.get("llm_relevance_score")
            if llm_score is not None:
                return float(llm_score)
            return float(item.get("combined_score", 0.0))

        best_score = _score_for_auto(pool[0])
        dynamic: List[Dict] = []
        prev_score: Optional[float] = None
        for item in pool:
            score = _score_for_auto(item)
            if prev_score is not None and (prev_score - score) > gap_stop_delta:
                break
            prev_score = score
            has_llm_score = item.get("llm_relevance_score") is not None
            floor = min_llm_score if has_llm_score else min_combined_score
            if score < floor:
                continue
            if best_score > 0 and score < best_score * relative_ratio:
                continue
            dynamic.append(item)
        return dynamic
    
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
                fmt = {"type": "json_object"} if supports_openai_json_mode(self.query_llm_model) else None
                content = chat_completion(
                    self.query_llm_model,
                    messages=[
                        {"role": "system", "content": "You expand search queries to improve recall. Return valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    openai_key=self.api_key,
                    anthropic_key=self._anthropic_key,
                    google_key=self._google_key,
                    temperature=0.3,
                    response_format=fmt,
                )
                text = (content or "").strip()
                if text.startswith("```"):
                    text = text.split("```", 2)[-1].strip()
                    if text.lower().startswith("json"):
                        text = text[4:].lstrip()
                expansions = json.loads(text)

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
