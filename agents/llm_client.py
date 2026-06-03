import os
from openai import OpenAI

_openai_client: OpenAI | None = None
_ollama_client: OpenAI | None = None

OLLAMA_BASE_URL = "http://localhost:11434/v1"


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise EnvironmentError("OPENAI_API_KEY is not set.")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def _get_ollama_client() -> OpenAI:
    global _ollama_client
    if _ollama_client is None:
        url = os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
        _ollama_client = OpenAI(base_url=url, api_key="ollama")
    return _ollama_client


def call_llm(
    system_prompt: str,
    user_message: str,
    model: str = "gpt-4o-mini",
    reasoning_effort: str | None = "low",
    provider: str = "openai",  # "openai" | "ollama"
) -> str:
    client = _get_ollama_client() if provider == "ollama" else _get_openai_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict = {"model": model, "messages": messages}

    # reasoning_effort only applies to OpenAI o-series / gpt-5-nano; skip for Ollama
    if reasoning_effort is not None and provider != "ollama":
        kwargs["reasoning_effort"] = reasoning_effort

    # Local models benefit from low temperature for reliable JSON output
    if provider == "ollama":
        kwargs["temperature"] = 0.3

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
