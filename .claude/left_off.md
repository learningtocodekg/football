# Left Off
Date: 2026-06-12

## What We Worked On
WR thread (QB was being redone in a separate chat). Chased down WHY the WR breaks its route
absurdly early — on the slant it cut at t=0.2 / ~0.6yd when the route is a 5yd / ~1.0s stem —
and fixed it **without** breaking the high-freedom principle (guide via information, never
enforce a decision in code). The fix that finally worked: **timestamped plan steps + Pydantic
structured outputs.**

## Root Cause (confirmed by reading config → observation → behavior)
- Config is correct: `ROUTES["slant"] = [(1.0, 0.0), (999, 45.0)]` → cut_time 1.0s, ~5yd depth.
- The observation correctly told the WR `CUT TARGET: break to 45° at t≈1.0s, ~5yd`. So timing/
  yardage were NOT missing.
- The WR LLM ignored it. Two compounding mechanisms:
  1. **Blind batched plan.** The LIVE-free phase makes ONE plan call (`wr_agent.decide`) that
     returns up to 4 steps served from a queue with no fresh CB look. The model baked the
     break+call into step 3/4 of its very first plan at t=0.0 — committing the cut sight-unseen.
  2. **Cloned reasoning** (`parse_wr_plan`) stamped one plan-level string onto every step, so the
     replay showed "maintain stem" on the very step that broke — masking what happened.

## What Got Done — the fix (in the tree)
- **`agents/schema.py`** — `WRStep` / `WRPlan` Pydantic models + `wr_plan_steps()` converter.
  Each step: `t, heading, throttle(Literal), facing, call_for_ball, reasoning`. `parse_wr_plan`
  (Ollama text fallback) now tags each step with its own `t` and per-step reasoning.
- **`agents/llm_client.py`** — `call_llm_structured()` using `chat.completions.parse` with the
  Pydantic schema as `response_format` (OpenAI structured outputs, guaranteed shape — no regex).
- **`agents/wr_agent.py`** — `decide()` free phase: OpenAI → structured path (`WRPlan`); Ollama →
  keeps lenient `call_llm` + `parse_wr_plan`.
- **`agents/prompts/wr_live_free.txt`** — plan output is now a list of TIMESTAMPED steps. Window
  is `[T+0.1, T+0.4]` (1–4 steps), each step tagged with absolute `t` and its own one-line
  reasoning; JSON example includes `t`.
- **`agents/observation.py`** — concrete `PLAN WINDOW: you are at t=…, plan may cover t+0.1…t+0.4;
  your break at t≈X is INSIDE/BEYOND this window` line. Also REVERTED an earlier REQUIRE/MUST
  detour back to factual/consequence framing (see below).

## Result — IT WORKED (slant)
slant seed 42, gpt-5-nano: **CATCH, sep 4.35, 0 parse errors.** WR held the 0° stem to **t=0.9**,
broke to 45° and called at the cut window (was t=0.2). `detected_cut_t=0.9`, throw_t=1.0,
throw_distance 12.2yd (a real slant from depth). Per-step reasoning now reads against the clock
(`t=0.7 eyes still on break point ~1.0s`). Freedom intact — it re-plans each tick and *chooses*
to hold the stem; we made the clock legible, didn't force it.

## Go route — early-throw bug FIXED, but play INCOMPLETE for a SEPARATE reason
go seed 42: WR held stem, called at t=0.9, QB threw at **t=1.5 (not the old t=0.2 bomb)** —
the original go-route early-deep-throw is gone. BUT outcome = **INCOMPLETE, sep 2.34**, due to a
downstream QB/air issue, NOT the stem: QB threw a **17.6yd loft** that hangs ~1.9s; the WR reaches
the fixed landing spot way too early (~t=2.0, ball ETA still ~1.4s), then thrashes
brake→accelerate and **overshoots**. Also 1 `[QB pass1 parse error] raw=` (empty response).
→ **User parked the loft/air-timing issue for the QB thread.**

## Detours that FAILED (don't repeat)
- **REQUIRE/MUST language** in prompt+obs (forbid breaking before the window): works against the
  high-freedom principle — reverted.
- **Factual consequence reframe alone**: WR still broke at t=0.3.
- **Tick-math fact alone** ("break is ~7 ticks away, a 4-step plan can't reach it"): BACKFIRED —
  the model *rationalized* a 0.3–0.4s stem, using the new info to justify the early break instead
  of extending. Lesson: information about timing didn't stick until each step was forced to carry
  its absolute `t` (structured output) — then the model couldn't pretend a short plan reached 1.0s.

## NEXT STEP
**Run the full 10-route A4 suite (seed 42, gpt-5-nano) to confirm the timestamped/structured-output
WR holds its stem on every route and check for regressions.** The fix is verified only on slant
(CATCH) and the go stem so far. `python run_all_routes.py`.

## Open / Future
- Loft hang-time vs WR air-arrival overshoot + QB under-leading a deep ball → **QB thread**.
- Save-to-memory pending: "timestamped Pydantic structured-output plan is what finally held the WR
  stem (freedom-preserving)" — durable finding worth recording.
- Ollama path uses the lenient text parser (no structured outputs via openai-compat); only
  exercised if `--local`.
- LLM nondeterminism: single runs aren't proof; suite run will be more telling.
