let currentProjectId = null;
let currentProject = null;

document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();
    loadProjects();
    // Poll every 4s for real-time updates
    setInterval(fetchStatus, 4000);
});

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        if (data.switch_core && data.switch_core.status === "online") {
            const badge = document.getElementById("switch-status-badge");
            if (badge) {
                badge.innerHTML = `<span class="dot pulse"></span><span>Switch Core: <strong>ONLINE (${data.switch_core.active_rooms} Rooms)</strong></span>`;
            }
        }
        if (data.wispr_flow) {
            const wisprBadge = document.getElementById("wispr-status-badge");
            if (wisprBadge && data.wispr_flow.installed) {
                wisprBadge.innerHTML = `<span class="dot green"></span><span>Wispr Voice: <strong>READY</strong></span>`;
            }
        }
    } catch (e) {
        console.error("Status fetch error:", e);
    }
}

async function loadProjects() {
    try {
        const res = await fetch("/api/projects");
        const data = await res.json();
        const list = document.getElementById("project-list");
        if (!data.projects || data.projects.length === 0) {
            list.innerHTML = `<div class="empty-msg" style="padding: 10px; font-size: 12px; color: #8fa0c0;">No projects yet. Click "+ New Project" above.</div>`;
            return;
        }

        list.innerHTML = data.projects.map(p => `
            <div class="project-item ${p.id === currentProjectId ? 'active' : ''}" onclick="selectProject('${p.id}')">
                <div class="project-item-title">${p.name}</div>
                <div class="project-item-meta">
                    <span class="badge ${p.current_state === 'COMPLETED' ? 'badge-online' : (p.current_state === 'AWAITING_APPROVAL' ? 'badge-supervisor' : 'badge-purple')}">${p.current_state}</span>
                    <span style="font-size: 10px; color: #566785;">${(p.created_at || '').substring(0, 10)}</span>
                </div>
            </div>
        `).join("");

        // Auto-select first project if none selected
        if (!currentProjectId && data.projects.length > 0) {
            selectProject(data.projects[0].id);
        }
    } catch (e) {
        console.error("Load projects error:", e);
    }
}

async function selectProject(projectId) {
    currentProjectId = projectId;
    try {
        const res = await fetch(`/api/projects/${projectId}`);
        const data = await res.json();
        currentProject = data;

        document.getElementById("active-project-title").innerText = data.name;
        document.getElementById("active-project-desc").innerText = `State: ${data.state} | Project ID: ${data.project_id}`;
        document.getElementById("workflow-controls").style.display = "flex";

        updatePipelineSteps(data.state);
        loadProjectDetails(projectId);
        loadProjects(); // refresh active highlight
    } catch (e) {
        console.error("Select project error:", e);
    }
}

function updatePipelineSteps(state) {
    const states = ["DRAFT", "ANALYZING", "DISCUSSING", "AWAITING_APPROVAL", "APPROVED", "EXECUTING", "COMPLETED"];
    const stepIdx = states.indexOf(state);

    for (let i = 0; i <= 5; i++) {
        const el = document.getElementById(`step-${i}`);
        if (!el) continue;
        if (stepIdx > i) {
            el.className = "pipeline-step completed";
            el.querySelector(".step-status").innerText = "Completed";
        } else if (stepIdx === i) {
            el.className = "pipeline-step active";
            el.querySelector(".step-status").innerText = "In Progress";
        } else {
            el.className = "pipeline-step";
            el.querySelector(".step-status").innerText = "Pending";
        }
    }

    const banner = document.getElementById("human-gate-banner");
    if (state === "AWAITING_APPROVAL") {
        banner.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f59e0b;">⚠️ <strong>ACTION REQUIRED:</strong> Hermes formulated the WBS. Human signoff required.</span>
                <button class="btn btn-warning" onclick="triggerApprove()" style="padding: 4px 12px; font-size: 12px;">✅ Approve All Tasks</button>
            </div>
        `;
    } else if (state === "APPROVED" || state === "EXECUTING" || state === "COMPLETED") {
        banner.innerHTML = `<span style="color: #10b981;">✅ <strong>AUTHORIZED:</strong> Sovereign human approval granted. Tasks dispatched to sandboxed runner.</span>`;
    } else {
        banner.innerHTML = `<span>Status: No pending approval requests.</span>`;
    }
}

async function loadProjectDetails(projectId) {
    // 1. Fetch Discussion Messages from Switch
    try {
        const roomLbl = document.getElementById("room-name-lbl");
        const chatContainer = document.getElementById("chat-messages-container");
        if (currentProject.switch_room) {
            roomLbl.innerText = currentProject.switch_room;
            const res = await fetch(`/switch/api/v1/rooms/${currentProject.switch_room}/messages`);
            const roomData = await res.json();
            if (roomData.messages && roomData.messages.length > 0) {
                chatContainer.innerHTML = roomData.messages.map(m => `
                    <div class="chat-msg">
                        <div class="chat-msg-header">
                            <span class="chat-msg-sender">
                                ${m.sender_name === 'ChatGPT Codex' ? '💻 ' : (m.sender_name.includes('AGY') ? '🚀 ' : (m.sender_name.includes('Gemini') ? '🧠 ' : '👑 '))}
                                ${m.sender_name}
                            </span>
                            <span class="badge ${m.sender_role === 'SUPERVISOR' ? 'badge-supervisor' : 'badge-online'}">${m.sender_role}</span>
                        </div>
                        <div class="chat-msg-content">${m.content}</div>
                    </div>
                `).join("");
            } else {
                chatContainer.innerHTML = `<div class="empty-msg">No discussion messages yet. Click '2. Start Switch Debate' to begin.</div>`;
            }
        }
    } catch (e) {
        console.error("Room fetch error:", e);
    }

    // 2. Load Tasks if present
    if (currentProject && currentProject.tasks && currentProject.tasks.length > 0) {
        renderSupervision({
            architecture_decision: "Consensus Architecture: Standard Library In-Memory Ring Buffer with Inverted Tag Index and Adversarial QA.",
            tasks: currentProject.tasks
        });
    }
}

// Workflow action buttons
async function triggerAnalyse() {
    if (!currentProjectId) return;
    const btn = document.getElementById("btn-analyse");
    btn.innerText = "Analyzing in Parallel...";
    try {
        const res = await fetch(`/api/projects/${currentProjectId}/analyse`, { method: "POST" });
        const data = await res.json();
        alert(`Independent Analysis complete for all 4 agents!\nProposals stored separately.`);
        await selectProject(currentProjectId);
        switchTab("tab-independent");
        renderIndependentProposals(data.summary);
    } catch (e) {
        alert("Analysis error: " + e);
    } finally {
        btn.innerText = "1. Run Independent Analysis";
    }
}

function renderIndependentProposals(summary) {
    const container = document.getElementById("independent-grid-container");
    if (!summary || summary.length === 0) return;
    container.innerHTML = summary.map(s => `
        <div class="proposal-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span class="proposal-agent-name">
                    ${s.agent.includes('Codex') ? '💻 ' : (s.agent.includes('AGY') ? '🚀 ' : (s.agent.includes('Gemini') ? '🧠 ' : '👑 '))}
                    ${s.agent}
                </span>
                <span class="badge badge-purple">${s.complexity} RISK</span>
            </div>
            <div class="proposal-item">
                <span class="proposal-item-lbl">Suggested Architecture:</span>
                <p style="margin-top: 4px; color: #f0f4fc; font-size: 13px;">${s.architecture}</p>
            </div>
            <div class="proposal-item">
                <span class="proposal-item-lbl">Tech Stack & Dependencies:</span>
                <p style="margin-top: 4px; color: #10b981; font-family: var(--font-mono); font-size: 12px;">${Array.isArray(s.tech_stack) ? s.tech_stack.join(', ') : s.tech_stack}</p>
            </div>
        </div>
    `).join("");
}

async function triggerDiscuss() {
    if (!currentProjectId) return;
    const btn = document.getElementById("btn-discuss");
    btn.innerText = "Debate in Progress...";
    try {
        const res = await fetch(`/api/projects/${currentProjectId}/discuss`, { method: "POST" });
        const data = await res.json();
        alert(`Switch Room debate completed across ${data.turns_completed} bounded turns!`);
        await selectProject(currentProjectId);
        switchTab("tab-switch-room");
    } catch (e) {
        alert("Debate error: " + e);
    } finally {
        btn.innerText = "2. Start Switch Debate";
    }
}

async function triggerAssign() {
    if (!currentProjectId) return;
    const btn = document.getElementById("btn-assign");
    btn.innerText = "Hermes Synthesizing WBS...";
    try {
        const res = await fetch(`/api/projects/${currentProjectId}/assign`, { method: "POST" });
        const data = await res.json();
        alert(`Hermes synthesized master plan and formulated ${data.tasks.length} WBS tasks!`);
        await selectProject(currentProjectId);
        switchTab("tab-supervision");
        renderSupervision(data);
    } catch (e) {
        alert("Synthesis error: " + e);
    } finally {
        btn.innerText = "3. Hermes Synthesis & WBS";
    }
}

function renderSupervision(data) {
    const container = document.getElementById("supervision-container");
    container.innerHTML = `
        <div class="dash-card" style="margin-bottom: 20px;">
            <div class="dash-card-header">
                <h3>👑 Hermes Recommended Architecture & Arbitration</h3>
                <span class="badge badge-supervisor">ARBITRATION PASSED</span>
            </div>
            <pre style="white-space: pre-wrap; font-family: var(--font-mono); font-size: 13px; color: #a5f3fc; line-height: 1.6;">${data.architecture_decision}</pre>
        </div>
        <div class="dash-card">
            <div class="dash-card-header">
                <h3>Work Breakdown Structure (WBS) & Role Assignments</h3>
                <button class="btn btn-warning" onclick="triggerApprove()" style="font-size: 12px; padding: 4px 12px;">✅ Approve All Tasks</button>
            </div>
            <table style="width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px;">
                <thead>
                    <tr style="border-bottom: 1px solid var(--border-color); text-align: left; color: var(--text-muted);">
                        <th style="padding: 8px;">Code</th>
                        <th style="padding: 8px;">Title</th>
                        <th style="padding: 8px;">Assigned Agent</th>
                        <th style="padding: 8px;">Priority</th>
                        <th style="padding: 8px;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.tasks.map(t => `
                        <tr style="border-bottom: 1px solid var(--border-color);">
                            <td style="padding: 8px; font-family: var(--font-mono);">${t.task_code}</td>
                            <td style="padding: 8px;">${t.title}</td>
                            <td style="padding: 8px; font-weight: 700; color: var(--accent-hover);">${t.assigned_agent}</td>
                            <td style="padding: 8px;"><span class="badge badge-purple">${t.priority}</span></td>
                            <td style="padding: 8px;"><span class="badge ${t.status === 'VERIFIED' ? 'badge-online' : 'badge-supervisor'}">${t.status}</span></td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}

async function triggerApprove() {
    if (!currentProjectId) return;
    if (!confirm("Are you sure you want to grant sovereign human authorization for sandboxed task execution?")) return;
    try {
        const res = await fetch(`/api/projects/${currentProjectId}/approve`, { method: "POST" });
        const data = await res.json();
        alert(`Human approval granted! Tasks unlocked for execution: ${data.approved_tasks.join(", ")}`);
        await selectProject(currentProjectId);
    } catch (e) {
        alert("Approval failed: " + e);
    }
}

async function triggerExecute() {
    if (!currentProjectId) return;
    const btn = document.getElementById("btn-execute");
    btn.innerText = "Executing & Testing...";
    try {
        const res = await fetch(`/api/projects/${currentProjectId}/execute`, { method: "POST" });
        const data = await res.json();
        switchTab("tab-execution");
        document.getElementById("terminal-output").innerText = data.test_output || "All tests executed successfully!";
        const badge = document.getElementById("test-exit-code-badge");
        badge.innerText = `STATUS: ${data.execution_status}`;
        badge.className = data.execution_status === "COMPLETED" ? "badge badge-online" : "badge badge-purple";
        alert(`🎉 Execution finished!\nStatus: ${data.execution_status}\nPony Tail Compliant: ${data.ponytail_passed}`);
        await selectProject(currentProjectId);
    } catch (e) {
        alert("Execution failed: " + e);
    } finally {
        btn.innerText = "5. Execute & Verify";
    }
}

// UI Tabs
function switchTab(tabId) {
    document.querySelectorAll(".tab-pane").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
    const pane = document.getElementById(tabId);
    if (pane) pane.classList.add("active");
    if (event && event.currentTarget) {
        event.currentTarget.classList.add("active");
    }
}

// Modal handling
function openNewProjectModal() {
    document.getElementById("new-project-modal").style.display = "flex";
}
function closeNewProjectModal() {
    document.getElementById("new-project-modal").style.display = "none";
}
function applyPreset(name, desc) {
    document.getElementById("modal-project-name").value = name;
    document.getElementById("modal-project-desc").value = desc;
}

async function submitNewProject() {
    const name = document.getElementById("modal-project-name").value.trim();
    const description = document.getElementById("modal-project-desc").value.trim();
    if (!name || !description) {
        alert("Please provide both project name and brief.");
        return;
    }

    try {
        const res = await fetch("/api/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, description })
        });
        const data = await res.json();
        closeNewProjectModal();
        await loadProjects();
        await selectProject(data.project_id);
        alert(`🐝 Project '${data.name}' initialized! Click '1. Run Independent Analysis' to begin.`);
    } catch (e) {
        alert("Failed to create project: " + e);
    }
}
