# AgentHive — Environment Status (`ENVIRONMENT_STATUS.md`)
**Inspection Date:** 2026-11-05
**Hackathon Target:** Flip the Switch Hackathon 2026 (Best Business Workflow)

---

## 1. Operating System & Hardware

| Parameter | Observed Value | Status |
|---|---|---|
| **OS** | macOS 27.0.1 (Darwin 27.0.0, Kernel Version 27.0.0, root:xnu-13432.1.9~1/RELEASE_ARM64_T8142) | ✅ Verified |
| **Architecture** | `arm64` (Apple Silicon) | ✅ Verified |
| **Processor** | Apple M5 (10-core virtualization host) | ✅ Verified |
| **Memory (RAM)** | 16 GB (17,179,869,184 bytes) | ✅ Verified |
| **Disk Space** | Ample APFS root storage (>340 GB available) | ✅ Verified |

---

## 2. Runtimes, Compilers & Toolchains

| Tool | Version | Path | Status |
|---|---|---|---|
| **Python** | 3.9.6 (venv: 3.9.6) | `./venv/bin/python3` | ✅ Available |
| **pip** | 26.0.1 | `./venv/bin/pip` | ✅ Available |
| **Node.js** | v26.13.0 | `/opt/homebrew/bin/node` | ✅ Verified |
| **npm** | 11.20.0 | `/opt/homebrew/bin/npm` | ✅ Verified |
| **Git** | 2.54.0 (Apple Git-157) | `/usr/bin/git` | ✅ Verified |
| **Docker Engine** | 29.9.2 (build a82e528901) | `/opt/homebrew/bin/docker` | ✅ Online & Verified |
| **Docker Compose** | Compose v2 | `/Users/sidh._./.docker/bin/docker-compose` | ✅ Online |

---

## 3. Platform Integrations & Real Agent Runtimes

### 3.1 ChatGPT Codex (Native Codex CLI)
- **Binary:** `/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex`
- **Version:** `0.166.0-alpha.5.1 · macos-aarch64`
- **Sandbox Policy:** `-s workspace-write` (strict workspace confinement, no host escapes)
- **Execution Mode:** `codex exec -C <workspace_dir> -s workspace-write --skip-git-repo-check "<prompt>"`
- **Status:** **Verified Operational (Creates real files with live token telemetry)**.

### 3.2 AGY (Google Antigravity CLI)
- **Binary:** `/Users/sidh._./.local/bin/agy` (v1.5.1)
- **Security Hardening:** **Unrestricted bypasses (`--dangerously-skip-permissions`) completely eliminated**. Runs with `--sandbox`, `--add-dir <workspace_dir>`, and granular `--settings` permissions.
- **Capabilities:** Systems integration, CLI generation, non-root Alpine Docker packaging.
- **Status:** **Verified Operational & Security-Hardened**.

### 3.3 Google Gemini
- **Model Support:** `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-1.5-pro`
- **Integration:** Official REST API endpoint (`https://generativelanguage.googleapis.com/v1beta/models/...`) with multi-turn session history frames.
- **Capabilities:** Deep reasoning, adversarial QA test suite generation, ReDoS/race condition stress testing.
- **Status:** **Dual-mode Verified (Live REST API when key present; Deterministic QA matrix offline)**.

### 3.4 Nous Research Hermes Agent
- **Daemon URL:** `http://localhost:8686`
- **Binary:** `/usr/local/bin/hermes`
- **Architecture Distinction:** Cleanly separates the external Hermes runtime from AgentHive's local supervisory consensus engine.
- **Status:** **Operational via HermesRuntimeAdapter with clear standalone fallback when daemon is disconnected**.

### 3.5 Switch Platform (`sandbox-quantum/switch`)
- **Official Specification:** SandboxAQ `https://docs.switchagents.ai/` and `https://github.com/sandbox-quantum/switch`
- **Protocol:** HTTP REST + Server-Sent Events (SSE) `/switch/api/v1/agents/{id}/events` + WebSockets.
- **Verification:** 5/5 automated test pass (`tests/test_switch_protocol.py`) verifying agent registration, room creation, subscriptions, heartbeats, and real-time SSE event delivery.
- **Status:** **Fully Verified & Protocol-Compliant**.

### 3.6 Pony Tail Skill (Dietrich Gebert)
- **Philosophy:** 7-Step Ladder of Laziness, 100% standard library (0 external pip dependencies), minimal diffs.
- **Status:** **Enforced by PonyTailEngine on all workspace deliveries**.

---

## 4. Test Suite Summary

- **Total Tests Passing:** 14/14 automated tests (9 End-to-End & Reliability + 5 Switch Agent Protocol).
- **Demonstration:** Complete 7-step workflow verified in `demo_competition_workflow.py` in 120 seconds.
