# Left Off
Date: 2026-06-09 (second session today — post-3D-transformation polish)

## What We Worked On
First live 3D route test, replay viewer fixes (debug viewer 3D crash + Ursina viewer visual overhaul), README replay-viewing docs, replays/ cleanup.

## What Got Done

### First 3D slant (GPT-5-nano, seed 42) → CATCH
- `python run_all_routes.py --seed 42 --routes slant` → **CATCH, sep=3.94 yd**, 0 parse errors (73 LLM calls).
- QB picked **bullet** this time ("bullet arc minimizes CB time to close") — the smoke test's loft choice did NOT replicate on an identical run. Single-run conclusions are provisional; model variance is real.
- WR ball-in-air was excellent: per-step ETA arithmetic, accelerate/coast to hit the landing spot without overshoot. This DID replicate from the smoke test.
- CB flip-flopped cut detection during the 1.2s flight ("real cut to 45°" ↔ "still in stem, no cut") — heading whipsawed, 3 self-induced cut recoveries, never contested. New 3D-era CB failure mode: stateless re-derivation of the cut every step. Note: runner already computes `detected_cut_t`; CB observation doesn't expose it.
- Quirk: one QB pass2 reasoning came out in Chinese (parsed fine).

### Viewers
- **viewer/debug_viewer.py crashed on 3D replays** (`ValueError` unpacking 3-elem ball pos) — fixed; now draws ground shadow + height-offset ball + z label. Headless-verified on both 3D and legacy 2D replays.
- **render/renderer_ursina.py was visually broken** (white void, field as horizon sliver, no players). Root causes: ursina 8.x `color.rgb()` takes 0–1 floats (all colors clamped to white) → switched to `color.rgb32()`; `camera.look_at()` silently no-ops → explicit pitch rotation, camera anchored behind QB's snap position from the replay; player labels distorted by parent cube scale → unscaled holder entities; non-ASCII reasoning caused glyph spam → ASCII sanitize; debug counters disabled. **User confirmed it works visually now.**

### Housekeeping
- README: new "View replays" section — view one route (`python -m viewer.debug_viewer replays/slant_42.json`), browse all with header-click dropdown (`python -m viewer.debug_viewer`), pygame side-view + ursina 3D commands. Sections renumbered.
- replays/ cleaned: deleted 10 junk JSONs (a4_* old naming, demo, play_42, test_*). Remaining: exactly the 10 route files + run11_log.txt.
- **NOTE: 9 of the 10 route replays are stale 2D runs** (flat ball, no arc) from before the 3D commit — only slant_42.json is 3D. Round 14 will overwrite them.

## What's Open / Known Issues
1. **Round 14 (full 10-route 3D suite) still not run** — only slant, which was a CATCH. User wants to go route-by-route / start small rather than all 10 at once.
2. CB cut-detection flip-flop during long flights (see above) — likely the first 3D-era prompt/observation target. Freedom philosophy: consider exposing already-computed facts (detected_cut_t) in the observation rather than rules.
3. Jump action (WR/CB vertical timing) deliberately deferred.
4. gen_demo.py still emits legacy ball_speed_mph format.
5. Carried from 2D: cb_pre_snap 5yd hardcode, bearing-vs-heading 1-step confusion, post_corner Window A.

## NEXT STEP
Continue Round 14 route-by-route with GPT-5-nano: `python run_all_routes.py --seed 42 --routes <route>` (e.g. go or corner next to stress arc range/choice on deep routes). Read QB arc choice + target_z reasoning, CB flight-phase behavior, lane-contest events. After a few singles look sane, run the full 10.
