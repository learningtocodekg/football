# Left Off
Date: 2026-06-03
Last worked on: Phase A1 full build
What got done:
  - Complete project scaffold written and verified end-to-end
  - Engine (physics, ball, resolution, state machine), replay recorder, all agent
    modules, sim runner, pygame renderer, main.py all in place
  - Mock QB smoke test passes: CATCH outcome, 29 steps, telemetry correct
What's broken / open:
  - OPENAI_API_KEY not set in this environment — live LLM run blocked
  - Default model is gpt-4o-mini (in sim/scenarios/a1_basic.yaml); change
    qb_model to "gpt-5-nano" and qb_reasoning_effort to "low" once key is set
NEXT STEP (do this first):
  Set OPENAI_API_KEY, then run:
    python main.py --seed 42
  Then watch the replay:
    python -m render.renderer_pygame replays/play_42.json
