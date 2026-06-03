import os
from openai import OpenAI

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise EnvironmentError("OPENAI_API_KEY is not set.")
        _client = OpenAI(api_key=key)
    return _client


def call_llm(
    system_prompt: str,
    user_message: str,
    model: str = "gpt-4o-mini",
    reasoning_effort: str | None = "low",
) -> str:
    client = _get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs: dict = {"model": model, "messages": messages}

    # reasoning_effort is supported on o-series and gpt-5-nano reasoning models.
    # Pass it and let the API error loudly if the model doesn't support it.
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
