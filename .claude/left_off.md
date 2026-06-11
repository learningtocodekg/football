# Left Off
Date: 2026-06-11

## What We Worked On
QB autonomy / independence. User's directive: the QB should make its OWN throw decision — able to throw BEFORE the WR calls (if it predicts the window opening) and able to HOLD after the WR calls (if coverage is tight). It currently had no independence; it just waited for the WR call as a trigger.

Mid-session the user reframed the approach: stop having the system DECLARE "cut confirmed / open." Instead teach the QB that **a throw is a prediction** — "open" = (1) WR direction confirmed by route design + real heading history, AND (2) separation predicted by projecting BOTH the WR and CB forward to ball-arrival.

(Note: another chat had branched to `realism` and committed most of the QB route-read scaffolding into shared history `a64143a` — route param, `_ROUTE_GEOMETRY`, lead-hint call-heading fix, the DIRECTION CHECK block. My session's net-new uncommitted work was the prediction-doctrine wording + the straight-route fix.)

## What Got Done

### Curl throw accuracy — FIXED (now CATCH)
Root cause: the QB LEAD HINT projected the WR off its **physical** heading. When the WR calls mid-cut (physical heading 270°) but its **locked call heading** is 180°, the projection pointed 5+ yd to the side → QB threw to empty grass. Fix (committed in shared history): project off `wr_call_heading` once the WR has called. Result: curl_42 = **CATCH, throw_t=2.7s, sep=5.02** (was INCOMPLETE/PBU for many rounds).

### QB prediction doctrine (qb_system.txt + observation.py)
Replaced the prescriptive "WHEN YOU CAN THROW — NOT A GATE" section with **"WHAT 'OPEN' MEANS — A THROW IS A PREDICTION"**: two-layer model (route design = expectation/prior; real position+heading+velocity history = confirmation), and "window is real" only when direction is confirmed AND separation is predicted at arrival. The observation's DIRECTION CHECK now reports facts (is the WR's heading on the route's break yet?) and hands the openness *prediction* to the QB, instead of issuing "DO NOT throw" / "you MAY throw" commands.

### Go-route SACK — straight-route fix applied, NOT yet tested
After the reframe, go_42 = **SACK** with max_sep=**6.62 yd** — the QB had a huge window and never threw. Cause: the DIRECTION CHECK logic gated on `expected_open_t < 9.0` and a route break; a go route has no break (`route_phases=[(999,0.0)]`, `expected_open_t=None`), so it fell into "direction not confirmed — wait for the break" and the QB waited forever. Fix: added a `straight_route` branch — when every route phase heads upfield, direction is confirmed from the snap and openness is "has the WR overtaken the CB with separation that holds." Committed to main but **the go re-run was killed before completing — fix is unverified.**

## What's Open / Known Issues
1. **Go straight-route fix is UNTESTED** — committed as "untested QB autonomity changes" (`03df8cd` on main). Re-run go_42 to confirm the QB now throws on the footrace instead of taking a sack.
2. **Full 10-route suite not run** with the QB prediction doctrine. Only curl (CATCH) + go (SACK, pre-fix) were checked.
3. **`realism` branch**: user intends to delete it. All my QB work is on `main`; nothing of value is realism-only. The WR-side realism changes (wr_agent.py, wr_live_free.txt, schema.py) remain UNCOMMITTED on realism — not my work, deliberately left alone.

## NEXT STEP
Re-run `python run_all_routes.py --routes go --seed 42` and confirm the straight-route fix makes the QB throw on the footrace (CATCH/contested) instead of SACK. If good, run the full suite and compare to the R14 baseline (8C/2INC).
