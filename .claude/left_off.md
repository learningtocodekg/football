# Left Off
Date: 2026-06-06

## What We Worked On
Prompt and scaffolding fixes based on Run 4 (seed=42, gpt-5-nano) analysis and kg_notes.md.
No new run executed — all changes are code/prompt only, ready for Run 5.

## What Got Done

### P-NEW fix (pre-cut ball call) — two layers
1. **`agents/wr_agent.py`**: Hard enforcement gate added to `decide()`. If `call_for_ball=true` but heading is >45° away from `cut_heading`, the call is suppressed with a printed warning. Go routes (cut_time >= 9.0) are exempt.
2. **`agents/prompts/wr_live_free.txt`** + **`wr_system.txt`**: Replaced "call when you have separation" with "anticipate future separation" — WR must project its own future trajectory and the CB's trajectory forward 1–2 steps. Also added "call_for_ball=true is only valid if heading within 45° of cut direction — system will reject it otherwise."

### O7/N2 fix (cookie-cutter jabs) — live angle blacklist
**`agents/observation.py`**: After the MOVE LOG, a new block scans full play history. Any heading bucket used 3+ times with zero CB reaction (ΔHdg < 5°) is listed under "JABS USED THIS PLAY — CB did NOT react: DO NOT use these angles again." Per-step, live, structural constraint — not a suggestion.

### O1 fix (ball-in-air heading abandonment)
1. **`agents/prompts/wr_ball_in_air.txt`**: Completely rewritten. HEADING is locked ("DO NOT CHANGE IT — QB threw to your projected spot at this heading"). FACING is the only thing that changes to track the ball. Explains the mechanism.
2. **`agents/observation.py`**: Ball-in-air block now shows "YOUR HEADING: X° — DO NOT CHANGE THIS" and "HEADING = locked. FACING = rotate toward landing zone."

### O3/N6 fix (go route QB throw target)
**`agents/observation.py`**: Go-route hint in QB WR-signal block expanded — throw target must be past the CB's current y, not just at the WR's projected y. Explicit: "throw PAST the CB: target y > {cb_y}."

### QB post-call judgment
**`agents/observation.py`**: Added "WR CALLED FOR BALL — use your own judgment" block in the WR-called branch. WR calling ≠ mandatory throw. QB checks coverage and decides.

## What's Open / Known Issues
- **O4 (slant cut direction)** — was diagnosed as a downstream effect of P-NEW. If the heading gate fixes premature calls on slant, the WR will now have to execute the actual cut. Not separately addressed; watch Run 5.
- **O2 (corner: WR abandons break and returns to stem)** — not addressed. WR still has no concept of "terminal cut" vs "jab."
- **detected_cut_t** still fires on first heading hold, not guaranteed to be the real route break.
- **CB pre-snap alignment** not varying by route type.
- **CB intent almost always "swat"** — never changed.

## NEXT STEP
**Run 5: run all 10 A4 routes with seed=42 (gpt-5-nano) and compare to Run 4 (4C/2D/3PBU/1INT).**
- Primary watch: does P-NEW enforcement eliminate the pre-cut calls on slant/corner/in/curl?
- Secondary watch: does the angle blacklist produce any non-330°/30° jabs?
- Tertiary watch: do ball-in-air headings stay locked now?
- Log new problems if any emerge.

Run command: `.venv\Scripts\python.exe run_all_routes.py`
