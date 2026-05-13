"""
Approximate USD pricing per 1M tokens for cost estimates.
Update from provider pricing pages — indicative only.
"""
from typing import Dict, List, Tuple

CHAT_MODEL_PRICING_USD_PER_1M: Dict[str, Tuple[float, float]] = {
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5.2": (1.75, 14.0),
    "claude-3-5-haiku-20241022": (0.80, 4.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-7-sonnet-20250219": (3.0, 15.0),
    "gemini-3-flash-preview": (0.10, 0.40),
}

EMBEDDING_PRICE_USD_PER_1M = 0.13

QUERY_LLM_MODELS: List[str] = [
    "gemini-3-flash-preview",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-7-sonnet-20250219",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.2",
]


def chat_price_per_million(model_id: str) -> Tuple[float, float]:
    return CHAT_MODEL_PRICING_USD_PER_1M.get(model_id, (1.0, 4.0))
