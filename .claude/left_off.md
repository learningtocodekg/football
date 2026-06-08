# Left Off
Date: 2026-06-07

## What We Worked On
Fundamental physics overhaul: acceleration was flat/static, which made every move physically wrong. A WR at rest and a WR at 7 yd/s both gained the same speed each step. There was no consequence to making a hard cut — no speed shed, no recovery time. Separation mechanics were therefore completely fake.

## What Got Done

### 1. Physics engine rewrite (`engine/physics.py`)
- `PlayerState` gets a new field: `cut_recovery: int = 0` (steps remaining in hip-turn recovery)
- **Dynamic burst**: `accel = peak_accel * headroom`, where `headroom = (max_speed - current_speed) / max_speed`. Explosive from rest, tapers to near-zero at top speed.
- **Cut recovery**: any turn >35° at speed >3 yd/s commits hips. Triggers `cut_recovery` steps of reduced burst, scaling with turn angle, speed, and agility. A 90° cut at 7 yd/s (agility=70) = 4 steps (~0.4s) of ~25% burst capacity.
- **Speed shed retuned**: agility=50 loses ~80% speed on 90° cut (not the old 95% linear formula — the recovery mechanic does the real punishing).
- Braking clears recovery instantly (you planted your feet).
- `cut_recovery_steps()` exposed as a standalone helper.
- All existing callsites (`ScriptedWR`, `runner.py` initial states) use keyword args, so the new default `cut_recovery=0` is backward-compatible.

### 2. `cut_recovery` in all observations (`agents/observation.py`)
- New helper `_accel_status(cut_recovery)` → human-readable burst string ("FULL burst available" / "RECOVERING — 3 steps left, burst ~43%")
- **WR observation**: shows `YOUR BURST` and `CB BURST` lines; explicit "!! CB HIP-TURNED — X steps left. THIS IS YOUR WINDOW" alert when CB.cut_recovery >= 2
- **CB observation**: shows `YOUR BURST` and `WR BURST`; "!! WR HIP-TURNED — CLOSE NOW" alert when WR.cut_recovery >= 2
- **QB observation**: shows `WR BURST` and `CB BURST`; alerts when CB is recovering ("sep likely to GROW") or WR is recovering ("sep may SHRINK")
- **Move history** (all three agents) extended with `WR rec` and `CB rec` columns — agents can see the full recovery timeline per step

### 3. Runner (`sim/runner.py`)
- `move_history` entries now track `wr_cut_rec` and `cb_cut_rec` and `cb_spd` per step

### 4. WR prompts rewritten
- `wr_system.txt`: full physics section explaining burst, cut recovery, speed shed. Three deception patterns: THE SELL (hip commit fake), THE SPEED FAKE, THE STUTTER STEP. Each explained mechanically in terms of `rec` columns.
- `wr_live_free.txt`: step-by-step framework: check burst status → check rec log → decide action (sell/snap/speed fake/stutter). Explicit: snap only when CB heading committed AND CB rec > 0.

### 5. CB prompts rewritten
- `cb_system.txt`: full physics section. "Your job is to NOT get your hips turned." DO NOT OVER-COMMIT section, ZONE-OF-CONTROL approach, explicit "when beaten" recovery guide. Read the history rec column.
- `cb_pass1.txt`: step-by-step framework: read burst status → read rec log → decide (mirror/close/hold). PATIENCE RULE: wait 2 steps before matching a WR heading change — one-step jabs are almost always fakes.

### 6. QB system prompt rewritten
- `qb_system.txt`: full section on burst/recovery reading. Four concrete scenarios with math for estimating separation at catch time using recovery steps + ball ETA (Scenario A: CB recovering → throw; B: WR recovering → hold; C: both free, WR ahead → safe; D: CB recovering, 0 sep → throw into the expected gap).

## What's Open / Known Issues
- No run done yet with new physics — everything passing smoke tests but untested end-to-end
- Speed shed formula changed (80% vs old 95%): may need tuning based on how hard cuts look in replays
- `CUT_RECOVERY_BASE_STEPS = 4` is a guess — could be too high or too low
- CB backpedal + cut_recovery interaction untested: does the CB stutter unnecessarily in backpedal?
- Prior open issues (WR pre-cut calls, WR note hallucination, detected_cut_t misfiring) unchanged

## NEXT STEP
**Run all 10 routes** and read replays to see if:
1. Hard cuts now visibly cost speed in the replay (speed should drop on cut steps)
2. `cut_recovery` in the move log shows when the window opened
3. WR and CB agents actually reference the rec column in their reasoning
4. Separation dynamics look more realistic — WR can gain real ground off a good fake

Run: `.venv\Scripts\python run_all_routes.py`
Then check: `replays/` — look at the move log in any replay JSON, confirm `wr_cut_rec`/`cb_cut_rec` non-zero after hard turns.
