# Left Off
Date: 2026-06-04
Last worked on: Phase A1 — test_e2e fix, Ollama/qwen3 JSON debugging, replay analysis

## What Got Done

**test_e2e.py fixed:**
- Updated mock_llm to handle two-pass system: pass 1 returns `thinking` JSON, pass 2 returns `throw` with `"option"` key
- Detects pass 2 by checking for "CATCHABLE"/"MISS by" in user prompt
- Test passes cleanly: CATCH outcome, 0 parse errors, 23 QB calls

**runner.py Unicode fix:**
- Print statements now sanitize non-ASCII chars to `?` before printing
- Was crashing on Windows cp1252 when model used special chars (≈, →, etc.)

**Ollama/qwen3:8b debugging:**
- Root cause: `response_format={"type": "json_object"}` causes qwen3 to return empty `content` (answer goes to `model_extra["reasoning"]` instead)
- Fix 1: removed `response_format` for Ollama provider in llm_client.py
- Fix 2: added fallback — if `content` is empty and provider=ollama, read from `model_extra["reasoning"]`
- Also removed `extra_body={"think": False}` (caused completely empty responses)
- Local model still slow (~10-30s/call), left background run running — user killed it

**GPT run confirmed working (seed 42, slant):**
- QB held until t=1.6s (close but slightly before the t=2.0s cut — still an issue)
- Outcome: DROP (probabilistic — WR was within CATCH_RADIUS, random roll failed, not a bug)
- 0 parse errors, 0 sacks

**tests/test_ollama.py created** — scratch file for Ollama debugging (can be deleted)

## What's Broken / Open
- QB throws slightly too early (t=1.6s on slant when cut is t=2.0s) — model isn't waiting long enough for the route to develop. User noted this explicitly.
- WR projection in pass 2 uses current heading/speed only — pre-cut throws all show as misses, which is correct, but model still sometimes commits early
- Ollama local runs are very slow; background run was killed. Functional but impractical for iteration.
- test_ollama.py scratch file left in tests/ — not a real test

## NEXT STEP
Make the QB wait longer before throwing on developing routes. The likely fix is adding explicit route-awareness to pass 2: when a cut is pending within 0.5s, show a note like "WR cut in Xs — projected positions above assume current heading and will be wrong" to discourage early commitment. Check agents/prompts/qb_pass2.txt and qb_agent.py _build_options().
