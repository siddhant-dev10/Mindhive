# AgentHive V2 — Release Checklist

## Security

- [x] Private `.env` is ignored by Git; template secret values are blank.
- [x] Dashboard owner-session, CSRF, exact-origin, loopback-mutation tests pass in isolation.
- [x] Project owner checks and approval task-version evidence are tested.
- [x] Dangerous permission-bypass flags are prohibited.
- [x] Implement and validate a vetted non-root isolated native-agent runner with container sandboxing, resource limits, zero Docker socket or host credential access, and generated file inventory.
- [ ] Deploy the updated dashboard/auth and runner code to the live backend process (requires authorized backend restart).
- [ ] Review and rotate any potentially active credentials with owner authorization; no rotation was performed.

## Infrastructure

- [x] Repository Compose templates contain no literal credential values and pass static `docker compose config --quiet` validation.
- [x] Pin and verify an immutable Official Switch image digest (`ghcr.io/sandbox-quantum/switch-core@sha256:03b2ea9caa38f235878f3d872ca99dee74c6bda7a731ea01a209edc739699c1d`).
- [x] Pin and verify an immutable PostgreSQL image digest (`postgres@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139`).
- [x] Prepare hardened Compose configuration with non-root identity, `cap_drop: ALL`, `no-new-privileges: true`, resource quotas, and internal network isolation.
- [x] Document Docker volume identity (`335d482fc95fde4b932db581b2678ed0da96c7f5d06523d0e87ed9cb716a53d7`), backup/restore procedures, and emergency rollback plan.
- [ ] Execute authorized container recreation and migration from `/tmp/test_official_switch` (strictly blocked pending operator maintenance window).

## Workflow

- [x] Discussion-aware planning preserves ordered project/room-associated source messages and fails on empty or mismatched history.
- [x] Approval is strictly separate from execution; owner identity and cryptographic task hash are checked.
- [x] Complete workflow verified in isolated tests: Project Creation → Analysis → Switch Discussion → Discussion-Aware Planning → Owner Approval → Secure Execution → Testing → Final Report.
- [x] Unavailable Codex/AGY/Hermes modes do not generate fake analysis or mock task files.
- [ ] Deploy updated backend and verify live Discord command synchronization.
- [ ] Re-run a fresh project through `/newproject`, `/analyse`, `/discuss`, `/assign` on the live Discord client.
- [ ] Obtain live owner approval on a disposable project in Discord.
- [ ] Trigger `/report` on Discord and verify live message delivery.

## Reproducibility and presentation

- [x] Install, configuration, architecture, workflow, security, deployment, and demo steps are documented.
- [x] Full test suite passes: 70 passed, 8 skipped, 0 failed in 1.22s.
- [x] FastAPI lifespan deprecation warnings eliminated cleanly.
- [ ] Clean-clone rehearsal on a fresh machine without local caches.
- [ ] Capture genuine post-remediation screenshots of the updated build.
- [ ] 3–5 minute live video recording completed.

## Acceptance

- [x] Existing acceptance project (`4d633575-798c-4737-93c1-0dfbcd63db1b`), discussion IDs, pending tasks, and workspace remain strictly unchanged.
- [ ] Live running processes and containers updated to match the verified codebase.

**Current disposition: READY FOR LOCAL SUPERVISED DEPLOYMENT; PUBLIC REPRODUCIBLE DEPLOYMENT GATED ON OPERATOR RESTART & MIGRATION.**
