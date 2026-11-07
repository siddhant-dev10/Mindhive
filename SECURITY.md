# AgentHive V2 — Security Model and Current Limits

## Dashboard authentication

The dashboard exchanges a credential supplied at sign-in for a short-lived signed session cookie. The credential is not stored in JavaScript, local storage, or session storage. The cookie is HttpOnly, SameSite Strict, and Secure in production. Mutating API calls require a valid session, a CSRF token held in page memory, an exact allowed Origin, and a loopback client address. Login attempts are rate-limited in process memory.

This is a single-owner local dashboard design, not a multi-user identity provider. Configure a private random dashboard credential of at least 32 characters, set exact allowed origins, use HTTPS in production, and set `AGENTHIVE_DASHBOARD_COOKIE_SECURE=true`. Do not expose the dashboard remotely without a separately reviewed proxy/authentication design. Changes are unit-tested through isolated ASGI requests; the live backend has not been restarted to load them.

## Owner authorization and approval

Project reads and mutations require the configured owner. Approval records the owner identity, timestamp, and a hash of the exact task fields. Changes after approval invalidate that evidence. Discord approval and execution are separate user actions. Tests exercise non-owner, stale-task, and unauthenticated cases using temporary databases.

The existing acceptance project is not a test fixture. Its approval state and tasks were not changed in this work.

## Workspace and subprocess boundaries

Project workspaces must resolve beneath the configured workspace root, and task workspaces must match the exact project record. Native agent subprocess environments omit AgentHive API credentials. CLI invocations prohibit dangerous permission-bypass arguments (e.g. `--dangerously-skip-permissions` is rejected by security assertions) and bound process lifetime.

Task execution is implemented through a verified isolated non-root container runner:
- **Non-root execution:** `--user=1001:1001` (or `65534:65534`).
- **Network isolation:** `--network=none` disables outbound network calls by default during task execution.
- **Filesystem sandboxing:** Read-only root filesystem with restricted tmpfs on `/tmp:rw,noexec,nosuid,size=64m`.
- **Zero privilege escalation:** `--cap-drop=ALL` and `--security-opt=no-new-privileges:true`.
- **Zero Docker socket access:** The Docker socket `/var/run/docker.sock` is never mounted or accessible.
- **Zero host credential leakage:** Subprocess and container environments are strictly stripped of AgentHive API tokens.
- **Resource bounds:** 1.0 CPU, 512MB RAM, and 64 PIDs enforced per container.
- **Execution tracking:** Exact file inventories (SHA-256 and size) are computed before and after task execution.
- **Fail-closed:** If `AGENTHIVE_TASK_EXECUTION_ENABLED` or `AGENTHIVE_SECURE_AGENT_TASK_RUNNER_CONFIGURED` is false, or if the runner image is missing, task execution fails closed. Host execution is strictly blocked.

## Official Switch

`SWITCH_MODE=official` is the default. Unknown modes fail. Official room discussion must verify participants and actual SSE delivery before saving a message. `SWITCH_MODE=local` is an explicit development/test choice and must be labeled local. No automatic fallback from Official Switch is allowed.

## Secrets

- `.env` is ignored by Git; keep it private and mode `0600`.
- `.env.example` contains blank secret fields and relative, non-user-specific paths.
- Shareable Compose templates require environment-supplied secrets and a pinned Switch image digest.
- Several historical report/template files contained credential-like strings. Before sanitizing those copies, the originals were preserved in the ignored `.local-private-evidence/2026-11-07/` directory with directory mode `0700` and file mode `0600`. Do not publish or commit this archive.
- No credential was rotated, revoked, or authenticated against during this work.
- Runtime output redaction covers common bearer, Discord, Google, OpenAI, AWS, webhook, URL-password, and private-key patterns. Redaction is defense in depth, not permission to log secrets.

## Deployment boundaries

The active Switch/PostgreSQL stack is owned by an external Compose project and Docker-managed volume. The repository templates define a separate stack and volume and have not been launched. Their `latest` dependency has been replaced by a required immutable image reference, but image compatibility, role permissions, health behavior, backup/restore, and migration have not been exercised. No database migration, container restart, or credential rotation was performed.

## Reporting security defects

Do not include live secret values, partial values, hashes, tokens, or credential-bearing command lines in reports or issues. Report filenames, variable names, affected component, and exposure class only.
