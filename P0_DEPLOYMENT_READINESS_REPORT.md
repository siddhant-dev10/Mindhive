# AgentHive P0 Deployment Readiness Investigation

**Date:** 2026-11-07  
**Scope:** Read-only operational investigation. This report is the only file created by this mission.  
**Deployment verdict:** **NOT READY TO DEPLOY**

## Executive summary

The code remediation is not live yet. The backend PID `82131` still serves its earlier in-memory version. The AGY process PID `53932` is a foreground process attached to a terminal, but its terminal buffer could not be safely accessed; do not assume it is safe to close. The running Switch/PostgreSQL stack belongs to Docker Compose project `test_official_switch` and was created from `/tmp/test_official_switch/docker-compose.yml`, not either Compose file in the repository. Its database is on a Docker-managed volume that must be explicitly preserved during any recreation.

Credential-like material exists in several untracked files, including the active `/tmp` Compose file and two reports. The active stack's credential values match that Compose file. No values, partial values, hashes or tokens are reproduced. The dashboard token guard is enabled in source, but the dashboard browser code sends no Authorization header, so setting the token alone would leave dashboard mutations blocked. The acceptance project remains unchanged and unapproved.

No source, credential, process, database or running service was modified. No authentication attempt, migration, task approval or task execution occurred. Only the named processes, AgentHive files, the two Switch/PostgreSQL containers and the existing AgentHive database were inspected.

## 1. AGY process investigation

| Item | Finding |
|---|---|
| Process | PID `53932`, owner `sidh._.`, state `S+` (foreground, sleeping/waiting) |
| TTY | `ttys000`; stdin is attached to `/dev/ttys000` |
| Start | `2026-11-07 14:23:25` local time |
| Executable | `/Users/sidh._./.local/bin/agy.1794041605499627000.old` |
| Command flags | `--dangerously-skip-permissions`; no prompt argument was present in the current sanitized argument inspection |
| Parent | PID `52272`, `-zsh`, same TTY; its parent is PID `52264`, `/usr/bin/login` |
| Children | None observed |
| Working directory | `/Users/sidh._./mindhive` |

The Kitty terminal application is running. The computer interface refused access to that app for safety reasons, so the visible terminal buffer and any pending prompt/output could not be inspected. I did not use another method to read the PTY buffer. The process is therefore consistent with an unfinished interactive AGY session, but its exact purpose and unsaved work cannot be established.

The AgentHive database has no task in `RUNNING`, `EXECUTING` or `IN_PROGRESS` status. The acceptance project has three pending tasks and zero execution logs. There are historical AGY execution records elsewhere in the database, but no record links PID `53932` to one. These facts do not prove that the terminal session has no unfinished work.

**Exit assessment:** It is **not verified safe to exit**. Preserve the process and parent. The owner should inspect the Kitty terminal, review any pending AGY response or prompt, save needed output, and only then exit normally if the session is no longer needed. Neither process was signalled or changed.

## 2. Credential inventory

Classification is based on variable names, placeholder/default patterns, Git state, file references and—only for the named Switch/PostgreSQL containers—in-memory comparisons that emitted booleans and variable names only. It is not a claim that any credential was authenticated. Values were never printed or copied into this report.

| File | Credential type and classification | Service/component reference | Git/current-stack status |
|---|---|---|---|
| `.env` | `DISCORD_BOT_TOKEN`: non-placeholder, potentially active. `SWITCH_REGISTRATION_TOKEN` and `SWITCH_API_KEY`: non-placeholder and potentially active. | `agenthive/config.py` loads `.env`; Discord gateway reads the bot token; Switch client and local bridge use the Switch credential names. In-memory comparison found both Switch values equal the current Switch registration credential. The current backend's loaded environment was not read. | Ignored/untracked; mode `0600`. Likely used when AgentHive starts from this project directory. Do not overwrite or rotate without an approved plan. |
| `.env.example` | Discord/OpenAI/Gemini values are placeholders. Switch registration/API entries and Hermes daemon token are non-placeholder generated/default candidates. | Discord, Codex/OpenAI and Gemini config references exist. `HERMES_DAEMON_TOKEN` has no source-code reference in this repository. | Tracked by Git; mode `0644`. Switch defaults are not the active container's Compose source. |
| `docker-compose.switch.yml` | Non-placeholder credential defaults for PostgreSQL and Switch, including database passwords, registration token, secret keys and gateway administrator password. | PostgreSQL and Switch services in this file. | Untracked; mode `0644`. Docker labels show this file did **not** create the running stack. |
| `deploy/docker-compose.switch.yml` | Same credential categories/default pattern as the root Compose file. | PostgreSQL and Switch services in this file. | Untracked; mode `0644`. Not the active stack source. |
| `SWITCH_ENGINEERING_REPORT.md` | Contains text matching `.env` Switch registration/API credential values. | Historical engineering report; no runtime service consumes the report. | Untracked; mode `0644`; potentially active credential material in a shareable document. |
| `FINAL_ACTIVATION_GUIDE.md` | Contains text matching `.env` Switch registration/API credential values. | Historical activation guide; no runtime service consumes the guide. | Untracked; mode `0644`; potentially active credential material in a shareable document. |
| `/tmp/test_official_switch/docker-compose.yml` | Literal, non-placeholder PostgreSQL/Switch database, owner, registration, secret-key and gateway administrator credentials. Current container values match the literals in this file. | This file created the running PostgreSQL and Switch containers. Its credential environment names are present in those containers. | Outside the canonical repository and not in its Git worktree; mode `0644`. No adjacent `/tmp/test_official_switch/.env` exists. This is the active credential-bearing Compose file. |

The active Compose file's values are required by the running services: PostgreSQL has `POSTGRES_PASSWORD`; Switch has `DB_PASSWORD`, `DB_OWNER_PASSWORD`, `AGENT_REGISTRATION_TOKEN`, `SECRET_KEYS` and `GATEWAY_ADMIN_PASSWORD`. I did not disclose or authenticate with any value. The two repository Compose files contain credential defaults too, but they are not the source identified by the running containers.

**Containment risk:** `0644` on the active Compose file and historical reports permits local users with file access to read them. Removing or rewriting these files could destroy historical evidence or disrupt service configuration, so no cleanup was attempted. Owner decision is required on preserving a restricted original plus creating sanitized shareable copies versus replacing the contents; credential rotation must be separately authorized.

## 3. Active Compose and deployment review

### Runtime ownership and ports

Docker metadata identifies:

- Compose project: `test_official_switch`.
- Compose source label: `/tmp/test_official_switch/docker-compose.yml`.
- Switch container: `ghcr.io/sandbox-quantum/switch-core:latest`, running; no health check status was reported.
- PostgreSQL container: `postgres:16-alpine`, running and healthy.
- Host mappings: `127.0.0.1:5433` to PostgreSQL `5432`; `127.0.0.1:8080` and `127.0.0.1:8082` to Switch ports `8000` and `8081`.
- AgentHive backend: PID `82131` listens on `127.0.0.1:8000`.
- No competing listeners were observed on those four host ports.
- PostgreSQL data is mounted at `/var/lib/postgresql/data` on a Docker-managed volume. The Compose file does not declare an explicit persistent volume mapping; Switch has no data mount reported.

The repository files `docker-compose.switch.yml` and `deploy/docker-compose.switch.yml` are not the configuration that created the live containers. The Docker Compose project label is the direct evidence for the active source file. Do not assume a change to either repository file will affect the current stack.

### Missing or unverified controls

The active Compose definition does not explicitly configure a non-root user, `read_only`, `cap_drop`, `no-new-privileges`, resource limits, or a custom network. `privileged` is false, and host ports bind to loopback. An empty Compose `user` setting means the image default applies; the effective in-container user was not independently verified. The Switch image uses the mutable `latest` tag. PostgreSQL is healthy, but Switch readiness was not verified in this investigation.

### Can hardening preserve the existing database?

Yes, a container can be recreated while preserving the current PostgreSQL data **only if** the current Docker volume is backed up and the exact existing volume is deliberately reattached. The current Compose definition lacks an explicit volume mapping, so a naïve recreate risks starting against a fresh empty volume. Never use `docker compose down -v` or remove the current volume. Before deployment, make and verify a database backup, record the exact volume identity in the restricted operations record, declare/reuse that volume explicitly, and verify the recreated PostgreSQL container mounts the same data before allowing Switch to connect.

The safe rollback is to retain the original Compose file and image references in restricted storage, preserve the database volume, and recreate the prior services against that same volume. If the volume identity or restore cannot be verified, stop before container recreation. Any credential rotation must be coordinated with the restored configuration; do not roll back by exposing old credentials in a report or shell history.

## 4. Dashboard token, runner and workspace requirements

### Dashboard token

- Exact setting: `AGENTHIVE_DASHBOARD_API_TOKEN`.
- Source reads it from the process environment via `python-dotenv`/`os.getenv`; no value is present in `.env` or `.env.example` according to the prior configuration audit.
- The mutation middleware requires a Bearer token, a loopback client and an allowed browser Origin for `/api/projects` mutation routes. With no token, mutations return 403.
- The dashboard UI's `fetch()` calls do not add an `Authorization` header. Therefore, configuring this server token alone will not make browser mutations work. A safe browser credential-delivery design must be selected and implemented before expecting dashboard mutations to succeed. Do not embed the token in static JavaScript or commit it.
- Suitable secret delivery is an owner-controlled secret store or a mode-`0600` ignored local environment file loaded only by the service. Avoid command-line arguments, shell history, debug logs and browser-visible shared configuration. The application itself does not implement a Keychain lookup.

### Task test runner

- Exact settings: `AGENTHIVE_TEST_RUNNER_IMAGE`; `AGENTHIVE_TASK_EXECUTION_ENABLED` defaults to `false`.
- The image must already exist locally; the code does not pull it. The runner invokes `python -m unittest discover -s tests`, so Python and any project test dependencies must be installed in the image.
- The test container is invoked with `--network=none`, read-only root, UID/GID `65534:65534`, dropped all capabilities, `no-new-privileges`, PID/memory/CPU limits, a restricted `/tmp`, and the project workspace mounted read-only at `/workspace`. Timeout kills its process group.
- The current code checks only that the named image exists. It does not verify image provenance or enforce a digest. Before enabling it, build or select a reviewed image from a pinned base, record and configure its immutable digest, verify its contents and non-root execution, and keep it locally available. Do not enable task execution as part of runner setup alone.

### Workspace isolation

`WORKSPACE_ROOT` must be a dedicated AgentHive workspace root, not the repository root or a general user directory. The validator resolves paths and requires the exact workspace recorded for the task's project ID. Each project needs its own directory; symlink/path traversal and cross-project paths must fail closed. Tests receive read-only workspace access. Native task runners must remain constrained to the individual project workspace and use their configured workspace-write sandbox; no unrestricted permission flags are acceptable. The acceptance workspace is currently separate and contains only `PROJECT.md`.

## 5. Database and rollout state

The AgentHive application database is the SQLite file `data/agenthive.db`; it is distinct from the Switch PostgreSQL database. The current SQLite schema does not yet contain the additive remediation columns for project owner, discussion room/runtime evidence and task approval actor/time/hash. The migration code adds those columns during database initialization. The Switch PostgreSQL schema was not migrated or changed.

The acceptance project currently remains:

- Project ID `4d633575-798c-4737-93c1-0dfbcd63db1b`, state `AWAITING_APPROVAL`.
- Four discussion messages with their existing Switch event/message IDs.
- Three tasks, all `PENDING_APPROVAL`; zero approvals and zero execution logs.
- Workspace contains only `PROJECT.md`.

The historical discussion rows do not have a room ID in the existing SQLite schema. The additive migration will leave that field null. Planning for this project should continue to fail closed unless the correct room association is established from reliable existing evidence. Do not backfill by inference or rerun `/assign` as a deployment smoke test.

## 6. Staged deployment plan

Downtime estimates below are planning ranges, not measured guarantees. Exact duration depends on backup size, container readiness and Discord reconnect behavior. Stop if a health check or integrity comparison fails.

| Stage | Actions and gates | Expected downtime | Rollback point |
|---|---|---|---|
| **A — Credential containment and owner decisions** | Owner inspects the AGY terminal and decides when it can exit normally. Decide treatment of the `.env`-matching values in reports, untracked Compose defaults and the active `/tmp` Compose file. Decide whether any credential rotation is authorized and how to preserve originals privately. No service changes until the credential owner approves a plan. | None for investigation/decisions. If Discord credential rotation is later approved, plan a gateway reconnect; if Switch credentials change, plan coordinated Switch/AgentHive reconfiguration and outage. | No-op: preserve existing files and credentials. Do not proceed until owner decisions are recorded. |
| **B — Compose hardening** | Securely preserve the active Compose source; prepare a hardened definition with explicit non-root identity where supported, read-only/capability/resource restrictions, loopback bindings, pinned image references, and an explicit mapping to the existing PostgreSQL volume. Validate the resolved configuration without printing secrets. Take a consistent database backup and verify it before recreating anything. Confirm image compatibility, especially Postgres entrypoint requirements. | Estimate 5–15 minutes for Switch/PostgreSQL recreation and readiness checks; unmeasured. Switch-dependent operations unavailable during restart. | Recreate from the retained prior configuration against the same verified volume. If volume reattachment or health cannot be proven, stop before Switch reconnects. Never remove the volume. |
| **C — Dashboard token and runner configuration** | Resolve the UI token delivery gap before setting `AGENTHIVE_DASHBOARD_API_TOKEN`. Configure it through a protected secret source. Review and locally preload an immutable, vetted test-runner image; set `AGENTHIVE_TEST_RUNNER_IMAGE`. Keep `AGENTHIVE_TASK_EXECUTION_ENABLED=false` until separate authorization and safeguards are verified. | Image preparation: none. Backend restart to load settings: estimate 1–3 minutes, including Discord gateway reconnect; unmeasured. | Remove the new setting or restore prior protected configuration and restart once. Since execution remains disabled, runner setup can be rolled back without task effects. |
| **D — Additive database migration** | Back up `data/agenthive.db` using a consistent SQLite backup, verify the backup, stop writes, and let the additive initialization migration add only the documented columns. Confirm row counts, acceptance state, task approval flags, discussion IDs and workspace files before any Discord action. Do not migrate Switch PostgreSQL. | SQLite migration expected to take seconds for this database, but backend is unavailable while stopped; verify duration before scheduling. | Additive columns should be backward-compatible. If startup or integrity checks fail, stop the new backend and restore the verified SQLite backup only with owner authorization; keep the original copy. |
| **E — Controlled backend restart** | Stop PID `82131` gracefully through its known service owner, verify it exited, then start exactly one backend using the approved startup procedure. Confirm PID/listener uniqueness, dashboard health, Switch registrations and Discord gateway/command status. Do not start a second backend concurrently. | Estimate 1–3 minutes for backend startup and Discord reconnect; unmeasured. | Stop the new instance and return to the prior code/config against the same SQLite database. Do not discard the additive migration or restore a database unless integrity requires it and the owner approves. |
| **F — Live smoke tests** | Use read-only Discord status/command synchronization checks and Switch readiness/room read checks first. Verify project API reads and that unauthenticated/cross-origin mutations fail closed. Because browser UI does not send the token, test authenticated project mutation only after its credential-delivery design is implemented. If a write test is authorized, use a new isolated smoke project, never the acceptance project. Verify approval presentation and separation without automatically approving or executing anything. Any live owner approval test must be performed by the owner on a dedicated smoke task. | No planned outage; smoke tests may create persistent records if write operations are approved. | Stop testing on unexpected writes, failed auth or degraded health. Preserve the smoke project and evidence; no cleanup/deletion without approval. |
| **G — Acceptance-project integrity verification** | Take read-only before/after snapshots of the known project, its four Switch IDs, three pending tasks, approval fields, execution-log count and workspace contents. Confirm all remain unchanged. Do not run `/assign`, approve or execute acceptance tasks. | None. | If any value changed unexpectedly, halt and preserve logs/database; do not attempt an automatic repair. |

### Owner decisions required before deployment

1. Inspect the Kitty terminal and decide whether PID `53932` can exit normally; I cannot confirm unfinished work is saved.
2. Decide whether to rotate potentially active credentials and how to preserve/sanitize historical reports and untracked Compose files. Rotation is not authorized by this investigation.
3. Approve a secure dashboard token delivery design; server-side token configuration alone is insufficient for current browser requests.
4. Select/approve the immutable test-runner image and secret storage method; keep task execution disabled unless separately authorized.
5. Approve a controlled recreation of Switch/PostgreSQL containers and the explicit reuse/backup plan for the current Docker volume.
6. Authorize the SQLite backup, additive migration and controlled backend restart.
7. Establish the acceptance project's historical discussion-room association only if there is reliable evidence; otherwise keep it blocked from replanning.
8. Approve any write-based live smoke project. Do not use or alter the acceptance project for smoke tests.

## 7. Verification and limitations

- Process metadata, TTY attachment, executable path, start time, parent chain and current flags were checked without reading process environment variables. No process signal was sent.
- Kitty was listed as running, but the computer-use interface explicitly denied access to that app. No terminal buffer was read.
- Docker project/config labels, images, health, port bindings, mounts and selected credential comparisons were inspected for only the named Switch and PostgreSQL containers. Container environment data was processed in memory; output contained variable names and comparison results only. No unrelated container was inspected.
- Host listener checks found only Docker Desktop listeners on `5433`, `8080`, `8082` and backend PID `82131` on `8000`.
- AgentHive task-state counts were read from SQLite in read-only mode. No writes, migrations, test-suite runs, authentications, Discord interactions or Switch mutations occurred.
- The full task execution and live service behavior remain unverified. The working-tree code has not been loaded by the current backend. No claim is made that remediation is deployed.

**Final assessment: NOT READY TO DEPLOY.** Resolve credential containment and the terminal uncertainty, close the dashboard token delivery gap, harden the active Compose source while preserving its existing volume, configure a reviewed runner, then use the staged migration/restart and smoke-test sequence above.
