# WR Agent Design — Self-Authored Decision Tree (freedom branch)

Status: DESIGN, not yet built. Co-designed 2026-06-19. This is the stored spec for the next WR build.

## Research framing
Question: can a **stateless** LLM run routes through real geo-spatial reasoning with **NO rails** and
**NO forcing mechanics**? `main` solves route-running with a soft rail — that is explicitly NOT the goal.
Two dead ends are ruled out: rails (override the LLM's output) and prompt-stuffing (tried repeatedly,
documented in state.md, does not work). The lever is the **TYPE of control the LLM has** — its action
space, representation, and query cadence — not the prompt text.

## Core idea — the plan IS the state
A stateless model can't hold intent across 0.1s ticks, so we **externalize its intent into an artifact
it authors itself**, once, with full reasoning budget, and thread it forward. The artifact is a shallow
**conditional decision tree** for the route, keyed to what the WR reads off the CB. This is exactly how a
real WR thinks:
- "Stem fast, slow near the break, jab away, then turn-and-sprint where I want — BUT if the CB plays
  cushion, cut EARLIER to keep him backpedaling; if he's tight, fake-juke, run a LONGER stem, then break."
- Comeback: "sell a corner, then cut back; if cushioned cut earlier; if tight, drive him upfield first,
  then break down."

The tree default-action per node + a few branch points ("watch for X; if cushion → A, if tight → B") is
the externalized state. Each per-step decision becomes small and pre-scoped by past-self. Expensive
reasoning happens ONCE up front; runtime collapses to "execute / evaluate this node."

This kills both observed failure modes structurally:
- **Oscillation** dies — the WR isn't *asked* to re-decide a stable situation; it's mid-node, executing.
- **Juke-spam** dies — a fake is one authored node, not a per-tick reflex.

## Timing model — WALL-CLOCK anchored (DELIBERATE; do not change to milestone-only)
Decision nodes live on a **wall-clock timeline**. This is a deliberate choice by the user: without time
anchors the WR drifts off and **completely ditches the route design** (we saw exactly this when the WR
ran free per-tick). So:
- The pre-plan places its decision/branch nodes at authored TIMES.
- **The only moments the WR agent is "alive" (queried) are these decision nodes.** Between nodes the
  engine executes the node's durative action with no LLM call.
- After a branch is taken, the following nodes are timed **RELATIVE to that decision** — e.g.
  "decision + 0.2s", not an absolute "t=0.8s". Different branch choices ⇒ different downstream timelines,
  so the tree's shape and timing differ per path.

(Note: this is the opposite of "milestone-keyed only." We keep wall-clock as the spine; reads modify the
branch taken and the relative offsets, but time keeps the WR honest to the route.)

## Conditions / reads — LLM-invented vocabulary, LLM-evaluated (for now)
- The LLM **invents its own condition vocabulary** in the pre-plan (e.g. "if he's bailing", "if he's
  pressed up", "if he bit my jab"). No fixed engine vocab in v1.
- Because the words are the LLM's own, the **pre-plan must concretely define what each word means in
  reality** for its future self — i.e. ground each read in observable geometry ("'cushion' = he's 3+ yd
  off and backpedaling") so the future-self decision at the branch is unambiguous.
- At a branch node the **LLM evaluates the condition itself** (it is alive at that node anyway) and picks
  the branch, seeing only that node's pre-authored options.
- FUTURE WORK (memory + handoff): consider making condition evaluation **mechanical** (engine-checked
  structured predicates) once the LLM-authored version is understood. Kept LLM-side for v1 by user choice.

## Pruning — show only the current node
The LLM is never shown the whole tree mid-play. At a node it sees only that node's authored options.
Once it takes path X, only X's subtree is live for the rest of the play.

## Reuse (compose, don't rebuild)
- Pre-snap planning hooks exist: `WRAgent.pre_snap`, `build_wr_pre_snap_observation`. Extend
  "alignment/deception hint" → "author the full conditional plan (decision tree)."
- Durative execution exists: `engine/endroute.py` `step_endroute` / `simulate_endroute` run committed
  motion with no LLM. Generalize "final break only" → "every node's action."
- Runner already has a committed-execution branch (`sim/runner.py` ~196-202) and event stamps
  (`detected_cut_t`, `vertical_committed`) usable as read inputs.

## Build sketch
- Schema: plan = ordered nodes; node = `{action (durative, direction + effort), at_time (abs for node 0,
  relative-to-branch after), branches: [{cond_label, goto}] }`. Authored by a new `decide_plan` step
  (extends pre_snap).
- Runner: track current node + clock; advance the node's durative action between nodes; at a node's time,
  wake the LLM to evaluate its own condition and pick a branch (showing only that node's options).
- `call_for_ball` / `end_route` remain the final-break primitive (already durative).
- Apply to WR first. QB stays PAUSED (known lob-on-short-route issue).
- Judge by coverage / route quality, NOT catch/PBU (memory `feedback_outcome_vs_quality`).

## Open items
- **Off-tree fallback:** if reality matches none of the authored branches, do we allow ONE mid-play
  re-plan, or hold the last action to the ball? (Wall-clock anchoring reduces but doesn't eliminate this.)
- **Mechanical conditions:** the future-work item above.

## Why the CB can NOT use this design (→ next session's problem)
This whole approach depends on **planning ahead**. The CB has no such privilege: it is **purely reactive
to the WR's actions** — it cannot author a route-like timeline because it doesn't own the initiative.
Good testing of THIS WR design also depends on a competent CB (a chaotic CB makes any WR look fine/broken
at random). So the CB needs its OWN approach to stateless coherence — that is the next design problem.
