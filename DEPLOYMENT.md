# AgentHive V2 — Deployment and Operations

## 1. Deployment Readiness Verdict

### A. Local Deployment Readiness: PARTIAL / CONDITIONAL
- **Status:** **READY for local supervised execution** upon owner-authorized backend process restart.
- **Completed:**
  * All isolated tests pass: **70 passed, 8 skipped, 0 failed**.
  * FastAPI lifespan management implemented cleanly (zero deprecation warnings).
  * Dashboard authentication complete (short-lived signed HttpOnly SameSite=Strict cookies, in-memory CSRF tokens, loopback client restrictions, rate limiting).
  * Isolated non-root task runner implemented and verified (`--network=none`, `--read-only`, `--user=1001:1001`, `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`, CPU/memory/pid limits, tmpfs `/tmp`, file inventory tracking).
  * Strict separation between owner approval and task execution verified.
  * Acceptance project `4d633575-798c-4737-93c1-0dfbcd63db1b` preserved intact (4 messages, 3 pending tasks, 0 approvals, 0 execution logs).
- **Remaining Requirements before live local restart:**
  1. Graceful restart of backend PID `82131` to load updated worktree code into memory.
  2. Owner-provided `AGENTHIVE_DASHBOARD_API_TOKEN` configured in private mode-0600 `.env`.
  3. Interactive owner verification on a fresh disposable test project (e.g. `/newproject`, `/analyse`, `/discuss`, `/assign`, `/approve`, `/report`).

### B. Public Reproducible Deployment Readiness: BLOCKED
- **Status:** **BLOCKED** pending infrastructure migration approval, credential rotation, and public endpoint hardening.
- **Remaining Requirements for Public Release:**
  1. Controlled migration from the external `/tmp/test_official_switch` Docker Compose stack to the repository hardened Compose template.
  2. Data volume backup and restore rehearsal on an isolated staging server.
  3. Coordinated credential rotation for Discord gateway, Switch registration, and PostgreSQL administrator credentials.
  4. Public TLS reverse proxy (e.g. Caddy / Nginx) with HTTPS and valid certificates (dashboard currently restricts mutations to loopback origins).
  5. Clean-clone rehearsal on a fresh Linux/macOS host without pre-existing cache.

---

## 2. Active Infrastructure Inventory

The live Switch/PostgreSQL stack was inspected in read-only mode:

| Component | Active Live Value | Repository Hardened Target |
|---|---|---|
| **Compose Project** | `test_official_switch` | `agenthive-switch` |
| **Compose Source** | `/tmp/test_official_switch/docker-compose.yml` | `docker-compose.switch.yml` |
| **PostgreSQL Container** | `test_official_switch-postgres-1` (Up, healthy) | `postgres` service with healthcheck |
| **PostgreSQL Image Digest** | `postgres@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139` | Pinned immutable digest |
| **PostgreSQL Volume** | `335d482fc95fde4b932db581b2678ed0da96c7f5d06523d0e87ed9cb716a53d7` | Named/reusable: `${SWITCH_POSTGRES_VOLUME:-agenthive_switch_postgres_data}` |
| **Switch Container** | `test_official_switch-switch-1` (Up) | `switch` service with `depends_on: postgres` |
| **Switch Image Digest** | `ghcr.io/sandbox-quantum/switch-core@sha256:03b2ea9caa38f235878f3d872ca99dee74c6bda7a731ea01a209edc739699c1d` | Pinned immutable digest |
| **Port Bindings** | `127.0.0.1:5433` (Postgres), `127.0.0.1:8080` (Switch API), `127.0.0.1:8082` (Switch SSE) | Explicit loopback bindings only |

> [!IMPORTANT]
> The active Docker-managed PostgreSQL volume `335d482fc95fde4b932db581b2678ed0da96c7f5d06523d0e87ed9cb716a53d7` must **never** be deleted or pruned. It contains the active Switch database state.

---

## 3. Hardened Compose Architecture

The repository files `docker-compose.switch.yml` and `deploy/docker-compose.switch.yml` implement:
1. **Capability Stripping:** `cap_drop: ALL` on Switch services.
2. **Privilege Escalation Block:** `security_opt: [no-new-privileges:true]` on all services.
3. **Resource Quotas:**
   - PostgreSQL: 2.0 CPUs, 1GB RAM, pids_limit 128.
   - Switch Core: 2.0 CPUs, 1GB RAM, pids_limit 256.
   - Init-DB: 0.5 CPUs, 256MB RAM, pids_limit 64.
4. **Network Isolation:** Services communicate over an internal network `switch_private` (`internal: true`). Host port mappings are strictly pinned to loopback (`127.0.0.1`).
5. **Healthcheck & Dependencies:** Switch depends on `postgres: condition: service_healthy` and `init-db: condition: service_completed_successfully`.
6. **Reusable Volume Configuration:** Set `SWITCH_POSTGRES_VOLUME=335d482fc95fde4b932db581b2678ed0da96c7f5d06523d0e87ed9cb716a53d7` to attach the existing data directly.

---

## 4. Backup, Restore, and Rollback Procedures

### A. PostgreSQL Volume Backup
Before any infrastructure restart or container recreation:
```sh
# 1. Ensure target backup directory exists
mkdir -p ~/mindhive/backups

# 2. Consistent snapshot of active PostgreSQL volume
docker run --rm \
  -v 335d482fc95fde4b932db581b2678ed0da96c7f5d06523d0e87ed9cb716a53d7:/volume_data:ro \
  -v ~/mindhive/backups:/backup \
  alpine tar czf /backup/postgres_switch_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /volume_data .
```

### B. SQLite Application Database Backup
```sh
# Consistent SQLite online backup
sqlite3 ~/mindhive/data/agenthive.db ".backup '~/mindhive/backups/agenthive_db_backup_$(date +%Y%m%d_%H%M%S).sqlite'"
```

### C. Volume Restore Procedure
```sh
# Restore snapshot into a target Docker volume
docker volume create agenthive_switch_postgres_restored
docker run --rm \
  -v agenthive_switch_postgres_restored:/volume_data \
  -v ~/mindhive/backups:/backup \
  alpine tar xzf /backup/<BACKUP_FILE>.tar.gz -C /volume_data
```

### D. Emergency Rollback Plan
If container recreation fails:
1. Re-run `docker compose -f /tmp/test_official_switch/docker-compose.yml up -d` pointing to original volume.
2. Verify Switch health at `http://127.0.0.1:8080/health/ready`.
3. If SQLite migration encounters errors, restore `agenthive_db_backup.sqlite` to `data/agenthive.db`.

---

## 5. Credential Containment and Rotation Order

If authorized by the project owner, execute credential rotation in strict sequential order:

1. **Step 1: Discord Bot Token**
   - *Owner:* Discord Developer Portal.
   - *Action:* Regenerate bot token.
   - *AgentHive Dependency:* Update `DISCORD_BOT_TOKEN` in `.env` (mode 0600).
   - *Verification:* Verify bot connects and registers 9 guild commands.
2. **Step 2: Switch Registration Token & API Key**
   - *Owner:* Switch Core Administrator.
   - *Action:* Update Switch registration secret in Switch configuration.
   - *AgentHive Dependency:* Update `SWITCH_REGISTRATION_TOKEN` and `SWITCH_API_KEY` in `.env`.
   - *Verification:* Test `/switch/api/v1/health/ready` and ensure all 4 agents connect and subscribe to SSE.
3. **Step 3: Database & Gateway Admin Passwords**
   - *Owner:* Infrastructure Operator.
   - *Action:* Apply after verified volume backup during scheduled maintenance window.
   - *Verification:* Confirm PostgreSQL authentication and Switch data queries.

---

## 6. Local API Startup & Verification

```sh
cd ~/mindhive
./venv/bin/python -m uvicorn agenthive.main:app --host 127.0.0.1 --port 8000
```
- Open `http://127.0.0.1:8000/`.
- Log in with the configured `AGENTHIVE_DASHBOARD_API_TOKEN`.
- Verify system status badge displays "HEALTHY" and Switch Core shows "ONLINE".
