# Build State
Current phase: A1
Built:
  - engine/ (field, physics, ball, resolution, state_machine)
  - replay/recorder.py
  - agents/ (schema, observation, llm_client, qb_agent, scripted WR/CB)
  - sim/ (seeds, runner, rosters/default.yaml)
  - render/renderer_pygame.py
  - main.py (--local/--model flags for Ollama support)
  - requirements.txt + python-dotenv (.env support)
  - tests/test_e2e.py (two-pass mock QB smoke test — passes)
  - tests/test_ollama.py (scratch debugging file — not a real test, can delete)
  - Ollama local model support (qwen3:8b default, provider="ollama")
  - 4 scripted routes: slant, post, comeback, out
  - 6 scenario YAMLs: a1_basic, a1_local, a1_1st10_slant, a1_2nd25_post, a1_3rd10_comeback, a1_3rd3_out
  - article.md: scaffolding decisions log for future article

QB agent architecture (two-pass):
  - Pass 1: model reads field, outputs hold or thinking+rough_target
  - Pass 2: concrete options at target (5 speed tiers: bullet/hard/medium/soft/lob),
    each showing WR projected position at arrival and catchable/miss verdict
  - agents/prompts/: qb_system.txt, qb_pass1.txt, qb_pass2.txt

QB observation includes:
  - Positions, speeds, headings, current separation with coverage context
  - Ball travel time reference (bullet/regular/lob) to current WR distance
  - Route schedule: cut times, headings, plain-English labels, estimated WR position at each cut
  - Movement history (last 20 steps)
  - Expected open timestep hint (per scenario)

Resolution (engine/resolution.py):
  - PBU only possible if CB within 1 yd of WR OR CB in passing lane (1.5 yd from ball path)

Scripted CB (agents/scripted.py):
  - 2.0s lockup phase: mirrors WR directly before reaction delay engages

Ollama (llm_client.py):
  - No response_format for ollama provider (causes empty content in qwen3)
  - Falls back to model_extra["reasoning"] if content is empty
  - Functional but slow (~10-30s/call on local hardware)

All scenarios use: gpt-5-nano, reasoning_effort="low", max_completion_tokens=4000

Not started: A2 (CB agent), A3 (WR agent), A4 (all live), B–E

Known issues:
  - QB throws too early on developing routes (t=1.6s on slant when cut is t=2.0s)
  - WR projection in pass 2 uses current heading only — pre-cut throws shown as misses is correct behavior, but model still sometimes commits before the cut
  - Ollama runs functional but slow; not practical for rapid iteration
