---
description: End this session — write a clean handoff into left_off.md, then push to git
---
Summarize everything we did this session and update files:
1. Update `.claude/left_off.md`: date, what we worked on, what got done, what's broken/open, and a crisp single NEXT STEP.
2. Update `.claude/state.md` if the build state changed (phase, what's built, known issues).
3. Update `article.md` with any interesting problems we hit and lessons learned this session — add to the existing "Additions" or "Observations" sections as appropriate. Only include things that would be interesting to a reader: non-obvious failure modes, surprising model behaviors, scaffolding decisions and why, things that backfired. Skip routine fixes.
4. Keep it concise and concrete — no fluff. This is a handoff to a fresh context.
5. Stage all changes (`git add -A`), commit with a short message summarizing the session, and push to `origin main` (`git push origin main`).
