#!/usr/bin/env python3
"""AgentHive Master Hackathon Demonstration Script.
Executes a complete, reproducible multi-agent engineering workflow:
Project Creation -> PROJECT.md -> Independent Analysis -> Switch Discussion ->
Hermes Supervision -> Human Approval -> Sandboxed Execution -> Verification -> Final Report.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agenthive.demo")

# Ensure agenthive is importable
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from agenthive.discord_gateway.bot import discord_dispatcher
from agenthive.engine.orchestrator import orchestrator
from agenthive.engine.ponytail import ponytail_guard

def print_banner(text: str):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")

async def run_master_demonstration():
    print_banner("AGENTHIVE — FLIP THE SWITCH 2026 COMPETITION DEMONSTRATION")
    print("Project: StreamGuard (Bounded Sliding-Window Metrics Engine)")
    print("Agents: ChatGPT Codex, AGY (Antigravity), Google Gemini, Hermes Supervisor")
    print("Governance: Sovereign Project Owner (Human-in-the-Loop)")
    print("Discipline: Pony Tail Minimalism (Zero Pip Packages)\n")

    start_time = time.time()
    evidence_log = {}

    # STEP 1: Project Creation
    print_banner("STEP 1: /newproject — Project Intake & PROJECT.md Generation")
    req_name = "StreamGuard"
    req_desc = (
        "A high-throughput in-memory sliding-window metrics aggregator for microservices. "
        "Must track request latencies, calculate P95/P99 percentiles over sliding time windows, "
        "and enforce strict memory bounds using only the Python standard library."
    )
    res_create = await discord_dispatcher.cmd_newproject(req_name, req_desc, user_id="po_lead_engineer")
    project_id = res_create["project_id"]
    evidence_log["step_1_create"] = res_create
    print(f"✅ Project Created: {res_create['name']} (ID: {project_id})")
    print(f"📄 Generated Workspace: {res_create['slug']}")

    # STEP 2: Independent Parallel Analysis
    print_banner("STEP 2: /analyse — Parallel Zero-Bias Independent Analysis")
    res_analyse = await discord_dispatcher.cmd_analyse(project_id)
    evidence_log["step_2_analyse"] = res_analyse
    print(f"✅ Independent proposals submitted separately by {res_analyse['analyses_count']} agents:")
    for a in res_analyse.get("summary", []):
        print(f"  • {a['agent']} [{a['complexity']} RISK]: {a['architecture'][:120]}...")

    # STEP 3: Switch Room Collaborative Debate
    print_banner("STEP 3: /discuss — Multi-Agent Switch Room Collaborative Debate")
    res_discuss = await discord_dispatcher.cmd_discuss(project_id)
    evidence_log["step_3_discuss"] = res_discuss
    print(f"✅ Switch Room debate concluded in {res_discuss['turns_completed']} bounded turns:")
    for m in res_discuss.get("messages", []):
        print(f"\n--- [Turn {m['turn']}] {m['sender']} ({m['role']}) ---")
        lines = m['content'].strip().split("\n")
        print("\n".join(lines[:6]) + ("\n..." if len(lines) > 6 else ""))

    # STEP 4: Hermes Supervision & Consensus Synthesis
    print_banner("STEP 4: /assign — Hermes Conflict Resolution & WBS Allocation")
    res_assign = await discord_dispatcher.cmd_assign(project_id)
    evidence_log["step_4_assign"] = res_assign
    print("✅ Hermes synthesized consensus and formulated capability-aware WBS:")
    print(f"Decision: {res_assign['architecture_decision'][:160]}...\n")
    for t in res_assign.get("tasks", []):
        print(f"  • [{t['task_code']}] {t['title']} -> Assigned to: {t['assigned_agent']} ({t['priority']})")

    # STEP 5: Sovereign Human Approval Gate
    print_banner("STEP 5: /approve — Sovereign Human Approval Gate")
    res_approve = await discord_dispatcher.cmd_approve(project_id)
    evidence_log["step_5_approve"] = res_approve
    print(f"✅ Sovereign Human Approval Granted by Project Owner!")
    print(f"Authorized Tasks: {', '.join(res_approve['approved_tasks'])}")

    # STEP 6: Ephemeral Sandboxed Development & Testing
    print_banner("STEP 6: /report — Sandboxed Execution & Adversarial Verification")
    res_report = await discord_dispatcher.cmd_report(project_id)
    evidence_log["step_6_report"] = res_report
    print(f"✅ Development Execution Status: {res_report['execution_status']}")
    print(f"✅ Pony Tail Zero-Dependency Compliance: {'PASSED (0 external packages)' if res_report['ponytail_passed'] else 'FAILED'}")
    print(f"✅ Adversarial Test Results: {'ALL PASSED' if res_report['test_success'] else 'FAILED'}")
    print("\n--- Test Suite Console Output ---")
    print(res_report.get("test_output", "OK"))

    # STEP 7: Audit & Verification of Delivered Artifacts
    print_banner("STEP 7: Living Documentation & Artifacts Verification")
    proj = orchestrator.get_project(project_id)
    ws_dir = Path(proj.project_md_path).parent
    delivered_files = list(ws_dir.glob("**/*.*"))
    print(f"📁 Workspace: {ws_dir}")
    print(f"📄 Master Specification: {proj.project_md_path}")
    print(f"📦 Delivered Code Files ({len(delivered_files)} files):")
    for f in delivered_files:
        if not f.name.startswith("."):
            print(f"  - {f.relative_to(ws_dir)}")

    total_duration = time.time() - start_time
    evidence_log["total_duration_sec"] = total_duration

    # Save evidence log
    evidence_file = BASE_DIR / "data" / "demo_evidence_log.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(json.dumps(evidence_log, indent=2))
    print(f"\n💾 Evidence log saved to: {evidence_file}")

    print_banner("DEMONSTRATION COMPLETED SUCCESSFULLY IN {:.2f}s".format(total_duration))
    print("🏆 AgentHive is ready for Best Business Workflow at Flip the Switch 2026!")

if __name__ == "__main__":
    asyncio.run(run_master_demonstration())
