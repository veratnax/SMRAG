"""
Chat completions for OpenAI, Anthropic, and Google (Gemini) via LiteLLM.
Embeddings stay in Embedder (OpenAI).
"""
from typing import List, Dict, Optional, Any

import litellm

litellm.suppress_debug_info = True


def provider_for_ui_model(model_id: str) -> str:
    if model_id.startswith("gpt-"):
        return "openai"
    if model_id.startswith("claude-"):
        return "anthropic"
    if model_id.startswith("gemini"):
        return "google"
    return "openai"


def to_litellm_model(model_id: str) -> str:
    if model_id.startswith("gemini"):
        return f"gemini/{model_id}"
    return model_id


def supports_openai_json_mode(model_id: str) -> bool:
    return model_id.startswith("gpt-")


def validate_keys_for_model(
    model_id: str,
    openai_key: Optional[str],
    anthropic_key: Optional[str],
    google_key: Optional[str],
) -> None:
    p = provider_for_ui_model(model_id)
    if p == "openai" and not (openai_key or "").strip():
        raise ValueError("OpenAI API key is required (used for embeddings and GPT models).")
    if p == "anthropic" and not (anthropic_key or "").strip():
        raise ValueError("Anthropic API key is required for Claude models. Add it on the login screen.")
    if p == "google" and not (google_key or "").strip():
        raise ValueError("Google AI API key is required for Gemini models. Add it on the login screen.")


def chat_completion(
    model_id: str,
    messages: List[Dict[str, str]],
    *,
    openai_key: str,
    anthropic_key: str = "",
    google_key: str = "",
    temperature: float = 0.2,
    response_format: Optional[Dict[str, Any]] = None,
) -> str:
    validate_keys_for_model(model_id, openai_key, anthropic_key, google_key)
    provider = provider_for_ui_model(model_id)
    if provider == "openai":
        api_key = openai_key.strip()
    elif provider == "anthropic":
        api_key = anthropic_key.strip()
    else:
        api_key = google_key.strip()

    kwargs: Dict[str, Any] = {
        "model": to_litellm_model(model_id),
        "messages": messages,
        "temperature": temperature,
        "api_key": api_key,
    }
    if response_format and supports_openai_json_mode(model_id):
        kwargs["response_format"] = response_format

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content or ""
