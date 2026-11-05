# AgentHive — Development Strategy & Product Roadmap (`ROADMAP.md`)

This document outlines the phased development roadmap for **AgentHive**, contrasting the immediate **Hackathon MVP** execution plan against the long-term post-hackathon enterprise vision.

---

## 1. Hackathon MVP Strategy & Priorities

The Hackathon MVP is designed around a single guiding principle: **Validate the core multi-agent collaborative loop end-to-end with zero superfluous friction.**

```mermaid
gantt
    title AgentHive Hackathon MVP Implementation Timeline
    dateFormat  YYYY-MM-DD
    section Infrastructure
    Phase 1: Discord & Switch Setup          :done,    p1, 2026-11-04, 1d
    Phase 2: Connect Codex, AGY & Gemini     :active,  p2, after p1, 1d
    section Core Loop
    Phase 3: Shared PROJECT.md & Analysis    :         p3, after p2, 1d
    Phase 4: Agent Discussions in Switch     :         p4, after p3, 1d
    section Governance & Exec
    Phase 5: Hermes Supervision & WBS        :         p5, after p4, 1d
    Phase 6: Human Approval & Sandboxing     :         p6, after p5, 1d
    Phase 7: Demo, Packaging & Report        :         p7, after p6, 1d
```

---

### Detailed Hackathon Phases

#### Phase 1: Discord and Switch Setup (Foundations)
- **Goal:** Establish the communication backbone connecting Discord to the local Switch engine.
- **Key Deliverables:**
  - `docker-compose.yml` spinning up Switch Core (`sandbox-quantum/switch`) and local SQLite DB.
  - Discord Bot registered with Message Content and Slash Command intents.
  - Working `/agenthive create` command that creates a dedicated Discord project thread and binds it to a Switch Room.

#### Phase 2: Connect Codex, AGY, and Gemini (Agent Adapters)
- **Goal:** Enable the three specialist agents to ingest room context and emit typed responses.
- **Key Deliverables:**
  - Custom async Python adapters for OpenAI (`gpt-4o` / Codex), Antigravity CLI (`agy`), and Google GenAI (`gemini-1.5-pro`).
  - Webhook identity mapping rendering unique avatars and names for each agent in Discord.

#### Phase 3: Shared `PROJECT.md` & Independent Analysis
- **Goal:** Eliminate groupthink through isolated, parallel review.
- **Key Deliverables:**
  - Automated `PROJECT.md` generator populating project constraints from `PROJECT_TEMPLATE.md`.
  - Parallel invocation of Codex, AGY, and Gemini in isolation.
  - Structured analysis storage in SQLite.

#### Phase 4: Agent Discussions in Switch Room
- **Goal:** Enable dynamic peer debate, architectural defense, and cross-examination.
- **Key Deliverables:**
  - Switch Room message distributor managing turn order (Codex opening -> AGY review -> Gemini challenge).
  - Live mirroring of agent debate turns into the project's Discord war room thread.

#### Phase 5: Hermes Supervision & Role Assignment
- **Goal:** Moderate debates, eliminate deadlocks, and synthesize actionable tasks.
- **Key Deliverables:**
  - Nous Research Hermes daemon/CLI integration.
  - Conflict detection engine triggering when contradictory proposals arise.
  - Automated Work Breakdown Structure (WBS) generator assigning tasks to specific agents.

#### Phase 6: Human Approval Gate & Sandboxed Task Execution
- **Goal:** Maintain human sovereignty and run approved code safely under Pony Tail discipline.
- **Key Deliverables:**
  - Discord Interactive Approval embed with `Approve`, `Request Revisions`, and `Abort` buttons.
  - Ephemeral Docker sandbox runner mounting project directories with `network_mode: none` and dropped capabilities.
  - Pony Tail prompt constraints enforcing zero unnecessary external dependencies.
  - Automated execution of Gemini's test suite inside the container.

#### Phase 7: Final Demonstration & Retrospective Documentation
- **Goal:** Package, polish, and prove the complete system in action.
- **Key Deliverables:**
  - Working end-to-end demo: Building an in-memory TTL cache from a single Discord prompt.
  - Automated updates to `PROJECT.md` logging passed tests, diffs, and execution times.
  - Delivery of final artifacts and retrospective summary to Discord.

---

## 2. MVP Scope Boundary Matrix

To maintain focus and avoid scope creep during hackathon development, features are explicitly classified as **In-Scope (MVP)** vs **Deferred (Post-MVP)**:

| Feature Area | In-Scope for Hackathon MVP | Deferred to Post-MVP |
|---|---|---|
| **User Interface** | Discord Slash Commands, Threads, Buttons & Modals | Standalone React / Next.js Web Dashboard |
| **Agent Roster** | Codex, AGY, Gemini, Hermes | Dynamic Agent Marketplace (Add custom agent via UI) |
| **Persistence** | SQLite with WAL mode + Git files | Multi-node PostgreSQL with pgvector indexing |
| **Execution Sandbox** | Docker Engine with `cap-drop: ALL` | Firecracker microVMs or gVisor sandboxes |
| **Git Automation** | Local Git repository commits | Automated GitHub PR creation & CI/CD webhook hooks |
| **Pony Tail Skill** | Prompt injection + Standard Library whitelist | Static AST static analyzer enforcing LOC quotas |
| **Multi-Tenancy** | Single Discord Guild / Single Active Project | Multi-tenant SaaS with billing & quota tiers |

---

## 3. Post-Hackathon Future Horizons

### Horizon 1: Agent Marketplace & Dynamic Swarms
- Allow project owners to select specialized agents from a community registry (e.g. Security Auditor agent, Frontend UI Tailwind specialist, Rust performance tuner).
- Support for on-the-fly agent spawning based on task requirements.

### Horizon 2: GitHub & GitLab Native Lifecycle Integration
- Bi-directional sync with GitHub Issues and Pull Requests:
  - Creating a GitHub Issue automatically triggers an AgentHive war room.
  - Approved task execution automatically opens a verified PR with test coverage reports.

### Horizon 3: Multi-Modal Code & UI Prototyping
- Integration of visual layout review tools: AGY and Codex generate UI code; an automated headless browser takes screenshots and feeds them to Gemini Vision for visual regression critiques.

### Horizon 4: Enterprise Compliance & Switch Trust Deepening
- Full integration with SandboxAQ Switch Trust for automated enterprise compliance checks, software bill of materials (SBOM) generation, and license compatibility verification.
