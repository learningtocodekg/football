# Gridiron Minds — LLM Agents Play American Football

A 2D American football simulator where players are controlled by LLM agents. Each agent reads the field as structured text, reasons about the situation in football terms, and issues movement/action intents each decision step. A deterministic physics engine turns intent into motion; a deterministic resolution layer turns geometry + attributes + seeded randomness into outcomes.

---

## How to Run

### 1. Set up virtualenv and install dependencies
```
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```
All commands below assume the venv is active (or prefix with `.venv\Scripts\python`).

### 2. Run the smoke test (no API key required)
```
python tests/test_e2e.py
```
Expected output: `--- PASS ---` with outcome, step count, and telemetry.

### 3. Generate a demo replay (no API key required)
```
python gen_demo.py          # uses seed 7 → replays/demo_7.json
python gen_demo.py 42       # custom seed
```
The mock QB waits for the slant to open, then throws with realistic reasoning text.

### 4. Watch a replay
```
python -m render.renderer_pygame replays/demo_7.json
```
**Controls:** `SPACE` play/pause · `← →` step frame · `R` toggle reasoning overlay · `+/-` speed · `Q/Esc` quit

### 5. Run a live LLM play (requires OpenAI API key)
```
set OPENAI_API_KEY=sk-...
python main.py --seed 42
python -m render.renderer_pygame replays/play_42.json
```
Optional flags: `--scenario`, `--roster`, `--output`

**Hardcoded situations** — pre-built scenarios with specific down/distance and route.

With OpenAI:
```
python main.py --scenario sim/scenarios/a1_1st10_slant.yaml --seed 42
python main.py --scenario sim/scenarios/a1_2nd25_post.yaml --seed 42
python main.py --scenario sim/scenarios/a1_3rd10_comeback.yaml --seed 42
python main.py --scenario sim/scenarios/a1_3rd3_out.yaml --seed 42
```
With a local Ollama model (no API key needed):
```
python main.py --local --scenario sim/scenarios/a1_1st10_slant.yaml --seed 42    # 1st & 10 — Slant
python main.py --local --scenario sim/scenarios/a1_2nd25_post.yaml --seed 42     # 2nd & 25 — Post
python main.py --local --scenario sim/scenarios/a1_3rd10_comeback.yaml --seed 42 # 3rd & 10 — Comeback
python main.py --local --scenario sim/scenarios/a1_3rd3_out.yaml --seed 42       # 3rd & 3 — Out
```
Watch any of them with:
```
python -m render.renderer_pygame replays/play_42.json
```

python main.py --scenario sim/scenarios/a3_wr_slant.yaml
### 6. Run with a local model via Ollama (no API key needed)

Install [Ollama](https://ollama.com), then pull a model and run it:
```
ollama pull qwen3:8b
ollama serve              # starts the local API at localhost:11434
```
In another terminal:
```
python main.py --local --seed 42
python main.py --local --model qwen3:8b --seed 42
python -m render.renderer_pygame replays/play_42.json
```
Or use the pre-made local scenario directly:
```
python main.py --scenario sim/scenarios/a1_local.yaml --seed 42
```
Other models that fit in 8 GB VRAM (RTX 5060 / RTX 3070 / etc.):
| Model | Pull command | VRAM |
|---|---|---|
| Qwen3 8B (recommended) | `ollama pull qwen3:8b` | ~5–6 GB |
| Llama 3.1 8B | `ollama pull llama3.1:8b` | ~5 GB |
| Mistral 7B | `ollama pull mistral:7b` | ~4.5 GB |
| Phi-4 mini | `ollama pull phi4-mini` | ~3.5 GB |

---

## Project Status

**Current phase: A1** — QB is an LLM agent; WR and CB are scripted (deterministic paths). The full engine is built and verified end-to-end with a mock QB. Live LLM play is blocked only on setting `OPENAI_API_KEY`.

### Phase Roadmap
| Phase | Description | Status |
|---|---|---|
| **A1** | QB agent, WR + CB scripted | **Built / Verified** |
| A2 | CB agent, WR scripted | Not started |
| A3 | WR agent, CB scripted | Not started |
| A4 | All three live — **MVP** | Not started |
| B | 3v3: QB progressions, man assignment | Not started |
| C | 1 OL vs 1 DL blocking/rush model | Not started |
| D | 3 OL vs 3 DL: stunts, double teams | Not started |
| E | Full 3 OL/DL/WR/CB with dynamic pressure | Not started |

---

## Directory Structure

```
football/
├── main.py                        # Entry point: run_play(scenario, roster, seed, output)
├── gen_demo.py                    # Generate replay with mock QB (no API key needed)
├── requirements.txt               # openai, pygame, pyyaml
│
├── engine/
│   ├── field.py                   # Field constants (53.3 × 120 yd), in_bounds()
│   ├── physics.py                 # PlayerAttrs, PlayerState, apply_action() kinematics
│   ├── ball.py                    # BallState, throw_ball(), advance_ball()
│   ├── resolution.py              # resolve() — catch/PBU/INT/DROP at ball arrival
│   └── state_machine.py           # PlayPhase enum: PRE_SNAP→LIVE→BALL_IN_AIR→RESOLUTION→END
│
├── agents/
│   ├── llm_client.py              # call_llm() wrapper around OpenAI SDK
│   ├── schema.py                  # parse_qb_action() — JSON parser + validator
│   ├── observation.py             # build_qb_observation() — structured text prompt builder
│   ├── qb_agent.py                # QBAgent class — calls LLM, tracks errors
│   ├── scripted.py                # ScriptedWR (slant route) + ScriptedCB (man coverage)
│   └── prompts/
│       └── qb_system.txt          # QB system prompt
│
├── sim/
│   ├── runner.py                  # run_play() — main game loop, orchestrates all modules
│   ├── seeds.py                   # make_rng(seed) — seeded random for reproducibility
│   ├── rosters/
│   │   └── default.yaml           # QB/WR1/CB1 attributes (Madden-style 0–99 stats)
│   └── scenarios/
│       └── a1_basic.yaml          # Model, scripted route config, reaction delays
│
├── replay/
│   └── recorder.py                # Recorder class — collects steps, saves JSON replay log
│
├── render/
│   └── renderer_pygame.py         # Interactive top-down pygame viewer
│
├── replays/
│   ├── demo_7.json                # Pre-generated demo replay (seed 7)
│   └── test_mock.json             # Replay from smoke test
│
└── tests/
    └── test_e2e.py                # End-to-end smoke test with mocked LLM
```

---

## What Is Built (A1)

### Engine
- **Field** ([engine/field.py](engine/field.py)): constants, `in_bounds()`. Coordinate system: `x ∈ [0, 53.3]` (sideline to sideline), `y ∈ [0, 120]` (upfield = +y), 0° heading = upfield, clockwise.
- **Physics** ([engine/physics.py](engine/physics.py)): `PlayerAttrs` (Madden-style stats), `PlayerState` (pos/speed/heading/facing/mode), `apply_action()`. Turn cost sheds speed proportional to degrees turned, scaled by `agility`. Throttle: `accelerate / hold / brake`.
- **Ball** ([engine/ball.py](engine/ball.py)): `BallState`, `throw_ball()` (sets velocity vector from QB to target at chosen mph), `advance_ball()` (straight-line per-step travel). Tracks `eta` countdown.
- **Resolution** ([engine/resolution.py](engine/resolution.py)): `resolve()` runs at ball arrival. Checks `ball_offset` vs `CATCH_RADIUS` (1.3 yd) → INCOMPLETE if uncatchable. Then smooth sigmoid catch probability over separation, weighted by WR.catch and CB.coverage. Contest outcomes by CB intent (`go_for_pick` → INT chance, `swat` → PBU bias, `play_man` → default contest).
- **State machine** ([engine/state_machine.py](engine/state_machine.py)): `PlayPhase` enum.

### Agents
- **QB LLM Agent** ([agents/qb_agent.py](agents/qb_agent.py)): wraps `call_llm()`, parses action JSON, falls back to `hold` on parse error, tracks call count and error count.
- **Observation builder** ([agents/observation.py](agents/observation.py)): builds the QB's text prompt with player positions, speeds, headings, current separation, and **projected throw options** (5 time horizons × extrapolated WR/CB positions, separation at arrival, required mph, feasibility). This is the key feature-engineering that makes `gpt-4o-mini` viable — the agent never does trig.
- **LLM client** ([agents/llm_client.py](agents/llm_client.py)): singleton OpenAI client, supports `reasoning_effort` parameter for o-series/gpt-5-nano models.
- **Schema parser** ([agents/schema.py](agents/schema.py)): strips markdown fences, validates JSON, returns `hold` or `throw` dicts.
- **Scripted WR** ([agents/scripted.py](agents/scripted.py)): slant route — sprints upfield for `wr_cut_time` seconds (default 2.0 s), then cuts inside to `wr_cut_heading` (default 40°).
- **Scripted CB** ([agents/scripted.py](agents/scripted.py)): man coverage with `REACTION_DELAY = 0.3 s`. Mirrors the WR's position history with a delay, staying 1.5 yd upfield of WR.

### Sim
- **Runner** ([sim/runner.py](sim/runner.py)): `run_play()` — loads YAML scenario + roster, initializes states, runs the game loop at `DT = 0.1 s`, sack clock = 5.0 s, max 200 steps. QB decides every step. Emits replay JSON, prints telemetry.
- **Recorder** ([replay/recorder.py](replay/recorder.py)): collects per-step snapshots (t, phase, sack_clock, player states + actions + reasoning, ball state, events) and saves as JSON with header + footer.

### Renderer
- **Pygame renderer** ([render/renderer_pygame.py](render/renderer_pygame.py)): full interactive top-down viewer. Players drawn as triangles pointing in facing direction, with fading trail. Ball as dot with arc line to landing spot + ETA. Reasoning overlay (toggleable with R) floats next to each player — this is the clip-worthy feature. Sidebar shows phase, sack clock, events, result, telemetry.

### Tests
- **test_e2e.py** ([tests/test_e2e.py](tests/test_e2e.py)): monkey-patches `call_llm` with a deterministic mock QB (holds until t ≥ 2.3 s, then throws to slant spot). Runs full `run_play()`, validates replay schema, asserts outcome is a valid enum value. **Passes without any API key.**

---

## Key Design Points (for quick context)

- **Separation is measured at ball arrival, not release.** The QB must predict where WR and CB will be when the ball gets there, not just now. The observation builder precomputes this for 5 time horizons.
- **Physics controls the body; LLM controls intent.** The LLM never does coordinate math. It picks from a feature-enriched menu.
- **σ = 0 for now.** Throw accuracy error is wired in (`resolution.py`) but the ball lands exactly at `target_coord`. Flip `accuracy_enabled=True` later.
- **CB intent is hardcoded to `"play_man"`** in `runner.py:162` during BALL_IN_AIR phase. This is a stub for the A2 CB agent.
- **Model default is `gpt-4o-mini`** (in `sim/scenarios/a1_basic.yaml`). `gpt-5-nano` is the PRD target but may not be widely available. `reasoning_effort` is `null` for gpt-4o-mini (it uses temperature, not reasoning_effort).

---

## Known Issues / Next Steps

1. **OPENAI_API_KEY not set** — live LLM play blocked. Run `gen_demo.py` or `tests/test_e2e.py` to verify without an API key.
2. **A2 (CB agent) not started** — CB intent in `runner.py` is hardcoded to `"play_man"`. Next phase builds a LLM CB agent with backpedal, hip-flip, go-for-pick intents.
3. **A3 (WR agent) not started** — WR runs a fixed slant. Next after A2.
4. **A4 (all live) not started** — MVP: all three agents LLM simultaneously, parallel calls.
5. **No eval/telemetry module** — PRD describes `eval/` (metrics, play browser). Not built.
6. **No video export** — PRD mentions `renderer_video.py` (matplotlib + ffmpeg). Not built.
