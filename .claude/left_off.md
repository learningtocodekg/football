# Left Off
Date: 2026-06-07

## What We Worked On
WR agent freedom redesign — moved from prescriptive phase-by-phase instructions to a context-only model. Then iterated on several bugs surfaced by live runs (seed=42, gpt-5-nano, A4 slant).

## What Got Done

### WR freedom redesign (previous session, carried in)
- Removed jab angle blacklist, pre-computed turn cost, oppressive phase instructions from observation
- Route schedule kept as shared QB/WR language but no longer enforced timing
- `wr_system.txt` rewritten: deception section now explains CB tracking mechanic and why multi-step commitment is required
- `wr_live_free.txt` simplified to context + deception reminder

### Persistent WR scratchpad (`wr_note`)
- WR now outputs a `wr_note` field each step — one line, ~120 chars
- `WRAgent.wr_note` stores it; passed back into next step's observation as "YOUR NOTE (from last step)"
- `parse_wr_live` in schema.py returns it; all prompt templates updated to include `wr_note` in JSON schema
- The note is a living plan — WR is told to overwrite it, not accumulate it, and to verify it against the move log (not treat it as ground truth)
- No hard truncation in code — WR owns the discipline

### Encoding fix
- Reasoning strings were `.encode("ascii","replace").decode("ascii")` in runner.py — all non-ASCII (°, →, ') became `?`
- Stripped all 9 instances; now passes through as UTF-8

### Calling-too-early fix
- WR was calling for ball with heading correct but CB still right next to it
- Added to `wr_system.txt` and `wr_live_free.txt`: call only when BOTH heading is near break AND separation is actually real and growing

### Ball-in-air facing fix
- Resolution scores facing toward QB (ball comes FROM QB), but observation was telling WR to face the landing zone (upfield) — opposite directions on a slant
- Fixed observation to show "QB is at bearing X° from you — ball is coming from that direction"
- Fixed `wr_ball_in_air.txt` to say: the ball is coming from the QB, face that direction to see it
- Added facing compass anchors (0°=upfield, 90°=right, 180°=toward QB, 270°=left) to both `wr_system.txt` and `wr_ball_in_air.txt`

### Note hallucination fix
- WR was writing "2-step fake completed" after only 1 step
- Added to `wr_live_free.txt`: "Your note is a plan — not ground truth. Always verify against the move log before acting on it."

## What's Open / Known Issues
- **WR still calls too early sometimes** — calls at t=1.5 with 1 step of fake, says "deception completed"
- **QB throws too fast after WR call** — throw_distance consistently 10–17yd on slant, ball arrives before WR has real separation
- **CB swats almost every play** — intent almost always swat, rarely play_man or INT
- **All plays ending PBU or DROP** — no CATCH yet this session on seed=42 slant
- **max_separation=5.02 every run** — same seed, same WR behavior, separation profile unchanged

## NEXT STEP
**Diagnose why WR note hallucination persists even after fix** — run seed=42 slant again and check if WR note now tracks steps correctly vs the move log. If WR is still overclaiming fake completion, the note mechanism isn't grounding it. May need to inject actual step count into the observation ("you have been on heading X° for N steps") rather than relying on the WR to count from its own note.
