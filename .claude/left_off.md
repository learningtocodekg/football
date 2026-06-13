# Left Off
Date: 2026-06-13 (session 2)

This session: user reviewed the 6C/3PBU/1DROP suite and named specific route faults. Fixed the two real
ones — **go** (QB fundamental misunderstanding) and **comeback** (settle route) — and re-ran the full
suite: **9C/1PBU**, every flagged route now a CATCH, no regressions. All fixes are prompt-understanding
+ one mechanical solver change (no WR call-timing code gates — see memory no-phase-gate).

## What got done
- **Go — FIXED (the priority).** The QB was bulleting into the CB's cushion at t=0.9: it read sep=3.96
  as "open" when the CB was still 3.8yd DOWNFIELD (in front, off-coverage cushion). Taught the QB that
  separation with the CB in front is a CUSHION, not a beaten man — a deep ball is only "over the top"
  once the WR is EVEN WITH/PAST the CB, and a SHRINKING sep with the CB in front is the cushion closing,
  not a window. Edits: `qb_system.txt` ("WHO IS CLOSER TO THE CATCH POINT" block) + `qb_pass1.txt`
  (direction-of-separation note + a cushion-hold example + a corrected even/past throw example; deleted
  the old incoherent "CB a step behind on a go" example that taught the wrong lesson). Validated:
  **5/5 hold** on the exact failing geometry (deterministic harness), live **CATCH** (QB held the bullet,
  waited for WR to pass CB, threw a touch over the top). In the suite, go sep GROWS in flight 2.14->3.52.
- **Comeback — FIXED.** It's a STOP route but the WR sprinted 24yd through the 225° break and the QB
  lofted a rainbow to chase. Root cause: the meeting-point solver projects the WR IN-STRIDE, so it
  placed the ball where he'd be if he kept running, and the air-phase logic then dragged him there.
  Made the solver **settle-aware**: `SETTLE_ROUTES={"comeback"}` + `SETTLE_DISTANCE=1.5` in `qb_agent.py`
  — for a settle route every arc meets the WR at the FIXED settle spot (break point + 1.5yd), only the
  arrival time changes. Threaded `route` through `QBAgent.decide()` and the runner. Also rewrote the
  comeback route description (`scripted.py`) so the WR brakes/settles, and the QB geometry hint
  (`observation.py`) so it bullets the settle spot. Live: a TRUE comeback — WR settles ~1.5yd back at
  (14.7,60.9) and sits (speed 0), QB bullets right there.
- **Regression caught + fixed mid-session:** the go cushion-caution bled into the comeback (QB held 1.3s
  waiting for the WR to "pass the CB" on a route where he never does). Fixed by scoping the caution to
  "a ball thrown BEYOND the CB" vs "underneath/settle routes (comeback/curl)" in both qb_system + pass1.
  Re-confirmed go still 5/5 hold after the qualifier.

## Suite result (gpt-5-nano, seed 42): 9C / 1PBU  (was 6C/3PBU/1DROP)
slant C, comeback C, go C, double_move C, curl C(7.47), zig C, drag C, post_corner C(1.61->1.9), in C.
Only loss: **corner PBU** (sep 2.03->0.85) — a genuine deep-coverage contest, NOT flagged by the user.

## Broken / Open
- **corner PBU** — deep break to 315°; CB recovers and contests (sep@catch 0.85). Coverage contest,
  governed by QB/CB decisioning, not a mechanical bug. The remaining single loss.
- **post_corner / zig** — CATCH this run but user says they're not "real" routes and low-worry; the post
  part of post_corner and the in-then-out of zig may not fully execute. Parked per user.
- **curl** still runs back ~6yd (180°) rather than truly settling 2yd — it's a settle route too but was
  NOT added to SETTLE_ROUTES (user said curl is "much better," avoid regressing a working route).
  Easy extension if desired: add "curl" to SETTLE_ROUTES.
- LLM nondeterminism persists — go/comeback were validated DETERMINISTICALLY (exact failing geometry)
  to avoid chasing model noise; the suite is a single noisy sample on top.

## NEXT STEP
**Address the corner PBU** — the lone remaining loss. It's the same deep-ball family as go but with a
315° break: check whether the QB throws over the top late enough (WR past the CB) or forces it into the
recovering CB. Likely a pass1 timing read on the deep corner, not a placement bug.

## Housekeeping
- Scratch files still in repo root: `kg_qb_prompt.txt`, `*_step_example.txt`, `curl_check.py`,
  `show_wr_obs.py`, `wr_obs.txt`, `run_log_42.txt`. Delete when convenient.
- New replays this session: `replays/{go,comeback}_42_fix*.json` (verification runs).
