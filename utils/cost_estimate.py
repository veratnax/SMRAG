"""
Heuristic cost estimates for query processing (OpenAI embeddings + selected LLM).
"""
from typing import List, Optional, Dict, Any, Tuple

from processors import ExcelProcessor
from config import EMBEDDING_MODEL
from utils.llm_pricing import EMBEDDING_PRICE_USD_PER_1M, chat_price_per_million

EXPANSION_BATCH = 25
RERANK_CANDIDATES = 10
PDF_SNIPPET_CHARS = 500
EXCEL_SNIPPET_CHARS = 300


def _chars_to_tokens(chars: int) -> int:
    return max(1, int(chars / 4))


def count_queries_slice(
    file_path: str,
    query_column: str,
    primary_key_column: Optional[str],
    query_offset: int,
    query_limit: Optional[int],
) -> Tuple[int, List[str]]:
    proc = ExcelProcessor()
    proc.load_excel(file_path)
    queries = proc.process_queries(query_column, primary_key_column=primary_key_column)
    if query_offset < 0:
        query_offset = 0
    if query_offset > len(queries):
        return 0, []
    sliced = queries[query_offset:]
    if query_limit is not None:
        if query_limit < 0:
            query_limit = 0
        sliced = sliced[:query_limit]
    texts = [q["query"] for q in sliced]
    return len(sliced), texts


def estimate_rerank_prompt_tokens(
    use_case: str,
    avg_query_chars: float,
    n_candidates: int,
    matching_guidance: str,
    few_shot_extra_chars: int = 0,
) -> int:
    base = 350 + few_shot_extra_chars
    g = len(matching_guidance or "")
    q = int(avg_query_chars)
    cand_chars = n_candidates * (PDF_SNIPPET_CHARS if use_case == "pdf_kb" else EXCEL_SNIPPET_CHARS)
    cand_chars += n_candidates * 80
    return _chars_to_tokens(base + g + q + cand_chars)


def estimate_expansion_batch_tokens(batch_queries: List[str]) -> Tuple[int, int]:
    system = 80
    template = 420
    body = sum(len(q) for q in batch_queries)
    inp = system + template + body
    out = 120 + 40 * len(batch_queries)
    return _chars_to_tokens(inp), _chars_to_tokens(out)


def estimate_embedding_tokens_for_queries(query_texts: List[str], guidance: str) -> int:
    g = len(guidance or "")
    per = _chars_to_tokens(g + 40)
    total = 0
    for q in query_texts:
        total += per + _chars_to_tokens(len(q))
    return total


def build_cost_estimate(
    *,
    num_queries: int,
    query_texts: List[str],
    use_case: str,
    top_n: int,
    use_llm_reranking: bool,
    use_query_expansion: bool,
    matching_guidance: str,
    llm_model: str,
) -> Dict[str, Any]:
    if num_queries <= 0:
        return {
            "num_queries": 0,
            "total_usd": 0.0,
            "avg_usd_per_query": 0.0,
            "breakdown": {},
            "disclaimer": "No queries to process in this batch.",
            "embedding_model": EMBEDDING_MODEL,
            "llm_model": llm_model,
        }

    avg_qc = sum(len(t) for t in query_texts) / max(len(query_texts), 1)
    n_cand = min(RERANK_CANDIDATES, max(top_n * 2, 5))

    in_price, out_price = chat_price_per_million(llm_model)

    emb_tokens = estimate_embedding_tokens_for_queries(query_texts, matching_guidance)
    emb_usd = (emb_tokens / 1_000_000) * EMBEDDING_PRICE_USD_PER_1M

    exp_in, exp_out = 0, 0
    if use_query_expansion:
        for start in range(0, num_queries, EXPANSION_BATCH):
            batch = query_texts[start : start + EXPANSION_BATCH]
            if not batch:
                continue
            bi, bo = estimate_expansion_batch_tokens(batch)
            exp_in += bi
            exp_out += bo

    rr_in, rr_out = 0, 0
    if use_llm_reranking:
        toks_in = estimate_rerank_prompt_tokens(
            use_case, avg_qc, n_cand, matching_guidance,
        )
        toks_out = 280
        rr_in = toks_in * num_queries
        rr_out = toks_out * num_queries

    chat_in = exp_in + rr_in
    chat_out = exp_out + rr_out
    chat_usd = (chat_in / 1_000_000) * in_price + (chat_out / 1_000_000) * out_price

    total = emb_usd + chat_usd
    avg = total / num_queries if num_queries else 0.0

    return {
        "num_queries": num_queries,
        "total_usd": round(total, 4),
        "avg_usd_per_query": round(avg, 6),
        "total_usd_range": [round(total * 0.7, 4), round(total * 1.4, 4)],
        "breakdown": {
            "embeddings_usd": round(emb_usd, 4),
            "embeddings_tokens_est": emb_tokens,
            "chat_input_tokens_est": chat_in,
            "chat_output_tokens_est": chat_out,
            "chat_usd": round(chat_usd, 4),
            "expansion_enabled": use_query_expansion,
            "reranking_enabled": use_llm_reranking,
        },
        "disclaimer": (
            "Approximate only. Actual cost depends on real token usage and provider billing. "
            "Embeddings use OpenAI; the selected model is used for expansion and reranking."
        ),
        "embedding_model": EMBEDDING_MODEL,
        "llm_model": llm_model,
    }
