# LLM QB Agent — What We Had to Add (and Why)

Notes for article. Tracks every scaffold addition made to get the model to behave like a real QB.

---

## Base Setup

- QB is an LLM (gpt-4o-mini / gpt-5-nano) called every 0.1s timestep
- Receives: current positions, speeds, headings of WR and CB, current separation, movement history
- Outputs: `hold` or `throw` with target coordinates and ball speed in mph
- WR runs a scripted route. CB plays scripted man coverage.
- No minimum hold time — QB was free to throw from snap

---

## Additions

**Hardcoded minimum hold time (0.5s)**
The QB was calling throw at t=0.0 before the WR had moved a single step — there was no history to reason from. Added a hard 0.5s gate before the LLM is even consulted. Without this, the model had no signal at all and just threw immediately.

**Route schedule in observation (cut time + heading + estimated cut position)**
The QB had no idea when or where the WR would cut. It was hallucinating target coordinates wildly — throwing to (36, 90) on a slant where the WR starts at x=16 and never gets past x=24. Added a per-timestep route schedule showing each cut's time, direction, and estimated WR position at cut time based on current speed/heading. Grounded the model's spatial reasoning significantly.

**Heading labels (plain English directions)**
The model was treating heading angles as raw numbers with no feel for field geometry. "Cut to 40°" meant nothing — it would interpret it as a huge rightward move. Added plain English labels: "diagonal upfield-right (toward right sideline)", "straight back toward QB", etc. alongside every angle.

**Removed projected throw options (pre-computed separation at arrival)**
The original observation pre-computed WR and CB positions for 5 time horizons and showed separation at arrival. This was meant to help but it backfired — the model saw "3.2 yd separation, feasible" and just threw without reasoning about whether the route had actually developed. Removing it forced the model to do its own reasoning from raw history.

**Ball travel time reference (bullet / regular / lob)**
The model had no concept of how long a throw takes to arrive. It would target a spot 1.3 seconds away and throw a "bullet" that arrived in 0.27s — completely mistimed. Added a per-timestep line showing actual flight time to the WR's current position at three speed tiers (bullet = max mph, regular = mid, lob = min). The model could now at least understand the magnitude of travel time.

**Two-pass decision system**
Single-shot decisions let the model commit to a throw without checking whether the WR would actually be at the landing spot. Added pass 1 (read the field — where do you think you want to throw?) and pass 2 (here are the concrete options at that target — will the WR actually be there?). Separates intent from commitment.

**WR projected position at arrival shown in pass 2 options**
Even with two passes, the model was targeting a future WR waypoint (e.g. "where WR will be at cut time") and treating it as a valid throw target right now. In pass 2, added a column showing where the WR will actually be at ball arrival for each speed option, plus whether it's catchable or a miss. The model now sees "MISS by 11.7yd" for every option when the route hasn't developed yet, and holds correctly.

**CB lockup duration (2 seconds before reaction delay kicks in)**
In replays the CB was giving up 4+ yards of separation within the first second. The CB was chasing a delayed WR signal from frame 0, so as the WR accelerated upfield the CB fell behind immediately. Added a 2-second lockup phase where the CB mirrors the WR's current position directly before the reaction delay engages. Now the CB stays tight for a realistic duration before the cut creates separation.

**PBU requires proximity (1 yard) or CB in passing lane**
A PBU was firing at 5.91 yards of separation — completely unrealistic. A cornerback 6 yards away cannot break up a pass. Changed resolution logic so a PBU is only possible if the CB is within 1 yard of the WR at arrival, or is physically in the passing lane (within 1.5 yards of the line between the landing spot and the WR).

---

## Observations

- The model's biggest failure mode is spatial: it has no grounded sense of where players are relative to each other or how fast they move across the field. Every scaffold addition was essentially providing that grounding.
- Pre-computing things "to help" often backfired (projected separation, min hold time from scenario YAML) because the model would anchor on the pre-computed number instead of reading the actual situation.
- The two-pass system revealed that the model's intent and its commitment were disconnected — it would say "I want to throw here" and then pick an option that physically couldn't reach the receiver.
- Travel time was a consistent blind spot. The model understood the concept when told, but couldn't apply it correctly without seeing explicit "WR will be at X when ball arrives" numbers.
