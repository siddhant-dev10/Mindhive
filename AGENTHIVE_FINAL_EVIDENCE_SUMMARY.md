# AgentHive V2 — Final Evidence Summary

## Latest worktree evidence — 2026-11-07

**Current verdict: NOT READY.** The updated source has not been deployed to the running backend. A read-only post-run snapshot shows the existing acceptance project is still `AWAITING_APPROVAL`, with four ordered discussion messages and their original Switch event/message IDs, three pending tasks, zero approvals, zero execution logs, and only `PROJECT.md` in the workspace. See `FINAL_RELEASE_REPORT.md` for current code changes, isolated tests, live-state limits, and release blockers. Earlier live Discord/Switch evidence below remains historical and does not prove this updated build is running.


**Verdict: NOT READY**

## Previous live acceptance evidence (before resume) — November 7, 2026

Priority 1's actual protocol defect is fixed and verified against the live Official Switch service. `run_switch_discussion()` now creates a shared room, subscribes participants, sends each turn through Official Switch, waits for other agents' SSE deliveries, persists distinct Switch message IDs and SSE event IDs, and reconnects using event cursors. The API uses the moderation room `id` for subsequent room operations; using `transport_room_id` had caused 404 errors. Five targeted live integration/health tests passed; bidirectional Codex↔AGY delivery and a four-agent room exchange were verified. No live Discord discussion command was completed after this fix.

The running backend (PID 75618) reports: Discord online in MindHive with 9 guild commands; Official Switch online with 4 registered and 4 SSE-connected agents; Docker online. Health is `degraded`: Gemini is local fallback because `GEMINI_API_KEY` is absent, and Hermes is in standalone governance mode because no daemon/binary is available. The dashboard uses backend status and persisted project records; visible Switch rooms are not mislabeled as active rooms.

AGY headless execution is corrected: actual scoped CLI write verification succeeded using `--sandbox`, `proceed-in-sandbox`, workspace-specific `write_file(...)`, and `.git`/`.env` denies, without dangerous bypass flags or broad command permission. Codex execution now has bounded timeouts, cancellation, process monitoring, partial output/session evidence and retries limited to read-only work. Fake CLI probes verified timeout retry and cancellation evidence; no end-to-end approved task has validated the complete native execution chain.

The command-picker root cause was the computer interaction layer: Discord had synchronized nine guild-scoped commands and its picker displayed commands in `#commands`; stale accessibility indices and a malformed draft caused earlier input failures. Actual `/newproject` and `/analyse` interactions succeeded for fresh project `4d633575-798c-4737-93c1-0dfbcd63db1b` (`AgentHive Switch Acceptance 2026-11-07`). `PROJECT.md`, its workspace and Discord war-room thread exist. Four independent-analysis rows and the Discord response are verified, but the rows have no native runtime/session metadata, so they do not prove four external agent executions. The project is still `ANALYZING`; it has zero Switch discussion messages and zero tasks. The desktop UI later stopped accepting computer input (`noWindowsAvailable`); `/discuss`, `/assign`, owner approval, execution, generated-project tests and `/report` were not performed for this project. The literal messages `/analyse/`, `/discussdiscuss` and an earlier `/newproject` were plain text, not application commands. No approval was granted by this agent.

Targeted verification: `./venv/bin/python -m compileall -q agenthive tests`, `git diff --check`, and targeted Official Switch/runtime tests succeeded earlier (**5 passed, 16 deselected**). The complete current suite was run with `./venv/bin/python -m pytest -q`: exit code 1, **43 passed, 3 failed, 0 skipped in 632.11s**, with two FastAPI deprecation warnings. All three failures came from dispatcher tests calling `/discuss` without running FastAPI startup, so the four Official Switch clients were not connected in that process; the production backend reported all four connected. A test-only async fixture now opens and closes Official Switch sessions for the three affected discussion tests. Rerun of exactly those failed tests exited 0: **3 passed in 355.70s**. The full suite was not rerun after the fixture change, so no green full-suite result is claimed.

The pre-existing AGY process remains untouched: PID `53932`, parent `52272`, user `sidh._.`, TTY `ttys000`, working directory `/Users/sidh._./mindhive`, command `agy --dangerously-skip-permissions`. Do not treat it as a process started or authorized by this remediation.

Discord IDs: Application/Bot `1568557236626792498`; Guild `1567933462575325375`; `#general` `1567933463120842765`; owner `1027116327997034496`. Invite permissions integer `309237763072`. No bot token or API secret was accessed, displayed, or added to reports.

Remaining acceptance blockers: complete `/discuss` and `/assign` for the fresh Discord project through the actual client, then stop for owner approval; verify approved execution and project tests/report; configure genuine Gemini API access and a live Hermes daemon if those external runtimes are required. See the detailed reports below and [MINDHIVE_OPERATIONS_GUIDE.md](MINDHIVE_OPERATIONS_GUIDE.md).

The sections below are retained historical evidence. Where they conflict with this latest remediation section, this latest section controls.

## Live acceptance resume — 2026-11-07

### Existing project preserved

Continued the existing project `AgentHive Switch Acceptance 2026-11-07` (`4d633575-798c-4737-93c1-0dfbcd63db1b`). No project was recreated and the four existing analysis records were not overwritten. Database inspection confirms the four records are Codex, AGY, Gemini, and Hermes. They contain analysis text, but `raw_payload` is NULL for all four, so the analysis rows do not preserve native runtime session IDs or independent execution evidence.

### Actual Discord /discuss interaction

Invoked the registered `/discuss` command for this project through the Discord application command picker. Discord returned a successful AgentHive embed stating that the collaborative debate concluded in four bounded turns. The initial invocation before the backend restart returned Discord's explicit `Failed to create official room: Invalid credentials` error; it is not counted as a successful discussion.

The successful discussion created Official Switch room `c52deec5-df2e-46c0-9461-eebe885fb5c1`. The database now contains four ordered discussion messages, each with both a Switch event ID and message ID:

| Turn | Participant | Switch event ID | Switch message ID |
|---|---|---:|---|
| 1 | ChatGPT Codex | `9007194959773920` | `sw_6871010e5fd847db8ec6eacef9ea25f8` |
| 2 | AGY (Antigravity) | `9007194959773924` | `sw_2b68d61343244b83b8ab25219f9bfcee` |
| 3 | Google Gemini | `9007194959773926` | `sw_61a26c46731a4afc81a06b22a062ea9f` |
| 4 | Hermes Supervisor | `9007194959773929` | `sw_352a6d86bafd4ebdade991cd584772d6` |

The integration code waits for each turn's content to arrive on every other agent's listener queue, requires an event ID from those SSE-delivered events, and refuses to persist a turn without that evidence. The successful Discord response plus the four ordered rows with event IDs and message IDs therefore verifies the four-turn Official Switch/SSE delivery path. The sender order is Codex → AGY → Gemini → Hermes.

Runtime status reports Codex and AGY as native CLI modes and available. Gemini is explicitly a local fallback because its API credential is missing. Hermes is explicitly standalone governance mode because the Hermes daemon is disconnected. The discussion text identifies those modes; it does not provide session IDs or prove separate external Gemini/Hermes runtime execution.

At the time of this resume, backend PID `82131` was running and `/health/ready` returned `ready`. The live `/api/status` response showed Discord online in one guild with nine commands registered, and all four agents marked connected to Official Switch. This describes transport connectivity; Gemini remained a missing-credential local fallback and Hermes remained disconnected from its daemon.

### Actual Discord /assign interaction and approval gate

The Chrome interaction attempt returned `noWindowsAvailable`; the Discord native client remained accessible. Used its Application Launcher, selected AgentHive's registered `assign` command, supplied the existing project ID, and submitted the application command. Discord returned the Hermes WBS embed, including the consensus architecture and these assignments:

| Task | Assigned agent | Priority | Status |
|---|---|---|---|
| `TASK-01` — Core In-Memory Engine & Storage Primitive | ChatGPT Codex | P0 | `PENDING_APPROVAL` |
| `TASK-02` — CLI Harness & Sandboxed Docker Packaging | AGY (Antigravity) | P1 | `PENDING_APPROVAL` |
| `TASK-03` — Adversarial Unit Test Suite & Concurrency Verification | Google Gemini | P0 | `PENDING_APPROVAL` |

Database verification shows project state `AWAITING_APPROVAL`, three tasks, and `human_approved=0` for every task. No task was approved or executed. The flow is intentionally stopped here for the project owner to approve in Discord.

### Remaining blockers / evidence limits

- Owner approval in Discord is required before any execution. Do not approve or execute on the owner's behalf.
- No execution, generated project source, or generated-project test evidence exists for these proposed tasks yet.
- The four original analysis records have no persisted raw runtime payload/session evidence. Current backend status identifies Codex/AGY native CLI as available, while Gemini and Hermes remain fallbacks.
- Discord showed two earlier plain-text composer entries (`/discussdiscuss` and `/discuss/`); they were not application interactions and are excluded from command evidence.
- The top-level readiness verdict remains **NOT READY** until owner-approved execution, verification, and reporting are completed.
