import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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
    model: str = "gpt-5-nano",
    reasoning_effort: str | None = "low",
    provider: str = "openai",  # "openai" | "ollama"
) -> str:
    client = _get_ollama_client() if provider == "ollama" else _get_openai_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict = {"model": model, "messages": messages}

    if provider == "ollama":
        # qwen3 via Ollama: thinking goes to model_extra["reasoning"], content has the answer.
        # response_format=json_object causes content to be empty — don't use it.
        # Instead rely on prompt instructions + _extract_json parser.
        kwargs["temperature"] = 0.3
    else:
        # gpt-5-nano: reasoning_effort, structured JSON output, tight token budget
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        kwargs["response_format"] = {"type": "json_object"}
        kwargs["max_completion_tokens"] = 4000

    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    content = msg.content or ""

    # Retry once if content is empty
    if not content.strip():
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        content = msg.content or ""

    # qwen3 via Ollama sometimes puts the answer only in model_extra["reasoning"]
    # when thinking mode triggers and content ends up empty
    if not content and provider == "ollama":
        extra = getattr(msg, "model_extra", None) or {}
        content = extra.get("reasoning", "") or ""
    return content


def call_llm_structured(
    system_prompt: str,
    user_message: str,
    response_model,
    model: str = "gpt-5-nano",
    reasoning_effort: str | None = "low",
):
    """OpenAI structured output: returns a validated `response_model` instance (or None).

    Uses chat.completions.parse with a Pydantic schema so the model's output is
    guaranteed to match — no regex JSON extraction. OpenAI only; callers route
    Ollama through call_llm + a lenient text parser.
    """
    client = _get_openai_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "response_format": response_model,
        "max_completion_tokens": 4000,
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort

    resp = client.chat.completions.parse(**kwargs)
    parsed = resp.choices[0].message.parsed
    if parsed is None:  # retry once
        resp = client.chat.completions.parse(**kwargs)
        parsed = resp.choices[0].message.parsed
    return parsed
