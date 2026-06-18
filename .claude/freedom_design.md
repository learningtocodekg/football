# Freedom Branch — Design Contract

Goal: cut the scaffolding, give the LLMs real freedom, keep good gameplay. The LLM becomes a
**Madden-style input controller** on top of the existing physics/ball engine (which we KEEP).

Replaces the soft-rail WR system and the coordinate-placing QB. Replay JSON output is UNCHANGED
(every player's motion is still recorded every 0.1s, even when their agent isn't being queried).

Coordinate frame (unchanged): heading 0°=upfield(+y), 90°=right(+x), 180°=back to QB, 270°=left.
WR1 starts LEFT (x=16) so 90°=inside (toward middle), 270°=his (left) sideline.
QB (26.65,48) power 85 → max ball launch speed ≈ 26.5 yd/s. WR1 max 9.5 yd/s. CB1 starts 5.5yd off.

---

## Control flow (sim/runner.py — OWNED BY FOUNDATION)

Phases: `LIVE` (pre-throw) → `BALL_IN_AIR`.

Each 0.1s step:

1. **WR**
   - `BALL_IN_AIR`: WR is ALIVE → `WRAgent.decide_air(obs)` LLM each step (adjust to the ball).
   - committed (called for ball, ball not yet thrown OR in air-but pre-throw): **NO LLM** — engine
     advances the WR deterministically along its locked `end_route` (see below).
   - free (pre-call): `WRAgent.decide_free(obs)` LLM each step → heading/facing/throttle/call_for_ball
     (+ `end_route` when call_for_ball=true).
2. **QB** — GATED. Not invoked until the WR's call has been visible for ≥0.2s (2 ticks). Before that:
   hold. Once engaged: `QBAgent.decide(obs)` → `hold` | `throw(arc)` where arc ∈ {bullet, lob}.
   The ENGINE computes the lead/placement (QB never emits coordinates).
3. **CB** — `CBAgent.decide_move(obs)` LLM every step (LIVE + air). Intent locked once at air start.
4. Advance ball if airborne; resolve at eta ≤ 0.

The 0.2s gap: WR "hits the button" ~0.2s before/at its final break; the QB only "hears" it 0.2s
later and is told the call time + the locked direction. WR `end_route` executes immediately on call.

Broken-play / OOB handling is DROPPED for now (user: don't worry about it).

---

## WR end_route (deterministic remainder) — engine/endroute.py (FOUNDATION)

At call, the WR declares the rest of its motion. Engine executes it with no LLM until the ball is
airborne; then the WR comes alive to adjust.

```
end_route = {
  "heading": float,            # final committed run direction (deg)
  "mode": "run" | "settle",
  "settle_ticks": int|null,    # settle only: run heading this many 0.1s ticks, then brake & hold
}
```
- `run`: accelerate at `heading` (physics caps it → naturally coasts at top speed). Used by
  go/slant/out/post/corner/in/drag/double_move/zig/post_corner. This is "continue accelerating in
  the direction, then coast".
- `settle`: accelerate at `heading` for `settle_ticks`, then brake to a stop and hold the spot
  (facing handled when the WR comes alive). Used by curl/comeback ("cut, run 2 ticks, then stop").

The WR chooses run vs settle from PROMPT UNDERSTANDING of its route (not enforced by route name).

engine/endroute.py provides (FOUNDATION owns; QB + runner consume):
- `step_endroute(state, attrs, end_route, progress_ticks, dt) -> PlayerState`
- `simulate_endroute(state, attrs, end_route, progress_ticks, duration, dt) -> PlayerState`
- `solve_lead(qb_x, qb_y, wr_state, attrs, end_route, progress_ticks, arc, throw_power) -> dict`
   returns `{target:[x,y], tau, arrival_t, dist, feasible}` (bisection meeting-point on the WR's
   deterministic future path; `feasible` = within arm range for that arc).

---

## QB (Madden throw) — agents/qb_agent.py + observation_qb.py + prompts/qb_*.txt (QB SUBAGENT)

The QB only times the throw and picks **bullet vs lob**. The engine leads the WR (exact, because the
WR's post-call path is deterministic). Observation must show, for each of {bullet, lob}: the engine
meeting point, arrival time (s from now), the resulting throw distance, and whether it's in range
(bullet capped by arm strength → has a max distance; lob reaches farther). Prompt teaches the
tradeoff (bullet = less time for CB to close but limited range / flatter; lob = more air, more hang,
reaches deep but CB can close). QB output: `{"action":"throw","arc":"bullet"|"lob","reasoning":...}`
or `{"action":"hold","reasoning":...}`. Runner calls `solve_lead(...)` for the chosen arc to place
the ball. Drop drive/touch, target_z, target_coord from the QB's surface.

Contract signature (runner calls):
`QBAgent.decide(obs) -> {"action","arc"?,"reasoning"}`
`build_qb_observation(t, sack_clock, qb_state, qb_attrs, wr_state, wr_attrs, cb_state, cb_attrs,
   ball, lead_options: dict, wr_call_t, wr_call_heading, down, distance, history) -> str`
(runner computes `lead_options = {"bullet": solve_lead(...), "lob": solve_lead(...)}` and passes in.)

---

## WR — agents/wr_agent.py + observation_wr.py + prompts/wr_*.txt (WR SUBAGENT)

FRESH PROMPTING. No rail. Give CONTEXT (where the CB is, what the route is trying to do, the
physics of how the CB tracks/cuts) and let the WR decide. It must still run its assigned route shape
and try to create separation like an NFL WR — through prompt understanding, not enforcement. Failures
are data, not bugs (memory: high-freedom philosophy).

Two "buttons" exposed via the free-phase output:
- `call_for_ball: true` + `end_route{...}` = "this is my last break; from here I want the ball where
  I'm going." Locks the WR (deterministic exec). Anticipatory: call ~0.2s before/at the final break.
- `end_route.mode` lets the WR say run vs settle (curl/comeback stop).

Contract (runner calls):
`WRAgent.decide_free(obs) -> {"heading","facing","throttle","call_for_ball","end_route"?,"reasoning"}`
`WRAgent.decide_air(obs)  -> {"heading","facing","throttle","reasoning"}`
throttle ∈ {accelerate, coast, brake}.
`build_wr_free_observation(...) -> str`, `build_wr_air_observation(...) -> str` (signatures: see stub).

---

## CB — agents/cb_agent.py + observation_cb.py + prompts/cb_*.txt (CB SUBAGENT)

Already the most autonomous; KEEP that. Simplify intent: **collapse `swat` into `play_man`** — a CB
in man coverage contacts the WR to dislodge the ball; a PBU is an *effect* of playing man, not a
separate choice. Intent vocabulary is now **{"play_man", "go_for_pick"}** (go_for_pick = gamble for
the INT, higher risk). Default play_man. resolution.py reads this 2-value intent.

Contract (runner calls):
`CBAgent.pre_snap(obs) -> {"offset_yards","side","reasoning"}` (keep)
`CBAgent.decide_move(obs) -> {"heading","facing","mode","reasoning"}`
`CBAgent.decide_intent(obs) -> "play_man"|"go_for_pick"` (locked once)

---

## Catch — engine/resolution.py (CATCH SUBAGENT, review + implement)

Review the three-zone resolver (sep≥1.8 catch / ≤1.0 CB win / contested band rolls one die) +
facing/height/lane geometry for realism & over-complexity, and implement a simplification if
warranted. Inherent catch RNG is acceptable. MUST keep `resolve(...) -> {"outcome":...,
"separation":..., ...}` returning one of CATCH/PBU/DROP/INTERCEPTION/INCOMPLETE, and accept
`cb_intent ∈ {"play_man","go_for_pick"}` only (no "swat").

---

## Shared helpers — agents/observation_common.py (FOUNDATION)
`_heading_label`, `_accel_status`, `_height_label`, `_dist`, `FIELD_WIDTH`, history-table helpers.
Subagents import from here; do not duplicate.

## schema.py parsers (FOUNDATION defines; a subagent may tweak its own parser)
`parse_wr_free`, `parse_wr_air`, `parse_end_route`, `parse_qb`, `parse_cb_move`,
`parse_cb_intent`, `parse_cb_pre_snap`.
