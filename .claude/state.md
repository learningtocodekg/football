# Build State
Current phase: A1
Built:
  - engine/ (field, physics, ball, resolution, state_machine)
  - replay/recorder.py
  - agents/ (schema, observation, llm_client, qb_agent, scripted WR/CB)
  - sim/ (seeds, runner, rosters/default.yaml, scenarios/a1_basic.yaml)
  - render/renderer_pygame.py
  - main.py, requirements.txt
  - tests/test_e2e.py (mock QB, full loop verified)
In progress: live LLM run (needs OPENAI_API_KEY)
Not started: A2 (CB agent), A3 (WR agent), A4 (all live), B–E
Known issues:
  - Default model is gpt-4o-mini (scenario yaml); swap to gpt-5-nano when available
  - QB model uses no reasoning_effort (null in scenario) — set to "low" for o-series models
