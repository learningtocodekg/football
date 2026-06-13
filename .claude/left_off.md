# Left Off
Date: 2026-06-12

Two parallel threads ran this session: a **WR thread** (stem-discipline fix, committed `20eb439`)
and a **QB thread** (this chat: prompt redo + realistic routes + deep-ball meeting-point solver).

## QB THREAD (this chat) — what got done
Executed the planned QB-prompting redo end-to-end, made the routes physics-realistic, then solved
the deep-ball catch-22 with a meeting-point solver.
- **Routes retuned to real NFL depths, physics-derived cut times** [in 20eb439]: slant 5yd/1.0s,
  post 10yd/1.8s, curl 10yd/1.8s/180, comeback 12yd/1.9s/225, out 1.6s/270, corner 1.8s/315,
  in 1.6s/90, drag 4yd/0.9s, zig/double_move/post_corner retimed; out/corner headings fixed (were
  swapped). `_est_yards` rewritten to the real exponential burst-accel model (was +25% on depth).
- **QB system prompt** cut from ~180 sprawling lines to timeless context only. **LEAD HINT + editorial
  DIRECTION CHECK deleted.** Lean factual observation; separation framed center-to-center w/ real
  1.8 / 1.0 thresholds. **QB gated on the WR call** (runner; ScriptedQB unaffected). [20eb439]
- **Two-step flow + meeting-point solver** [THIS commit]:
  - **Pass 1 = the QB's own read.** Raw facts only (no projected sep). Outputs `open_window`
    `[t_from,t_to]` in SECONDS FROM NOW, or hold. Judging the window is the QB's job.
  - **Pass 2 = landing physics only.** `_meeting_options` (qb_agent.py) solves per arc for the
    self-consistent point where a ball released NOW meets the WR's locked line — bisection on arrival
    time `tau` s.t. `flight_time(dist to W(tau)) == tau`. Shows meeting coord + arrival(+s) + range,
    **no CB/sep** (that would re-answer the openness call the QB owns). QB picks arc + target_coord.
  - schema: `parse_qb_pass1` requires `open_window` (target_area dropped); `parse_qb_pass2` =
    arc + target_coord.

## WR THREAD (separate chat, committed 20eb439) — what got done
WR broke routes absurdly early (slant cut at t=0.2/~0.6yd vs a 5yd/1.0s stem). Config + observation
were already correct; the WR LLM ignored them. Root cause: the LIVE-free phase batches ONE plan of
up to 4 steps served queue-less, and the model baked the break+call into step 3/4 of its FIRST plan
at t=0.0 (cut sight-unseen); cloned plan-level reasoning masked it in the log. **Fix: timestamped
plan steps via Pydantic structured outputs** (`call_llm_structured` / `chat.completions.parse`) —
each step must emit its absolute `t`, so the model can't pretend a 4-step (0.4s) plan reaches the
1.0s break. Slant: CATCH sep 4.35, WR held stem to t=0.9. Freedom intact (it re-plans and *chooses*
to hold). Failed detours: REQUIRE/MUST language (reverted), consequence reframe alone, tick-math
fact alone (model rationalized a short stem) — only the forced timestamp stuck.

## Live results (gpt-5-nano, seed 42)
- **Slant: CATCH sep 2.27** — gated QB waited for call, anticipated its own window, threw a leading
  bullet away from CB. 0 QB parse errors.
- **Go: the early-deep-throw bug is GONE and the meeting-point fix WORKS.** WR held the 0deg stem,
  called t=1.6; QB pass1 computed its own window (0.18-2.4s), pass2 threw **29.6yd DEEP to (16,75.6)**
  vs the old 17.6yd-short loft to (16,62). Outcome = **PBU sep 0.41**, downstream not the QB.

## Broken / Open (the go-completion blocker first)
- **WR air-phase brakes off the go.** Ball-in-air controller does `required_speed = dist/ETA` and
  throttles DOWN to not overshoot the landing spot — right on a curl, suicidal on a go (kills the
  speed advantage, CB stays glued). This is why the deep ball PBU'd. **Top blocker for go catches.**
- **Meeting-point solver assumes constant WR speed** — exact for verticals, WRONG for routes where
  the WR decelerates/settles (curl, comeback). Needs a settle model before those place correctly.
- Full 10-route A4 suite NOT yet run with all this. Verified on slant (CATCH) + go (deep throw).
- 1 empty-response QB pass1 parse error seen (known LLM hiccup; holds that step).

## NEXT STEP
**Fix the WR air-phase so it runs THROUGH a deep ball at speed instead of decelerating to a fixed
spot, then re-run the go to confirm CATCH.** After that: run the full 10-route A4 suite
(`python run_all_routes.py`, seed 42) to check both threads for regressions, and add a settle/decel
model to `_meeting_options` for curl/comeback.

## Housekeeping
- `kg_qb_prompt.txt` / `*_step_example.txt` scratch files — verify gone / delete if still around.
- Ollama path still uses the lenient text parsers (no structured outputs); only hit with `--local`.
- LLM nondeterminism: single runs aren't proof; the suite run will be more telling.
