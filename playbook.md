# Gridiron Minds — Route Playbook

Field coordinate system:
- x ∈ [0, 53.3 yd]: left sideline (x=0) to right sideline (x=53.3)
- y ∈ [0, 120 yd]: upfield = +y direction
- WR starts at (16.0, 50.0) — left hash, line of scrimmage
- QB starts at (26.65, 48.0) — center
- Heading degrees (clockwise from upfield): 0°=upfield, 90°=right, 180°=back to QB, 270°=left

---

## Existing Routes

### Slant
- **Stem**: run upfield (0°) for ~2.0s (~10 yards)
- **Cut**: sharp inside cut to 40° (diagonal upfield-right, toward middle)
- **Call for ball**: immediately after cut when open
- **Purpose**: short-to-intermediate crossing route over the middle
- **Deception**: jab left (toward outside) before the cut to sell an out route
- **Phase definition**: `[(2.0, 0°), (999, 40°)]`

### Post
- **Stem**: run upfield (0°) for ~2.5s (~12 yards)
- **Cut**: diagonal cut to 45° (upfield-right, toward goal post/center)
- **Call for ball**: immediately after cut when open
- **Purpose**: deep intermediate route toward middle/post
- **Deception**: jab outside before cutting inside
- **Phase definition**: `[(2.5, 0°), (999, 45°)]`

### Comeback
- **Stem**: run upfield (0°) for ~2.5s (~12 yards)
- **Cut**: hard 180° turn back toward QB
- **Call for ball**: immediately after cut (facing QB)
- **Purpose**: back-shoulder catch against tight coverage; works with off-coverage CB
- **Deception**: burst upfield to sell a go route, then plant and come back
- **Phase definition**: `[(2.5, 0°), (999, 180°)]`

### Out
- **Stem**: quick upfield burst (0°) for ~1.8s (~9 yards)
- **Cut**: cut to 315° (diagonal upfield-left, toward left sideline)
- **Call for ball**: immediately after cut
- **Purpose**: quick sideline route, gets out of bounds for clock management
- **Deception**: jab right/inside before cutting outside
- **Phase definition**: `[(1.8, 0°), (999, 315°)]`

---

## New Routes

### Go
- **Stem**: run straight upfield (0°) the ENTIRE play — no cut
- **Cut**: NONE
- **Call for ball**: any time WR has 2+ yards separation and is deep
- **Purpose**: vertical route to stretch the defense; creates separation through speed
- **Deception**: subtle speed variation (brake 1 step then burst), micro head fakes (±5-10° then back to 0°)
- **Key insight**: deception on a go is about rhythm breaks, NOT heading changes. The CB must respect the threat of a cut that never comes.
- **QB timing**: QB throws when WR calls; must lead WR deep (significant throw)
- **Phase definition**: `[(999, 0°)]`

### Double Move
- **Phase 1 (stem)**: run upfield (0°) for 1.5s (~7 yards)
- **Phase 2 (first move / fake)**: cut to 90° (right/inside) for 0.7s (~3 yards right)
- **Phase 3 (real break)**: cut back to 0° (upfield) at t=2.2s — THIS is when WR calls for ball
- **Call for ball**: in Phase 3 when open and running upfield again
- **Purpose**: get CB to commit to one direction with the fake, then exploit the vacated space going upfield
- **Deception**: Phase 2 IS the deception — it must look like a real in-route to freeze the CB. WR plants hard and sells the fake before cutting back.
- **QB timing**: QB MUST wait for Phase 3. Do not throw on the fake cut.
- **Phase definition**: `[(1.5, 0°), (2.2, 90°), (999, 0°)]`

### Curl
- **Stem**: run upfield (0°) for ~1.5s (~7 yards)
- **Cut**: sharp 180° curl back toward QB at t=1.5s
- **Call for ball**: same step as the cut — TIMING CRITICAL
- **Purpose**: create a window just in front of the WR's original depth; QB throws immediately
- **Deception**: explosive upfield stem to push CB back, then rapid direction reversal
- **Timing note**: Unlike comeback (which is a longer stem), the curl is designed for immediate throw. WR signals as the cut executes — QB must be ready to release fast.
- **Key difference from comeback**: shorter stem (~1.5s vs 2.5s), earlier timing, QB throws RIGHT AWAY on the call
- **Phase definition**: `[(1.5, 0°), (999, 180°)]`

### Zig
- **Phase 1**: run upfield (0°) for ~0.6s (~3 yards)
- **Phase 2**: quick jab left (270°) for ~0.3s (~1-2 yards)
- **Phase 3**: cut back right (90°) — this is the real break, call for ball here
- **Call for ball**: in Phase 3 when running right
- **Purpose**: quick-hitting route to create separation underneath; lateral quickness test
- **Deception**: the left jab should momentarily take the CB the wrong way before the rightward cut
- **QB timing**: very quick throw, WR opens up fast at short depth
- **Phase definition**: `[(0.6, 0°), (0.9, 270°), (999, 90°)]`

### Drag
- **Stem**: minimal upfield push (0°) for ~0.3s (~1.5 yards)
- **Cut**: immediate drag right (90°) — WR crosses the field horizontally
- **Call for ball**: immediately after cutting right when open
- **Purpose**: short horizontal route behind the LOS depth; stresses CB's hip-flip speed
- **Deception**: subtle upfield push before the horizontal break; sell it's a deeper route
- **QB timing**: very fast throw, ball must be on time — WR is crossing quickly and won't stop
- **Phase definition**: `[(0.3, 0°), (999, 90°)]`

### Corner
- **Stem**: deep upfield run (0°) for ~2.5s (~12+ yards)
- **Cut**: diagonal cut to 315° (upfield-left, toward back corner of end zone)
- **Call for ball**: immediately after cut
- **Purpose**: attack the corner of the end zone or create deep separation on the outside
- **Deception**: run the stem hard like a go route or post to freeze the CB, then break outside
- **Key difference from out**: deeper stem (~2.5s vs 1.8s), attacks the end zone corner
- **QB timing**: throw to the back-left corner, significant distance — must lead WR to corner
- **Phase definition**: `[(2.5, 0°), (999, 315°)]`

### Post-Corner
- **Phase 1 (stem)**: run upfield (0°) for 2.0s (~10 yards)
- **Phase 2 (post fake)**: cut inside to 45° (upfield-right, like a post) for 0.4s (~2 yards)
- **Phase 3 (corner cut / real break)**: flip to 315° (upfield-left, corner direction) at t=2.4s
- **Call for ball**: in Phase 3, running to the back corner
- **Purpose**: premium route that beats all coverage — the post fake gets CB to commit inside, then WR goes outside to the corner
- **Deception**: Phase 2 must be convincing — sell the post before breaking out. This is the highest deception double move.
- **QB timing**: must wait for Phase 3 (corner direction). A throw on the post fake will be wrong.
- **Phase definition**: `[(2.0, 0°), (2.4, 45°), (999, 315°)]`

### In
- **Stem**: upfield run (0°) for ~1.8s (~9 yards)
- **Cut**: sharp 90° cut to the right (toward middle of field)
- **Call for ball**: immediately after cut when open
- **Purpose**: harder version of the slant — 90° cut is more angular, opens up a bigger window
- **Deception**: jab outside (toward left) before breaking inside at 90°
- **Key difference from slant**: cut is 90° (pure horizontal) vs 40° (diagonal); sharper and at same depth
- **QB timing**: throw across the middle, WR running perpendicular to the field
- **Phase definition**: `[(1.8, 0°), (999, 90°)]`

---

## Route Summary Table

| Route       | Stem time | Stem depth | Cut direction | Final heading | Call timing      | Cuts |
|-------------|-----------|------------|---------------|---------------|------------------|------|
| slant       | 2.0s      | ~10 yd     | inside diag   | 40°           | after cut        | 1    |
| post        | 2.5s      | ~12 yd     | inside diag   | 45°           | after cut        | 1    |
| comeback    | 2.5s      | ~12 yd     | back to QB    | 180°          | after cut        | 1    |
| out         | 1.8s      | ~9 yd      | outside diag  | 315°          | after cut        | 1    |
| **go**      | full play | —          | none          | 0°            | when open        | 0    |
| **double_move** | 1.5s  | ~7 yd      | fake right → back up | 0°   | after 2nd cut    | 2    |
| **curl**    | 1.5s      | ~7 yd      | back to QB    | 180°          | same step as cut | 1    |
| **zig**     | 0.6s      | ~3 yd      | left jab → cut right | 90°  | after 2nd cut    | 2    |
| **drag**    | 0.3s      | ~1.5 yd    | horizontal right | 90°        | after cut        | 1    |
| **corner**  | 2.5s      | ~12 yd     | outside corner | 315°         | after cut        | 1    |
| **post_corner** | 2.0s  | ~10 yd     | post fake → corner | 315°    | after 2nd cut    | 2    |
| **in**      | 1.8s      | ~9 yd      | sharp inside  | 90°           | after cut        | 1    |
