# Left Off
Date: 2026-06-04

## What We Worked On
Built and debugged the WR agent (Phase A3) — LLM WR + LLM QB, no CB on field.

## What Got Done

**WR agent now working correctly (agents/wr_agent.py):**
- Pre-snap: reads CB alignment, outputs deception plan.
- Live (free): per-step heading + facing + throttle + call_for_ball. Three prompt states: free / committed / broken play.
- Call-for-ball validated mechanically: only allowed within ±45° of prescribed cut heading.
- Heading locked post-call (while ball held). Free again once ball is in air.
- record_heading() detects cuts (30°+ heading change) → QB sees detected_cut_t.
- trigger_broken_play(): called by runner when WR near sideline heading OOB.

**Deception behavior debugged and working:**
- Bug 1: WR was cutting to 40° at t=0.2 (1.8s early). Root cause: prompt said "cutting early to exploit cushion" — model went straight to slant heading.
- Fix: system prompt now explicitly distinguishes pre-cut phase (run 0°, no cut heading) vs cut window (execute break). Observation labels the current phase explicitly with "KEEP HEADING NEAR 0°" during pre-cut.
- Bug 2: model understood "jab step" but camped at jab heading for entire play (e.g., hdg=330° for 20 steps). A "jab" that lasts 2s is just running the wrong direction.
- Fix: live free prompt now shows exact correct pattern (jab 1 step → return to 0° → hold stem → jab again) and the explicit wrong pattern to avoid. Model now executes clean 1-step jabs alternating with 0° stem.
- Key insight added to system prompt: CB sees exact heading/speed and projects WR forward 0.5s. Deception = making that projection wrong by briefly changing heading then snapping back.

**Prompt files (agents/prompts/):**
- wr_system.txt: full job description, 2D deception mechanics, how CB intercept works, route execution phases.
- wr_live_free.txt: phase-gated pre-cut / cut-window / post-cut logic with concrete jab pattern examples.
- wr_live_committed.txt, wr_live_broken.txt, wr_ball_in_air.txt: unchanged.

**agents/observation.py:**
- Pre-cut phase message now says "KEEP HEADING NEAR 0° (straight upfield). Do NOT move to X° yet."
- Cut window and post-cut labels unchanged.

**Bugs fixed from previous session:**
- call_t NoneType format error: moved self.call_t = t into WRAgent.decide() so it's always set when called_for_ball is True.
- wr_call_pending guard: added `not wr_call_visible and not wr_call_pending` to prevent re-triggering every step.
- ScriptedQB / QBAgent interface: ScriptedQB gets t=t via isinstance dispatch; QBAgent signature untouched.

**Final A3 results (slant, no CB):**
- Cut at prescribed t=2.0 (perfect timing).
- Clean upfield stem with 1-step jabs at 330° interspersed.
- Max separation: ~10-11 yd. Catch outcome.

## What's Open / Known Issues
- detected_cut_t fires on the first jab (any 30°+ heading change), not the real route break. Will matter in A4 when CB reads it.
- QB sometimes holds 2-3 extra steps after WR calls (pass2 sees "MISS" due to stale WR heading projection). Non-critical in A3; may matter in A4.
- No WR deception against a real CB has been tested yet — all A3 runs have no CB.

## NEXT STEP
**A4 mode: LLM QB + LLM WR + LLM CB — all three agents live.**

Steps:
1. Add `a4_mode: true` flag to runner (or reuse existing runner — CB agent already wired for A2).
2. Wire WR agent into the existing A2 runner path (currently uses ScriptedWR in A2).
3. Create sim/scenarios/a4_wr_slant.yaml and a4_wr_comeback.yaml.
4. Run and observe: does WR deception actually move the CB? Does QB wait for the call?
5. Key thing to watch: CB gets exact WR heading each step — does the 1-step jab actually cause it to misstep, or is the CB fast enough to recover before the real cut?
