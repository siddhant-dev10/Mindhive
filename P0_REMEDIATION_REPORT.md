# AgentHive V2 P0 Remediation Report

**Date:** 2026-11-07  
**Result:** PARTIALLY COMPLETE  
**Scope:** P0 security and core workflow remediation only

## 1. Initial findings

- `/assign` called local Hermes synthesis with an empty discussion list, although four persisted discussion turns existed for the acceptance project.
- Historical `discussion_messages` rows had project IDs and Switch event/message IDs, but no per-message Switch room ID. The project row has a room ID. The historical rows were not backfilled because the exact room association cannot be proven from the old schema alone.
- Codex created placeholder session IDs; AGY fallback prose could be labelled Native Antigravity CLI; Gemini and Hermes local work was not consistently marked as fallback. The dashboard also treated binary availability as native execution.
- Test execution ran Python on the host with the full application environment. Workspace validation included the repository and general temporary directories. The Docker runner built project-supplied Dockerfiles.
- The Discord “Approve & Run” button recorded approval and invoked `/report` in the same action.
- Project creation, analysis, discussion and assignment API routes were unauthenticated. Local Switch bridge routes also accepted unauthenticated mutations and event reads.
- Credential-like material was found in the locations listed in §3. No credential-bearing file was edited, no values are reproduced here, and no authentication attempt or credential rotation was made.

## 2. Changes implemented

The following source files were changed during this remediation:

- `agenthive/config.py`
- `agenthive/database.py`
- `agenthive/security.py`
- `agenthive/main.py`
- `agenthive/models/project.py`
- `agenthive/engine/orchestrator.py`
- `agenthive/engine/execution.py`
- `agenthive/agents/agy.py`
- `agenthive/agents/codex.py`
- `agenthive/agents/gemini.py`
- `agenthive/agents/hermes.py`
- `agenthive/switch/client.py`
- `agenthive/switch/server.py`
- `agenthive/discord_gateway/bot.py`
- `agenthive/discord_gateway/dispatcher.py`
- `agenthive/discord_gateway/views.py`
- `agenthive/discord_gateway/embeds.py`
- `tests/test_p0_remediation.py` (new isolated regression tests)

Changes are in the working tree and were not committed. Existing modifications and untracked evidence were preserved.

## 3. Security findings

### Credential locations

Credential-like material is present in these filenames:

- `.env`
- `.env.example`
- `docker-compose.switch.yml`
- `deploy/docker-compose.switch.yml`
- `SWITCH_ENGINEERING_REPORT.md`
- `FINAL_ACTIVATION_GUIDE.md`

The local `.env` file is mode `0600`. Its contents were not printed or copied. The checked-in example contains placeholders. Both Compose files contain non-placeholder credential-like defaults; a read-only comparison found corresponding values in the running Switch/PostgreSQL container configuration. `SWITCH_ENGINEERING_REPORT.md` contains bearer-shaped material. One credential-like entry in `FINAL_ACTIVATION_GUIDE.md` matched a value in `.env`. These may be active; their values and use were not tested. The source files were left intact because changing them could disrupt the running stack or lose historical material. No tokens, passwords, or keys appear in this report.

During that comparison, one broad read-only container query also collected credential-variable entries from an unrelated `openwa-api` container into transient process memory. Its values were not printed, logged, or used, and no follow-up inspection or action was taken on that container. That inventory query was broader than necessary.

### API and network boundaries

- Dashboard project mutation routes now require a configured `AGENTHIVE_DASHBOARD_API_TOKEN`, accept only loopback callers, and reject disallowed browser origins. Approval, rejection and execution API endpoints remain Discord-owner-only (HTTP 403).
- Local Switch bridge routes now require a Bearer token from the configured Switch registration/API credential; local clients send that credential. The generated placeholder API key was removed from the local registration response. The health endpoint remains public for readiness checks.
- Wildcard host binding is clamped to `127.0.0.1` unless `AGENTHIVE_ALLOW_REMOTE_BIND=true`. The effective source configuration is loopback. The running backend was independently observed listening on `127.0.0.1:8000`.
- Native Codex and AGY child processes now receive a small environment allowlist. AgentHive credentials are not inherited by those child processes.
- Secret redaction now covers common provider tokens, Bearer values, labelled key/secret assignments, and Discord tokens. Discussion and analysis content and persisted runtime evidence are redacted before storage or Switch delivery.
- Workspace validation now permits only the configured workspace root and its descendants. Agent task adapters additionally require the exact project workspace recorded for the task’s project ID, blocking cross-project workspace access.
- Both existing Switch Compose files were inspected without emitting their environment values. They set no explicit non-root `user`, read-only filesystem, dropped capabilities, `no-new-privileges`, or resource limits; the services publish ports and do not declare a custom network. The live stack was not changed or restarted because doing so could disrupt the running integration. Compose hardening remains an operational blocker.

### PID 53932 investigation

- PID `53932` is owned by `sidh._.` and is a child of PID `52272` (`-zsh`), whose parent is PID `52264` (`/usr/bin/login`).
- It started at `2026-11-07 14:23:25` local time, runs the AGY executable at `~/.local/bin/agy.1794041605499627000.old`, and has working directory `/Users/sidh._./mindhive`.
- Its command includes `--dangerously-skip-permissions` and print mode. Prompt text was not copied into this report. No child processes were observed in the earlier read-only inspection.
- The process is not shown as a child of the AgentHive backend. Its precise purpose cannot be established from process metadata. The bypass flag means it may act with broader permissions than this application allows. It and its parent were not signalled, suspended, modified, or terminated.
- Safest owner action: inspect the associated terminal and AGY task, preserve any needed work, then exit it normally if it is no longer required.

## 4. Discussion-aware planning

- Planning now loads discussion rows for the requested project in stable turn order and checks project ID, the project’s current room ID, sender, content and turn index.
- In official Switch mode, each row must also have both Switch event and message IDs. New discussion rows persist the room ID and runtime evidence.
- The synthesis function receives the actual ordered rows. The local governance plan records ordered sender/turn/source IDs and short discussion excerpts in its evaluated arguments; audit evidence is persisted before pending tasks are written.
- Empty discussion history, absent room association, mismatched rooms, or missing Official Switch evidence fail closed before existing tasks can be deleted or replaced.
- Regression tests verify ordered delivery to synthesis, correct project/room association, source evidence, and no approval or execution side effects.
- The existing acceptance project’s older rows have no room ID in its current database schema. They were not backfilled, re-planned, or modified. Its `/assign` command was not invoked.

## 5. Runtime provenance

- Codex uses a session ID only when one is extracted from actual CLI output. Failed or timed-out calls are marked as fallback with exit/error evidence. Native discussion attribution requires a successful invocation with usable output.
- AGY fallback text can no longer pass a response-length heuristic and be labelled native. A native label requires a successful JSON success envelope with a non-empty response. Invalid/error/time-out paths are marked fallback.
- Gemini reports `LOCAL FALLBACK` when no API request succeeds or no API credential is configured. A request ID is retained only when returned by the API.
- Hermes reports `LOCAL GOVERNANCE FALLBACK` when no daemon response was obtained. A daemon request ID is recorded only if returned. Local plan synthesis is explicitly identified as governance fallback.
- Analyses and discussion rows store runtime mode, session/request IDs when actually supplied, process ID where observed, exit status, and error reason. Schema changes are additive and do not backfill invented evidence.
- Dashboard refresh no longer probes Gemini or Hermes. Codex/AGY binary presence is presented as “available; execution not verified,” not as a successful run.
- Agent provenance tests use fakes; no native Codex/AGY process or Gemini/Hermes service was invoked for this mission.

## 6. Execution and approval safeguards

- Approval requires the action’s actor ID to match both the configured Discord owner and the project owner recorded at creation.
- Approval stores actor, timestamp and a hash over the exact task proposal fields. Execution rechecks the project, approval record, owner and task hash; modified tasks fail closed.
- Each task adapter independently requires a persisted owner approval for the exact task version and project workspace. Codex does not synthesize replacement files when native execution fails; AGY, Gemini and Hermes refuse task execution until genuine task executors are implemented.
- The approval button now records approval only. `/report` is a separate execution action. No acceptance-project approval or execution occurred.
- `AGENTHIVE_TASK_EXECUTION_ENABLED` defaults to false. It is false in the current configuration. Execution therefore fails closed until a secure agent runner is deliberately configured.
- Before task adapters run, the orchestrator verifies that the configured test-runner image is already present locally. It also refuses AGY, Gemini and Hermes assignments while those adapters are local fallbacks rather than native task executors.
- Host-side tests are disabled. Tests run only in an already-installed `AGENTHIVE_TEST_RUNNER_IMAGE` with no network, read-only workspace, non-root UID, dropped capabilities, no-new-privileges and resource limits. The image is not configured, so this runner was not executed.
- Workspace-supplied Dockerfiles are no longer built or run. Codex and AGY timeout paths terminate their process groups; AGY retains partial-output length evidence. No task was executed.

### Remaining execution/API limitations

- `AGENTHIVE_DASHBOARD_API_TOKEN` is not configured, so dashboard mutations currently return 403.
- No vetted local test-runner image is configured, and task execution is disabled. This is an intentional fail-closed state, not a successful execution capability.
- The current Switch/PostgreSQL Compose definitions lack container hardening controls (non-root identity, capability drops, read-only filesystem, resource limits and explicit network isolation). Fixing and applying these settings requires a planned stack change and restart; neither was attempted.
- AGY, Gemini and Hermes task execution remains unavailable. Their adapters fail closed; the orchestrator also refuses plans assigning tasks to these fallback-only runtimes.
- The complete test suite was not run because it includes tests that invoke native CLIs and tests that register agents/create rooms/send messages to the live Official Switch service. Running those against the current environment would not be isolated.

## 7. Verification

The final safe test command used a temporary SQLite database, a temporary workspace root, and local Switch mode:

```sh
DATABASE_URL=sqlite:////tmp/agenthive-p0-final-test-5.db \
WORKSPACE_ROOT=/tmp/agenthive-p0-final-workspaces-5 \
SWITCH_MODE=local \
AGENTHIVE_TASK_EXECUTION_ENABLED=false \
AGENTHIVE_TEST_RUNNER_IMAGE= \
AGENTHIVE_DASHBOARD_API_TOKEN= \
AGENTHIVE_ALLOW_REMOTE_BIND=false \
./venv/bin/python -m pytest -q \
  tests/test_p0_remediation.py \
  tests/test_agenthive.py::test_database_initialization \
  tests/test_agenthive.py::test_switch_server_protocol \
  tests/test_discord_gateway.py::test_dashboard_cannot_bypass_discord_owner_approval_gate \
  --disable-warnings
```

- **Result:** 24 passed, 0 failed, 0 skipped; 2 pytest warnings; 0.22 seconds.
- **Test database:** `/tmp/agenthive-p0-final-test-5.db`; workspace under `/tmp/agenthive-p0-final-workspaces-5`.
- **Live services touched by tests:** none. Switch coverage used the local in-memory protocol only; all agent runtime calls were mocked or in fallback paths.
- **Full suite:** not run for the isolation reasons above. Historical 43-passed/3-failed results remain historical and were not reclassified.
- **Python AST:** 34/34 Python files parsed successfully.
- **JavaScript:** `node --check agenthive/ui/app.js` passed.
- **Whitespace check:** `git diff --check` passed.

## 8. Acceptance project integrity

Read-only database snapshots before and after the changes show the same state:

- **Project:** `4d633575-798c-4737-93c1-0dfbcd63db1b`, `AWAITING_APPROVAL`.
- **Project Switch room:** `c52deec5-df2e-46c0-9461-eebe885fb5c1`.
- **Discussion messages:** 4. Switch event/message IDs remain unchanged: `9007194959773920` / `sw_6871010e5fd847db8ec6eacef9ea25f8`; `9007194959773924` / `sw_2b68d61343244b83b8ab25219f9bfcee`; `9007194959773926` / `sw_61a26c46731a4afc81a06b22a062ea9f`; `9007194959773929` / `sw_352a6d86bafd4ebdade991cd584772d6`.
- **Tasks:** 3, all `PENDING_APPROVAL`; approvals remain false.
- **Execution logs:** 0.
- **Workspace files:** `PROJECT.md` only; `src`, `tests` and `docs` contain no generated project files.
- **Services:** Official Switch and PostgreSQL containers remained running. No stack was started or stopped.

## 9. Rollout state and manual decisions

Code changes are not active in the running backend. PID `82131` is still serving the prior in-memory code on loopback. No service restart or live database migration was performed. The additive database migrations passed against a synthetic legacy schema in the isolated tests, but have not been applied to `data/agenthive.db`.

Owner decisions still required before deployment:

1. Inspect PID `53932` in its terminal and decide when to exit it normally.
2. Authorize how to replace credential-like Compose/report material. The running Switch/PostgreSQL containers use values matching the Compose defaults; changing them may disrupt services. No credential was changed or rotated.
3. Choose a secure method to configure `AGENTHIVE_DASHBOARD_API_TOKEN` and a vetted, already-installed `AGENTHIVE_TEST_RUNNER_IMAGE`. Do not enter the token in chat or this report.
4. Authorize a controlled backend restart and additive migration after the credential and runner decisions are resolved.
5. Decide how to establish the missing room association for the acceptance project’s historical discussion rows if that project is ever to be re-planned. No inference or backfill was performed.

## 10. Verdict

**PARTIALLY COMPLETE.** The discussion-planning, provenance, approval separation, workspace boundary, redaction and API fail-closed code changes are implemented and covered by isolated tests. Deployment remains blocked by potentially active credential material, the untouched AGY bypass process, missing Compose container hardening, the unconfigured dashboard token and secure runner, and the fact that the running backend has not been restarted or migrated. The acceptance project remains untouched and unapproved.
