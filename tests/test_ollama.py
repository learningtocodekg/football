"""Test: check model_extra reasoning field."""
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

resp = client.chat.completions.create(
    model="qwen3:8b",
    messages=[{"role": "user", "content": "What is 2+2? Reply with just the number."}],
    max_tokens=200,
)
msg = resp.choices[0].message
print("content:", repr(msg.content))
print("model_extra:", msg.model_extra)
