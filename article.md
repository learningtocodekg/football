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

**Pending-cut problem: pass 2 projections are wrong before the cut fires**
The two-pass system showed "MISS by 11yd" for every option while the route was developing — correct behavior. But the model would sometimes commit anyway at t=1.6s on a slant where the cut fires at t=2.0s. The pass 2 options use current WR heading/speed to project position at arrival. Pre-cut, those projections point the WR running straight upfield forever — so the landing spot is never near the projected WR. The model sees "MISS" and should hold, but occasionally reasons "the WR will be near there *after* the cut" and commits early. The fix is to make the pending-cut warning stronger in the pass 2 prompt: if a cut is imminent, the projections are explicitly labeled unreliable.

**CB agent: the model chose the wrong backpedal direction**
First run of the CB agent, the CB sprinted 22 yards the wrong way. The observation told the model "backpedaling means heading ~180°" and included an example — so when the CB was already *upfield* of the WR (between WR and end zone, which is the correct position), it read "backpedal = 180°" and ran *downfield through the WR* and kept going toward the QB. The CB went from 5 yd separation to 22 yd separation in 2.3 seconds. The fix wasn't physics — it was observation scaffolding. We replaced the abstract heading-vs-facing explanation with a **SITUATION block** that pre-computes the specific situation and emits a RECOMMENDED action with exact numbers: "WR is 4.2 yd downfield of you — backpedal upfield, heading ≈ 0°, facing ≈ 180°." The model follows prescriptions much more reliably than deriving the correct heading from a description of the coordinate system.

**CB agent: the model kept backpedaling after the WR blew past it**
Even after fixing direction, the CB would correctly backpedal while the WR approached, but then continue backpedaling *away* once the WR passed it. The situation flipped from "WR approaching" to "WR running away" but the model just kept doing the same thing. The SITUATION block needed to encode the phase transition explicitly: three named states — "WR approaching (backpedal)", "WR just passed (close gap)", "WR beaten by 2+ yd (CHASE)" — each with its own RECOMMENDED action and unambiguous instruction to flip hips and sprint. Without naming the phase change, the model doesn't detect it.

**ScriptedQB lead throw: naive projection vs. route simulation**
The first implementation of `ScriptedQB` used linear projection: take WR's current heading and speed, multiply by flight time, throw there. This broke badly the moment the WR was mid-cut — the WR's heading had just flipped to 40° and speed had shed from the cut, so the projection pointed way off field. The correct approach is obvious in retrospect: the WR's route is *fully deterministic* — we have `ScriptedWR.move()` and know the exact physics. The fix was to step the WR forward along its route using the same `move()` call the game loop uses, for exactly `eta` seconds. This is always accurate regardless of route phase. The lesson: when you have a scripted/deterministic system, simulate it — don't approximate it.

**Fuzzy landing zone: modeling human vision**
When the ball is in the air, a real DB doesn't know the exact landing spot immediately — they read trajectory and narrow in. We modeled this as ±4 yd uncertainty at release, tightening linearly to ±0.25 yd at arrival. The CB observation shows this shrinking zone each step. In practice the model latches onto the zone center from the first step anyway (treats it as point knowledge), so the fuzz is currently cosmetic. But it sets up future behavior where the CB must commit a direction before knowing the exact spot — which is the interesting decision.

**CB comeback route: the SITUATION block had a missing state**
The CB observation pre-computes a SITUATION block with a RECOMMENDED action. Originally three states, all keyed on `dy` (who is upfield of whom). On a slant or go route this works fine: CB backpedals while WR approaches, flips hips when WR passes. On a comeback, the WR runs upfield past the CB, then reverses to 180° and runs back toward the QB. After the cut, `dy` goes negative — CB is upfield of WR — and the old code emitted "you are between WR and end zone ✓ → backpedal." The CB dutifully backpedaled further upfield while the WR ran away in the opposite direction. Separation hit 14.17 yd at the catch. The fix was a fourth state: check `wr.heading` — if it's in 135–225° (running toward QB) AND CB is upfield, emit "WR has cut BACK toward QB — flip hips and CHASE downfield. Do NOT backpedal." After the fix: 0.1 yd separation, DROP. The lesson: the SITUATION block encodes field geometry logic that the LLM should not be trusted to derive. Every route type that can flip the positional relationship needs its own named state.

**Stateless calls mean the LLM can't detect phase transitions across steps**
Each timestep is a fresh two-message LLM call. The model has no memory of its previous reasoning or what it decided last step. It only sees the current observation plus a WR history table (last 10 steps of positions/headings embedded as text). This means phase transitions — "WR just cut, switch from backpedal to chase" — must be detected and expressed in the observation scaffolding, not left to the model to infer from the history. The history table contains the signal (heading changes), but the model won't reliably act on it without the SITUATION block calling it out explicitly with a named state and a RECOMMENDED action. Scaffolding is doing the perception work; the LLM is just executing the named response.

**Intent-aware facing during ball-in-air movement**
Once the ball is in the air the CB locks an intent (swat, go_for_pick, play_man). Early versions told the CB to always face the landing zone when the ball was in the air — correct for swat/INT, but wrong for play_man, where the CB should face the receiver (no facing requirement for play_man in resolution). The fix was to pass the locked intent into the movement observation and emit a FACING line that varies by intent: swat/INT → face the zone, play_man → face the WR and head toward the zone. This also captures the real football logic: a CB playing the receiver on a comeback should be in the receiver's face at the catch, not turning to look at the ball.

**WR agent: the model cut to the route heading immediately (1.8s early)**
The system prompt said "the cut time is a strict guideline (±0.2s)" but the live prompt said "if CB is giving cushion, consider cutting early to exploit it." The model resolved the contradiction the greedy way: it jumped to heading 40° at t=0.2 on a slant with cut_time=2.0. The route was telegraphed 1.8 seconds early. Fix: remove the early-cut escape hatch entirely, and replace it with phase-explicit instructions. The observation now shows which phase the WR is in with a hard directive ("KEEP HEADING NEAR 0°. Do NOT move to 40° yet"). Contradictions in the prompt are resolved by the model, not the prompt — always in the direction of least resistance.

**WR deception: "jab step" meant nothing without a mechanical definition**
The initial system prompt described deception as "false steps, speed changes, body fakes." The model's output: reasonable-sounding reasoning ("jabbing inside before the slant cut") with heading=40° every single step. It understood the concept but had no way to express it — there are no animations in a 2D simulation. A jab step IS a heading change. Fixing this required explaining exactly how the CB tracks the WR: it reads heading and speed, projects forward 0.5s, and moves to that point. Once the model understood this, it immediately started outputting heading=330° for one step then snapping back to 0° — correct behavior. The lesson: tell the model what the CB *computes*, not what football moves look like.

**WR deception: model understood "jab" but executed it for 20 steps**
After adding the mechanical definition, the model correctly jabbed left (330°) — but held that heading for the entire pre-cut phase (2 seconds). A jab that lasts 2 seconds is just running the wrong direction. The word "jab" implies brevity; the model interpreted it as a technique to apply, not a 1-step move to execute and release. Fix: show the exact step-by-step pattern explicitly ("step N: 330°, step N+1: 0°, step N+2: 0°, step N+3: jab again"). Also show the *wrong* pattern ("330°, 330°, 330° — this is NOT a jab, this is running left"). Making the failure mode explicit was as important as making the correct pattern explicit.

**call_t race condition: state mutation order matters**
The WR `decide()` call returned `call_for_ball: true` and the runner set `wr_agent.call_t = t` after the call returned. The *next* step's observation then read `wr_agent.call_t` to format "COMMITTED: called at t=X.Xs" — but `call_t` was still None because `decide()` hadn't been called yet for the new step. Fix: move `self.call_t = t` inside `decide()` at the moment of call validation, before returning. Observation reads state that was set during the *previous* decide() call — the runner setting state after the fact is always one step behind.

---

## Observations

- The model's biggest failure mode is spatial: it has no grounded sense of where players are relative to each other or how fast they move across the field. Every scaffold addition was essentially providing that grounding.
- Pre-computing things "to help" often backfired (projected separation, min hold time from scenario YAML) because the model would anchor on the pre-computed number instead of reading the actual situation.
- The two-pass system revealed that the model's intent and its commitment were disconnected — it would say "I want to throw here" and then pick an option that physically couldn't reach the receiver.
- Travel time was a consistent blind spot. The model understood the concept when told, but couldn't apply it correctly without seeing explicit "WR will be at X when ball arrives" numbers.
- The two-pass system partially solved premature throws but introduced a subtler failure: the model reasons about *future* WR state (post-cut) while the projections show *current* heading extrapolated forward. It's doing the right qualitative reasoning ("WR will be open after cut") but committing before the cut validates that. The scaffold showed MISS correctly; the model overrode it with narrative reasoning.
- Tooling footgun (Ollama): `response_format={"type": "json_object"}` causes qwen3:8b via Ollama's OpenAI-compat API to return empty `content`. The thinking goes to `model_extra["reasoning"]` and the answer never makes it to `content`. Removing the format constraint and falling back to the reasoning field fixes it — but the symptom (silent empty string) is a bad failure mode that looked like a hang.
- qwen3:8b without `json_object` constraint: 73% parse error rate (16/22 calls) — model outputs prose essays in `content` instead of JSON. The rare successful calls were correct (held until t=2.2s post-cut, CATCH outcome), but the model isn't reliable enough for local use without a better JSON-forcing mechanism. Prompt engineering or a smaller/faster instruct model would help more than further API tweaks.

**Cut detection: a threshold gate isn't enough when the LLM jabs at the threshold**
The first cut-detection fix raised the gate to `t >= 0.5` to skip early jabs. In the next run, the WR jabbed at exactly t=0.5 — every route, every run. The model hadn't "learned" to time its jab to defeat the gate; it just always jabs early, and 0.5s is inside the early-jab window. A fixed time gate becomes fragile the moment the model has a consistent habit. The real fix is structural: require heading persistence (2+ consecutive steps) with a snap-back test. A jab by definition returns to 0° within one step; a real cut holds. The detector now uses a two-step candidate system — a heading change creates a candidate, which is either confirmed (held) or discarded (snapped back) on the next step.

**Richer deception coaching did not break the template habit**
After adding detailed deception coaching — hold fakes, speed fakes, double fakes, explicit anti-repetition rules — the WR still jabbed 330°/30° on every single route across all 10 runs. The habit appears to be at training-data depth, not context depth. Prompt instructions to "vary your fakes" or "don't use the same angle twice" are not strong enough to override a deeply baked pattern. What hasn't been tried: showing the WR its own action history so it can observe the repetition in context, or an explicit per-step callout ("you have jabbed 330° four times this play — the CB has read it"). The second is likely stronger because it makes the failure concrete and present rather than abstract and future.

**When the LLM misreads a heading, the error is systematic**
On the comeback route, the QB consistently threw upfield when the WR was running downfield (heading 180°). The LEAD HINT used angle notation that the model conflated with "running far upfield." The model doesn't compute in coordinate space; it maps angles to football concepts. Heading=180° plus a projected y higher than current produced a throw upfield — the model reasoned "comeback" ≈ "throw short to the sideline" without processing that y=63.7 is upfield of the WR's actual position at y=62.4. The fix was explicit English: "y is DECREASING toward QB." This bypasses the model's angle-to-direction inference entirely. Whenever an angle is semantically ambiguous in football terms (180° means "downfield" in coordinate space but "back toward QB" in football vocabulary), add a prose disambiguation — don't trust the model to derive it.

**The constraint "we guide, not enforce" determines which problems are fixable**
Several Round 2 problems (WR exits fake phase early, QB throws a lob on a short horizontal route, WR drifts sideways during ball-in-air) could each be fixed with a code-level rule. But the experiment is designed to measure LLM spatial decision-making. If we add a floor on fake phase duration, a speed requirement for horizontal routes, or a heading lock during ball-in-air, we're no longer measuring the LLM — we're measuring our own rules. These problems are left open as data: the model made a bad football decision, and that's what we're measuring. This constraint filters every observation and prompt change: the question is always "does this give the agent better information?" not "does this guarantee a better outcome?"
