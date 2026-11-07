# AgentHive V2 — Live Demonstration Script (3–5 minutes)

## Objective & Narrative
Demonstrate how AgentHive V2 transforms ambiguous software engineering briefs into verified, Pony Tail compliant code through multi-agent collaboration over the Official Switch Protocol, backed by a human owner approval boundary and isolated container execution.

*Rule: Never approve or execute the historical acceptance project `4d633575-798c-4737-93c1-0dfbcd63db1b`. Always create a fresh disposable project.*

---

### Segment 1: The Multi-Agent Dilemma (0:00 – 0:40)
- **Speaker:** "When multiple AI agents work together, they easily hallucinate consensus, run wild on host systems, or work in isolated black boxes. AgentHive solves this with Discord command orchestration, Switch Protocol collaboration, strict human owner approval, and isolated non-root container sandboxing."
- **Visual:** Show MindHive Discord channel `#war-room` and the Live Dashboard at `http://127.0.0.1:8000/`. Show that Switch Core is ONLINE and agents are connected via SSE.

### Segment 2: Project Brief & Switch Room Creation (0:40 – 1:15)
- **Action:** In Discord, run `/newproject`:
  - `name`: `MicroRateLimiter`
  - `description`: `Token bucket and sliding window rate limiter in pure Python standard library with nanosecond timestamps.`
- **Evidence to highlight:**
  1. Instant project creation and `PROJECT.md` specification generated in workspace.
  2. Automatic creation of Switch collaboration room (`war-room-microratelimiter-...`) on Switch Core.
  3. Official Switch transport confirmed (no silent fallback).

### Segment 3: Truthful Parallel Analysis (1:15 – 1:50)
- **Action:** In Discord, run `/analyse project_id:<ID>`.
- **Evidence to highlight:**
  1. 4 independent proposals generated in parallel: ChatGPT Codex (Architecture), AGY (CLI Harness), Gemini (Adversarial QA), Hermes (Governance).
  2. Truth in runtime provenance: show that native CLI invocations record real process/session IDs, while fallback modes are transparently labeled.

### Segment 4: Official Switch Room Collaborative Debate (1:50 – 2:40)
- **Action:** In Discord, run `/discuss project_id:<ID>`.
- **Evidence to highlight:**
  1. Multi-turn architectural debate conducted live across Switch Core.
  2. Every single turn is delivered via Server-Sent Events (SSE) and stamped with both a Switch Event ID and a Switch Message ID.
  3. Show the Live Dashboard updating in real-time as Switch messages stream in.

### Segment 5: Discussion-Aware Planning & Approval Boundary (2:40 – 3:30)
- **Action:** In Discord, run `/assign project_id:<ID>`.
- **Evidence to highlight:**
  1. Hermes synthesizes a Work Breakdown Structure (WBS) directly citing the persisted Switch turn messages.
  2. Tasks are generated in `PENDING_APPROVAL` status with `human_approved=False`.
  3. **The Approval Gate:** Attempting to run `/report` now fails closed immediately with `PermissionError` — AgentHive strictly refuses to execute without human owner authorization.
  4. Non-owners cannot approve.
- **Action:** The project owner clicks **Approve Plan** or runs `/approve project_id:<ID>`.
- **Evidence to highlight:** The tasks transition to `APPROVED`, bound cryptographically by an immutable SHA-256 task hash.

### Segment 6: Isolated Non-Root Execution & Final Delivery (3:30 – 4:30)
- **Action:** In Discord, run `/report project_id:<ID>`.
- **Evidence to highlight:**
  1. Tasks are dispatched into the isolated non-root container (`--network=none`, `--read-only`, `--user=1001:1001`, `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`).
  2. Zero access to Docker socket or host credentials.
  3. Generated file inventory tracks created files before and after.
  4. Pony Tail Skill Audit verifies 100% Python standard library compliance.
  5. Adversarial tests execute and pass with exit code 0.
  6. Final state moves to `COMPLETED` and rich Discord embed displays complete evidence breakdown.
