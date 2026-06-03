# PRD — "Gridiron Minds": LLM Agents Play American Football

**Owners:** KG, Bryce, Claude Code
**Status:** Draft v1 — approved architecture, ready to build
**Last updated:** 2026-06-02

---

## 1. Overview

A 2D American football simulator where every player is controlled by an independent LLM agent. Each agent perceives the field as structured text, reasons about the situation in football terms, and issues a movement/action *intent* each decision step. A deterministic physics engine turns intent into motion, and a deterministic resolution layer turns geometry + attributes + seeded randomness into outcomes (catch, drop, PBU, interception, sack).

The product is **entertainment + technical showpiece**, not a money-maker. The win is twofold:

1. **The clip** — watchable top-down replays where the AI's *reasoning* shows next to its movement. This is the TikTok/LinkedIn artifact.
2. **The depth** — a clean, reproducible multi-agent simulation that demonstrates real systems engineering. This is the resume/repo artifact.

### Success criteria
- A 1v1 play (QB + WR + CB) runs end-to-end, all three controlled by `gpt-5-nano`, and produces a believable outcome with a watchable replay.
- Each agent's decisions are legible: you can read *why* the CB broke on the ball or *why* the QB threw when it did.
- Plays are reproducible from a seed for debugging and for "best of" reels.
- The codebase scales from 1v1 → 11-ish v 11-ish without a rewrite of the core loop.

---

## 2. Core Design Principles

These are non-negotiable and shape every section below.

1. **Split the brain from the body.** The LLM decides *intent* in football language (`break_left`, `track_ball`, `go_for_pick`). A deterministic physics layer executes the kinematics. The LLM never does coordinate math or trig — it is bad at it, and offloading it makes motion realistic *and* cheaper.
2. **Resolution is deterministic + seeded, never an LLM vote, never a pure coin flip.** Outcomes are a function of geometry, attributes, and a seeded random roll. The LLM chooses *intent* (throw / go-for-pick / contest); math + RNG decide the result.
3. **Separation is measured at ball arrival, not at release.** This single rule is what makes the QB a genuinely interesting agent — it has to predict *future* separation across the ball's flight time, not just see who's open now.
4. **Feature-engineer the state for a weak model.** `gpt-5-nano` is fast and cheap but limited. Precompute every geometric quantity it might need (distance to opponent, angle to opponent, separation, time-to-arrival) so the agent reasons over features, not raw coordinates.
5. **Decouple simulation from rendering.** The sim emits a structured replay log (JSON, one record per timestep). Renderers consume it. This lets you re-render the same play at higher fidelity later, overlay reasoning, and compute metrics — without touching the sim.
6. **Reproducibility first.** Every play runs from a single seed. Same seed + same agent responses = identical play. (Note: LLM nondeterminism means we also log every prompt/response so a play is fully replayable from the log even if the model drifts.)
7. **Model-agnostic agent interface.** `gpt-5-nano` is the default everywhere, but the agent's model is a per-role config value. If nano proves too weak for QB reads, swap a stronger model for that one role without code changes.

---

## 3. Coordinate System & Field

- Field is `x ∈ [0, 53.3]` (lateral, sideline to sideline) and `y ∈ [0, 120]` (downfield, including two 10-yard end zones).
- `(0, 0)` = bottom-left, `(0, 120)` = top-left, `(53.3, 0)` = bottom-right, `(53.3, 120)` = top-right.
- Units are yards. Headings in degrees, `0°` = facing `+y` (upfield), increasing clockwise.
- Default snap: offense lined up around `y = 50`, ball at `(26.65, 50)`. Configurable per scenario.
- Out-of-bounds (`x < 0` or `x > 53.3`) ends a player's route; a ball landing OOB is incomplete.

---

## 4. Time Model

- **Timestep:** `0.1 s` (configurable). A standard pass play is ~5 s = ~50 steps.
- **Sack clock:** QB has `5.0 s` from snap to release, else sack (Phase A). In Phase C+ a sack can also occur earlier if the rush reaches the pocket.
- **Decision cadence:** configurable. Default = the agent decides every step (`gpt-5-nano` is cheap enough — see §13). To cut cost/latency, set cadence to every N steps and persist the last intent between decisions ("run this intent until I re-evaluate"). Cadence is a config knob, not a code change.
- The sim runs **faster or slower than real time** — it is computed first, rendered after. Per-play wall-clock compute time is irrelevant to playability.

---

## 5. Player Model

### 5.1 Attributes (Madden-style, fixed per player, 0–99)

| Attribute | Applies to | Effect |
|---|---|---|
| `max_speed` | all | top velocity (yd/s) |
| `acceleration` | all | how fast they reach top speed |
| `agility` | all | turn rate; how little speed is lost per degree of turn |
| `height` / `weight` | all | feeds catch radius, contact (Phase C+) |
| `stamina` | all | (Phase B+) speed decay over a drive; ignore in A |
| `catch` | WR | base catch probability |
| `catch_in_traffic` | WR | resistance to contest penalty |
| `route_running` | WR | (soft) tightness of cuts the physics allows |
| `coverage` | CB | how much it suppresses WR catch prob |
| `ball_skills` | CB | PBU/INT success rate |
| `play_recognition` | CB | (soft) quality of state features it gets / reaction lag |
| `throw_power` | QB | caps the max ball speed the QB may choose |
| `accuracy` | QB | placement error σ (set to 0 in v1, see §7) |

### 5.2 Kinematics (the "body")

State per player: `position (x,y)`, `velocity (speed, heading)`, `facing`.

Each step, given the chosen intent, the physics layer computes the new state under constraints:
- **Max speed** capped by `max_speed`.
- **Acceleration/deceleration** capped by `acceleration`.
- **Turn cost:** turning sheds speed. A 5° turn costs little; a 90° turn forces a near-hard-stop. The shed amount scales inversely with `agility`. This is the rule that makes "cut left" feel different from "drift left."
- **Backpedal mode (CB):** a CB can move in reverse relative to facing (backpedaling downfield while facing the QB), with a lower max speed than forward sprint. Flipping hips ("turn and run") is an explicit intent that has a one-step transition cost.

### 5.3 Action space (the legal "menu")

The agent does **not** free-pick speed/accel/angle (that lets it choose physically impossible combos). Instead, **the physics layer generates the legal menu each step from current state**, and the agent picks from it:

- `turn`: one of `{-90, -85, ..., -5, 0, +5, ..., +85, +90}°` (5° increments). `±90` = hard stop / hard cut.
- `throttle`: `{accelerate, hold, brake}`.
- Mode toggles where relevant: CB `{backpedal, turn_and_run}`; WR `{normal, jump/high-point}` (jump only meaningful in BALL_IN_AIR).

The menu the agent sees includes the *computed consequence* of each option (resulting speed, resulting position delta), so the agent reasons over outcomes, not raw geometry. Example menu entry: `"break_left_45": turn -45°, brake → speed 4.1 yd/s, new pos (24.1, 61.3)`.

QB-specific actions: `{hold, scan, pump, throw(target_coord, receiver_id, ball_speed, placement)}`. On `throw`, the QB chooses **both the target coordinate and the ball speed** (`ball_speed_mph`, range `[20, 60]` or whatever bounds you set, capped by `throw_power`). QB pocket movement (scramble/step-up) is **out of scope until Phase E**.

---

## 6. Agent Architecture

### 6.1 The loop (per decision step, per agent)
1. Sim assembles the agent's **observation** (state + features + legal menu).
2. Observation is rendered into the agent's prompt.
3. Agent (LLM) returns a structured action (JSON) + a one-line reasoning string.
4. Sim parses, validates against the legal menu, applies via physics. Invalid/unparseable → fallback to `hold` and log the error.
5. Reasoning + action logged to the replay record for that step.

Agents for the same step are queried **in parallel** (independent context per agent — no shared memory; each only knows what it perceives).

### 6.2 Observation / state representation (textual)
Each agent sees, in its prompt:
- **Self:** position, speed, heading, facing, its own attributes, current mode.
- **Others:** each visible player's position, velocity, heading (CB sees WR + QB; WR sees CB + QB; QB sees both).
- **Ball:** state (`held` / `in_air` with landing spot + ETA / `dead`).
- **Game:** clock, sack clock remaining, down/situation (minimal in A), field boundaries.
- **Precomputed features:** distance to opponent, bearing to opponent, current separation, (in air) time-to-arrival, distance from self to ball landing spot. **These exist so nano never does trig.**
- **Legal menu:** the options from §5.3 with computed consequences.
- **Role prompt:** a short system prompt defining the agent's job, its personality (energy level), and what "good" looks like for its position.

### 6.3 Action schema (strict JSON)
```json
{ "action": "break_left", "turn": -45, "throttle": "brake", "mode": "normal", "reasoning": "CB has inside leverage, breaking outside to the sideline" }
```
QB throw:
```json
{ "action": "throw", "receiver_id": "WR1", "target_coord": [22.0, 64.0], "ball_speed_mph": 48, "placement": "lead_outside", "reasoning": "He'll have a step to the sideline in ~0.6s, zipping it so the CB can't close" }
```
Parsing: request JSON-only output, strip code fences, validate, fall back on failure.

### 6.4 Model config
- Default model everywhere: **`gpt-5-nano`** via OpenAI Chat Completions (`v1/chat/completions`).
- Use `reasoning_effort="minimal"` for movement agents (low latency, the decision is simple and feature-fed). Consider `"low"` for the QB throw decision.
- Reasoning-family models restrict some sampling params — do not assume `temperature` behaves normally; validate against current API behavior during setup.
- Per-role override in config (e.g., bump QB to `gpt-5-mini` if nano reads are weak). Newer variants (`gpt-5.4-nano`, etc.) exist as drop-in swaps.

---

## 7. Ball & Throw Model

When the QB issues `throw`, it supplies a **target coordinate** and a **ball speed** (`ball_speed_mph ∈ [20, 60]`, upper bound capped by `throw_power`):
1. **Landing spot:** `actual_landing = target_coord + N(0, σ)`. In **v1, σ = 0** (ball goes exactly where aimed). The error model is wired in but disabled; flip `accuracy_enabled=true` later to introduce execution variance. `σ = σ_base(accuracy) × dist_factor × pressure_factor × motion_factor`.
2. **Per-step travel (physics):** the ball is a moving entity. On release, set its velocity vector toward `actual_landing` at the chosen `ball_speed`. Each timestep, advance the ball's position by `speed × dt`. The ball's live position + ETA are part of the observation WR/CB see. **Arrival** = the step the ball reaches `actual_landing` (or its position falls within a player's catch radius). For 2D, model straight-line travel; vertical arc is cosmetic, added in the renderer only.
3. Sim transitions to **BALL_IN_AIR**. WR and CB keep deciding each step against the live ball; WR can `track_ball` / `high_point`, CB can `play_man` / `go_for_pick` / `swat`.
4. At arrival → §8 resolution.

**Why ball speed is a real decision (and how it ties to the keystone):** a faster throw = shorter flight = less time for the CB to close, so separation-at-arrival stays larger and the window stays open — but it's a tighter, harder catch and overshoots if the WR hasn't gotten there. A slower lob = more air time = the CB closes and the window shrinks, but it's easier to drop in over coverage. So `ball_speed` is a genuine velocity-vs-touch tradeoff the QB agent must reason about, and it interacts directly with the separation-at-arrival rule.

---

## 8. Catch / Contest / Interception Resolution

Run at the timestep the ball arrives.

```
catch_radius   = f(WR.height, reach, jump)          # ~1–1.5 yd
ball_offset    = |actual_landing − WR_pos_at_arrival|
if ball_offset > catch_radius (+ WR in-air adjust): → INCOMPLETE   # QB led him somewhere he couldn't reach
separation     = |WR − CB| at arrival                # the keystone: measured AT ARRIVAL
P(catch)       = floor + (1 − floor) · sigmoid((separation − s_mid) / k)
                 # weighted by WR.catch & WR.catch_in_traffic; suppressed by CB.coverage
roll r ~ U(0,1)
if r < P(catch): → CATCH
else:            → contested sub-roll  (depends on CB's chosen intent)
```

**Design notes:**
- **Smooth sigmoid, not a hard threshold.** "≥3 yd = guaranteed" produces robotic cliff behavior agents will game. Open WR → ~certain; tight coverage decays to a `floor` (~0.15, because contested catches are real).
- **Keep the interception.** When the catch fails and the CB chose `go_for_pick`, sub-roll INT vs PBU vs incomplete, weighted by `CB.ball_skills` and how well-positioned the CB is. INT is rare but always possible — it's the best clip.
- **The CB's intent matters:** `play_man` → no INT possible, but bigger contest suppression; `go_for_pick` → INT possible but a whiff lets the WR catch clean (gamble punished); `swat` → safe PBU bias.

Outcome set: `CATCH`, `DROP` (uncontested miss from `1 − WR.catch`), `INCOMPLETE` (uncatchable placement), `PBU`, `INTERCEPTION`, `SACK` (clock/rush).

---

## 9. Blocking & Pass-Rush Model (Phases C+)

Introduced when O-line/D-line enter. Lighter spec here since it's later; will be expanded into its own doc before Phase C.

- **Engagement:** when a DL enters an OL's block zone, they engage. Each step is a **leverage contest**: DL picks a rush intent (`bull`, `swim`, `speed_edge`, `spin`), OL picks `anchor` / `mirror` / `punch`.
- **Win/loss:** contest resolved by attributes (`DL.power/finesse/speed` vs `OL.anchor/agility/awareness`) + seeded roll → DL gains/loses ground toward the pocket.
- **Pressure:** accrues as DL nears the pocket; feeds the QB's `pressure_factor` (and, when accuracy is enabled, throw σ). DL reaches pocket within 5 s → **sack**. OL holds 5 s → protected.
- Phase D adds assignment (who blocks whom), double teams, stunts/twists.

---

## 10. Simulation Engine

### Play lifecycle (state machine)
`PRE_SNAP → SNAP → LIVE (route develops, sack clock runs) → [QB throws] → BALL_IN_AIR → RESOLUTION → END`
Branches: clock expires during LIVE → `SACK`; (Phase C+) rush reaches pocket → `SACK`.

### Engine responsibilities
- Tick the clock; assemble observations; query agents (parallel); validate + apply actions; advance physics; check transitions; run resolution; emit replay log; compute end-of-play telemetry.

---

## 11. Replay Log & Visualization

### 11.1 Replay log (the contract between sim and renderer)
One JSON record per timestep:
```json
{ "t": 1.3, "phase": "LIVE", "sack_clock": 3.7,
  "players": [ {"id":"WR1","pos":[24.1,61.3],"heading":18,"facing":18,"speed":7.2,"action":"break_left","reasoning":"..."} , ... ],
  "ball": {"state":"held"},
  "events": [] }
```
Plus a play header (seed, scenario, rosters) and footer (outcome, telemetry).

### 11.2 Renderer (the triangle viz)
- **Top-down 2D.** Field drawn to scale with yard lines and end zones.
- Each player = a **small triangle pointing in its facing direction**. Color by team (offense/defense); a thin trail shows recent path.
- Ball = a dot; an arc/line during BALL_IN_AIR to the landing spot.
- **Reasoning overlay:** the current `reasoning` string floats near each player (toggleable) — this is the money feature for clips.
- **Output modes:** (a) interactive playback (scrub/pause), (b) headless render to MP4/GIF for sharing.
- **Stack:** pure-Python first. `pygame` for interactive, or `matplotlib` FuncAnimation → `ffmpeg` for headless video. No web frontend required for A–B. A lightweight web viewer (canvas + reasoning overlay) is an optional polish item, not a dependency.

**Frontend verdict:** you do **not** need a web frontend to build or demo this. The Python renderer consuming the replay log covers everything through Phase E. Build a web viewer only if/when you want a slick interactive embed for the public clip.

---

## 12. Telemetry & Evaluation

The stated purpose is "see how each AI does in its decision-making," so measurement is a first-class feature, not an afterthought.

Per play, log: outcome, max separation created (WR), min separation allowed (CB), time-to-throw, throw distance, P(catch) at release vs actual, pressure time (C+), decision latency, count of invalid/fallback actions.

Aggregate across plays: catch rate, INT rate, sack rate, avg separation by matchup, "good decision" rate (heuristic flags, e.g., QB threw into <floor windows). Build a simple "play browser" that lists plays with outcomes and lets you open any replay. This doubles as the highlight-reel finder.

---

## 13. Cost & Latency (gpt-5-nano)

`gpt-5-nano`: **$0.05 / 1M input, $0.40 / 1M output.**

Per-step cadence, Phase A4 (WR + CB decide each step, QB sparse): ~105 calls/play, ~1,000 in + ~120 out each → ~100K in + ~12K out → **≈ $0.01 / play**. 10,000 dev iterations ≈ **$100**. Coarser cadence (every 3 steps) ≈ ⅓¢/play.

**Cost is not a constraint.** The real risk is *quality*: nano may be too weak for nuanced QB reads. Mitigation: feature-fed prompts (§6.2), `reasoning_effort` tuning, and per-role model override. Latency only affects per-play compute time (parallel agent calls keep a play to seconds), never playability, since rendering is offline.

---

## 14. Tech Stack & Project Structure

- **Language:** Python 3.11+.
- **LLM:** OpenAI SDK, `gpt-5-nano` default (per-role configurable).
- **Render:** pygame (interactive) / matplotlib + ffmpeg (video).
- **Config:** scenarios + rosters + seeds in YAML/JSON.
- **Dev tooling:** Claude Code (KG has Max).

```
gridiron/
├── CLAUDE.md                 # project context, auto-loaded by Claude Code (points to .claude/*)
├── .claude/
│   ├── roadmap.md            # phases & subphases (this doc's §15, condensed)
│   ├── state.md              # what's built so far
│   ├── left_off.md           # where we stopped + next step
│   └── commands/
│       ├── break.md          # /break  → summarize session into left_off.md
│       └── resume.md         # /resume → read left_off.md, reload context
├── engine/
│   ├── field.py  physics.py  ball.py  resolution.py  lifecycle.py  state_machine.py
├── agents/
│   ├── base_agent.py  observation.py  prompts/  schema.py  llm_client.py
├── sim/
│   ├── runner.py  scenarios/  rosters/  seeds.py
├── replay/
│   ├── log_schema.py  recorder.py
├── render/
│   ├── renderer_pygame.py  renderer_video.py  overlay.py
├── eval/
│   ├── telemetry.py  metrics.py  play_browser.py
└── tests/
```

---

## 15. Phased Roadmap

> **Honest note on sequencing:** Phase A1 is ~60% of the total engine work, not a small first step. The QB cannot exist without the field, coordinate system, kinematics, time loop, ball-flight phase, resolution layer, replay log, and renderer. A1 forces you to build everything *except* the WR/CB agent brains. Budget for that.

### Phase A — 2D, 1-on-1 (QB + WR + CB)

**A1 — QB agent; WR & CB hardcoded (scripted paths).**
- *Builds:* the entire core engine (field, kinematics, time loop, ball flight, resolution §7–8, replay log, renderer) + the QB throw-decision agent.
- *Hardcoded:* WR runs a scripted route; CB follows a scripted path (you feed coordinates/velocity/heading per step).
- *Agent's job:* read the (scripted) developing separation, decide *when* and *where* to throw within 5 s.
- *Acceptance:* a play runs snap→throw→resolution→END; ball flight + catch/INT/PBU/incomplete/sack all fire correctly; renderer shows triangles + ball + reasoning; reproducible from seed.
- *Effort:* the big one. ~2–3 focused weekends / 2–3 weeks part-time.

**A2 — CB agent; WR hardcoded; QB irrelevant.**
- *Agent's job:* track/mirror the scripted WR — backpedal, read the break, flip hips, maintain tight coverage.
- *Acceptance:* CB maintains believable coverage vs several scripted routes; coverage quality (min separation allowed) is measurable and improves with tuning.
- *Effort:* ~1 week part-time.

**A3 — WR agent; CB scripted.**
- *Agent's job:* improvise a route (you chose full freedom) to create separation vs a scripted CB.
- *Acceptance:* WR produces coherent, separation-seeking movement; routes don't look random after tuning.
- *Effort:* ~1 week part-time. (Expect messy routes early — improvisation is the hard, pure-AI part.)

**A4 — All three agents live simultaneously.**
- The first "real" play: QB + WR + CB all `gpt-5-nano`.
- *Acceptance:* full plays run with sensible-looking decisions; telemetry + play browser usable; you can pull a watchable clip with reasoning overlay.
- *Effort:* integration + tuning, ~1–2 weeks part-time. **This is the MVP / first shareable artifact.**

### Phase B — 2D, 3-on-3 (3 WR + 3 CB)
- *New mechanics:* QB **progression reads** (choose among 3 receivers), CB **man assignment** (who covers whom), **same-team spacing / soft collision avoidance**.
- *Acceptance:* QB works a progression; CBs hold assignments; no players stacking on the same point.

### Phase C — 2D, 1 OL vs 1 DL (no skill players)
- *New mechanics:* the **blocking/pass-rush model** (§9) — engagement, leverage contest, pressure, pocket, sack. QB is a fixed point being protected.
- *Acceptance:* DL win → sack within 5 s; OL win → protected 5 s; pressure is measurable.

### Phase D — 2D, 3 OL vs 3 DL (no skill players)
- *New mechanics:* blocker **assignment**, double teams, **stunts/twists**.
- *Acceptance:* line coordinates as a unit; stunts can be picked up or break through.

### Phase E — 2D, full 3 OL + 3 DL + 3 WR + 3 CB
- *New mechanics:* **dynamic sack clock** (pressure ends the play early), QB reading **under pressure**, optional **QB pocket movement** (step-up/scramble — first appearance).
- *Acceptance:* a complete pass play with rush, protection, progression, and coverage all interacting; the full-system clip.

---

## 16. Housekeeping Files (templates)

### `.claude/roadmap.md`
```md
# Roadmap — Gridiron Minds
Phase A — 2D 1v1
  A1 QB agent (WR/CB scripted) — core engine + throw decision
  A2 CB agent (WR scripted)
  A3 WR agent (CB scripted)
  A4 all three live  ← MVP
Phase B — 3v3 (3 WR / 3 CB): progressions, man assignment, spacing
Phase C — 1 OL vs 1 DL: blocking/rush model
Phase D — 3 OL vs 3 DL: assignment, double teams, stunts
Phase E — full 3 OL/3 DL/3 WR/3 CB: dynamic pressure, QB under pressure
```

### `.claude/state.md`
```md
# Build State
Current phase: A1
Built: (nothing yet)
In progress: engine scaffolding
Not started: A2–E
Known issues: —
```

### `.claude/left_off.md`
```md
# Left Off
Date:
Last worked on:
What got done:
What's broken / open:
NEXT STEP (do this first):
```

### `.claude/commands/break.md`
```md
---
description: End this session — write a clean handoff into left_off.md
---
Summarize everything we did this session and update files:
1. Update `.claude/left_off.md`: date, what we worked on, what got done, what's broken/open, and a crisp single NEXT STEP.
2. Update `.claude/state.md` if the build state changed (phase, what's built, known issues).
3. Keep it concise and concrete — no fluff. This is a handoff to a fresh context.
```

### `.claude/commands/resume.md`
```md
---
description: Resume work — load context from left_off.md and continue
---
Read `.claude/left_off.md`, `.claude/state.md`, and `.claude/roadmap.md`.
Briefly restate where we are and what the NEXT STEP is, then start working on it.
Do not re-explain the whole project — just enough to confirm context is loaded.
```
> `.claude/commands/<name>.md` filename = command name → `/break`, `/resume`. (Newer alternative is `.claude/skills/<name>/SKILL.md`, which also enables autonomous invocation; the commands format is simpler and exactly matches "a slash command I type.")

---

## 17. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| nano too weak for QB reads | feature-fed prompts; `reasoning_effort` up; per-role model override |
| Improvised routes look random (A3) | start with separation-reward heuristics in the prompt; tune; accept early jank |
| Movement looks robotic | physics turn-cost + smooth catch curve; tune kinematics constants |
| LLM nondeterminism breaks "reproducible" | log every prompt+response; replay from log, not just seed |
| Invalid/unparseable actions | strict schema, validate against legal menu, fallback to `hold`, log rate |
| Scope creep into 11v11 too early | hard phase gates; A4 is the MVP, ship a clip before B |
| Video-gen temptation | explicitly out of scope; engine render only (see §18) |

---

## 18. Out of Scope (v1)

AI video generation / photorealistic render; pass interference & penalties; run-after-catch; running plays; special teams; full 11v11; QB scramble before Phase E; fatigue modeling before Phase B; QB accuracy error (wired but disabled, σ=0).

---

## 19. Glossary

**Intent** — the football-language decision the LLM emits. **Resolution** — deterministic conversion of geometry+attributes+seeded RNG into an outcome. **Separation** — WR↔CB distance, measured at ball arrival. **Legal menu** — the physics-generated set of valid moves shown to the agent each step. **Replay log** — per-timestep JSON the renderer and eval consume. **Keystone rule** — separation is measured at arrival, not release.
