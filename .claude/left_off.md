# Left Off
Date: 2026-06-03
Last worked on: Phase A1 — QB agent scaffolding, realism fixes, two-pass decision system

## What Got Done

**Realism fixes:**
- CB lockup: CB now stays tight on WR for first 2.0s before reaction delay kicks in (was giving up 4+ yd gap in first second)
- PBU now requires CB within 1 yd of WR at arrival OR CB in passing lane — was firing at 5.91 yd separation (broken)
- Removed hardcoded qb_min_hold_time from scenario YAML; QB is consulted every step from t=0.5s onward

**QB observation improvements:**
- Removed pre-computed projected throw options (model was anchoring on them instead of reasoning)
- Added route schedule: cut time, heading, plain-English direction label, estimated WR position at cut time
- Added ball travel time reference (bullet/regular/lob) at current WR distance
- Added WR-CB separation context (>3 open, 1.5–3 contested, <1.5 tight)

**Two-pass decision system (agents/qb_agent.py, agents/schema.py):**
- Pass 1: model reads field, outputs `hold` or `thinking` with rough landing target
- Pass 2: concrete options shown at that target (5 speed tiers), each showing where WR will *actually be* at arrival and whether it's catchable or a miss
- Forces model to confront whether its intended target is physically reachable

**Model/config:**
- All scenarios switched to gpt-5-nano, reasoning_effort="low", max_completion_tokens=4000
- Added python-dotenv; .env file now loaded automatically (OPENAI_API_KEY)
- README updated with --local variants for all 4 hardcoded scenarios

**article.md created** — tracks every scaffold addition + outcome for future article

## What's Broken / Open
- QB still throws too early sometimes — pass 2 shows "MISS by Xyd" correctly, but model occasionally picks an option anyway (needs more testing)
- WR projection in pass 2 uses current heading/speed only — doesn't account for pending cuts, so post-cut targets still show as misses until cut actually happens
- article.md not exhaustive yet — needs results section once QB is playing well
- test_e2e.py uses old single-pass `decide()` signature — will break if run (needs updating to match new `decide(obs, qb_x, qb_y, wr_x, wr_y, wr_heading, wr_speed)`)

## NEXT STEP
Fix test_e2e.py to match new QBAgent.decide() signature, then run a full play and verify the QB waits for the slant cut (t=2.0s) before throwing:
  python main.py --scenario sim/scenarios/a1_1st10_slant.yaml --seed 42
