# Left Off — 2026-06-20 (WR decision-tree build session)

## Branch: `freedom` (NOT main).
Madden-style input controller on the kept physics/ball engine. Research thesis: stateless-LLM spatial
reasoning with NO rails, NO prompt-stuffing — change the TYPE of control. WR contract built this session
from `.claude/wr_agent_design.md`.

## What we did this session — WR REBUILT as a self-authored conditional decision tree
The WR no longer decides per-tick. It authors its whole plan ONCE pre-snap (full reasoning budget) and the
engine executes it; the WR is only "alive" at the decision nodes it wrote. The plan IS its externalized
state. This implements `.claude/wr_agent_design.md`.

- **Plan schema** (`agents/schema.py:parse_wr_plan` / `parse_wr_node_choice`): plan = `{idea, start,
  nodes}`. node = `{action:{heading,effort}, hold (s to run the action before deciding), read, branches}`.
  branch = `{cond, goto}` (move to another node) OR `{cond, call:<end_route>}` (call for the ball). Conds
  are the WR's own words but grounded in geometry. Empty-branch nodes get a default "commit and run" so the
  play can't dead-end.
- **WRAgent** (`agents/wr_agent.py`): `author_plan` (one-time pre-snap, with `_fallback_plan` backstop on
  parse failure → stem to designed break + break/call from ROUTES) and `decide_node` (pick one pruned
  branch by index). `decide_free`/`parse_wr_free`/`wr_free.txt` are now superseded (left in place, unused).
  `decide_air` unchanged.
- **Observations** (`agents/observation_wr.py`): `build_wr_pre_snap_observation` (route shape + PURPOSE +
  designed-break time/depth + CB alignment + field frame — the authoring call) and
  `build_wr_node_observation` (live YOU/CB geometry + move log + the node's authored read + its pruned
  options). The geometry block reports the relative frame: "UPFIELD of you (cushion)" / "even" / "BEHIND
  you (beaten)".
- **Prompts**: new `wr_plan.txt` (author the tree; wall-clock spine; ground your conds; shallow 1–3 nodes;
  a fake is ONE node) + `wr_node.txt` (evaluate your authored read vs the field, pick a branch). Reframed
  `wr_system.txt` ("you are stateless; think once pre-snap, the plan is your memory").
- **Runner** (`sim/runner.py`): authors the plan pre-snap, then a node-walk in the LIVE loop — between
  nodes it runs the durative action with NO LLM; at a node's `hold` it wakes the WR to pick a branch; a
  `call` branch locks the `end_route` exactly like the old call path (commit_step / WR_CALL event / QB
  gate unchanged). Imports swapped from `build_wr_free_observation` → pre-snap + node builders.

## Results (seed 42, gpt-5-nano; judge route/coverage quality, NOT catch/PBU label)
- **Juke-spam + oscillation ELIMINATED** on the first run — both were artifacts of per-tick re-deciding.
  0 parse errors across all runs.
- **Slant — PASS** (2/2 clean): clean vertical stem, ONE decisive inside break. Open both reps (2.22yd →
  air INT vs the elite CB; 1.02→3.17 CATCH).
- **Comeback — PASS** (2/2 CATCH): clean stem to the ~1.9s break, decisive 225° break-back, CB carried
  deep. Big separation (4.38→6.11; 1.37→4.57).
- **Go — calls too early** (the one open issue): wall-clock spine front-loads the lone decision node near
  ~1.0s and the WR commits there, calling at 0.4–1.1yd sep before it has overtaken the CB's cushion (a go
  is "open" only once the CB is EVEN/BEHIND, ~2.0–2.5s for a 9.5-speed WR). The WR misreads "CB giving
  cushion" (still upfield/ahead) as the green light. Editing the go PURPOSE ("full speed ahead… call only
  once level with or past him, take it over his head") REMOVED an earlier self-sabotaging hard-fake mode
  (verticals are clean now, detected_cut None) but did not move the call timing.

## Decision / reframe (user)
- The early WR call is **the QB's problem, not the WR's.** A receiver declaring intent early is realistic;
  the discipline of waiting for the throwing window belongs to the call-gated QB, which can simply HOLD.
  We deliberately did NOT patch the WR call timing (that would be a rail). → QB timing is the next thread.
- Go's purpose edit kept (good): removed the hard-fake self-sabotage without prescribing deception.

## Broken / open
- **Go premature call** — accepted for now; to be addressed via QB throw-timing (QB waits for the window),
  not by gating the WR.
- **QB still PAUSED** (known lob-on-short-route issue) — and now also owes the go "wait for level/past"
  window. This is the next focus.
- `wr_free.txt` / `decide_free` / `parse_wr_free` are dead (superseded by the plan path); left in place.

## NEXT STEP
Fix the QB throw-timing so it holds the ball until the WR is actually open, instead of throwing on the
(possibly early) call — especially the go window: don't release until the WR is EVEN WITH / PAST the CB
(sep@throw should reflect a real window, not the call instant). QB is currently PAUSED; this un-pauses it.
