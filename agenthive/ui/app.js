let currentProjectId = null;
let currentProject = null;
let dashboardCsrfToken = null;
let dashboardPollingStarted = false;

document.addEventListener("DOMContentLoaded", () => {
    restoreDashboardSession();
});

async function restoreDashboardSession() {
    try {
        const response = await fetch("/api/auth/session", { credentials: "same-origin", cache: "no-store" });
        const session = await response.json();
        if (session.authenticated && session.csrf_token) {
            dashboardCsrfToken = session.csrf_token;
            enterDashboard();
        }
    } catch (error) {
        console.error("Dashboard session check failed.", error);
    }
}

async function loginDashboard(event) {
    event.preventDefault();
    const input = document.getElementById("dashboard-login-token");
    const button = document.getElementById("dashboard-login-button");
    const error = document.getElementById("dashboard-auth-error");
    const credential = input.value;
    input.value = "";
    button.disabled = true;
    error.textContent = "";
    try {
        const response = await fetch("/api/auth/session", {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: credential }),
        });
        const result = await response.json();
        if (!response.ok || !result.authenticated || !result.csrf_token) {
            throw new Error(result.detail || `Sign in failed (${response.status})`);
        }
        dashboardCsrfToken = result.csrf_token;
        enterDashboard();
    } catch (exception) {
        error.textContent = exception.message || "Sign in failed.";
        input.focus();
    } finally {
        button.disabled = false;
    }
}

function enterDashboard() {
    document.getElementById("dashboard-auth-screen").hidden = true;
    document.getElementById("app-shell").hidden = false;
    fetchStatus();
    loadProjects();
    if (!dashboardPollingStarted) {
        dashboardPollingStarted = true;
        setInterval(fetchStatus, 4000);
        setInterval(() => { if (currentProjectId) refreshCurrentProject(); }, 4000);
        setInterval(loadProjects, 12000);
    }
}

function lockDashboard() {
    dashboardCsrfToken = null;
    currentProjectId = null;
    currentProject = null;
    document.getElementById("app-shell").hidden = true;
    document.getElementById("dashboard-auth-screen").hidden = false;
}

async function logoutDashboard() {
    try {
        await fetch("/api/auth/session", {
            method: "DELETE",
            credentials: "same-origin",
            headers: { "X-CSRF-Token": dashboardCsrfToken || "" },
        });
    } finally {
        lockDashboard();
    }
}

async function apiFetch(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && dashboardCsrfToken) {
        headers.set("X-CSRF-Token", dashboardCsrfToken);
    }
    const response = await fetch(url, { ...options, method, headers, credentials: "same-origin", cache: "no-store" });
    if (response.status === 401) lockDashboard();
    return response;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[ch]);
}

async function fetchStatus() {
    try {
        const res = await apiFetch("/api/status");
        if (!res.ok) throw new Error(`Status request failed (${res.status})`);
        const data = await res.json();
        const healthBadge = document.getElementById("system-health-badge");
        if (healthBadge) {
            const healthy = data.status === "healthy";
            healthBadge.innerHTML = `<span class="dot ${healthy ? 'green' : ''}"></span><span>AgentHive: <strong>${healthy ? 'HEALTHY' : 'DEGRADED'}</strong></span>`;
        }
        const switchBadge = document.getElementById("switch-status-badge");
        if (switchBadge) {
            const sw = data.switch_core || {};
            const ok = sw.status === "online";
            const rooms = sw.rooms_visible == null ? "visible room count unknown" : `${sw.rooms_visible} rooms visible`;
            switchBadge.innerHTML = `<span class="dot ${ok ? 'green pulse' : ''}"></span><span>Switch Core: <strong>${escapeHtml(ok ? 'ONLINE' : 'DEGRADED')}</strong> · ${escapeHtml(sw.mode || 'unknown')} · ${escapeHtml(rooms)}</span>`;
        }
        const dockerBadge = document.getElementById("docker-status-badge");
        if (dockerBadge) {
            const docker = data.docker || {};
            const ok = docker.status === "online";
            dockerBadge.innerHTML = `<span class="dot ${ok ? 'green' : ''}"></span><span>Docker: <strong>${escapeHtml((docker.status || 'unknown').toUpperCase())}</strong>${docker.version ? ` · ${escapeHtml(docker.version)}` : ''}</span>`;
        }
        const runnerBadge = document.getElementById("task-runner-status-badge");
        if (runnerBadge) {
            const runner = data.task_execution || {};
            const ready = runner.status === "ready";
            runnerBadge.title = runner.reason || "Secure runner status";
            runnerBadge.innerHTML = `<span class="dot ${ready ? 'green' : ''}"></span><span>Task runner: <strong>${escapeHtml((runner.status || 'unknown').toUpperCase())}</strong></span>`;
        }
        renderAgentRoster(data.agents || []);
        const ponytailBadge = document.getElementById("ponytail-mode-badge");
        if (ponytailBadge) ponytailBadge.textContent = `Policy: ${data.ponytail?.mode || 'unknown'}`;
        const maxLines = document.getElementById("ponytail-max-lines");
        if (maxLines) maxLines.textContent = data.ponytail?.max_diff_lines ?? "—";
        if (data.wispr_flow) {
            const wisprBadge = document.getElementById("wispr-status-badge");
            if (wisprBadge) {
                const state = data.wispr_flow.installed ? "READY" : "UNAVAILABLE";
                wisprBadge.innerHTML = `<span class="dot ${data.wispr_flow.installed ? 'green' : ''}"></span><span>Wispr Voice: <strong>${state}</strong></span>`;
            }
        }
    } catch (e) {
        console.error("Status fetch error:", e);
    }
}

function renderAgentRoster(agents) {
    const roster = document.getElementById("agent-roster");
    if (!roster) return;
    const icons = {"agent-codex": "💻", "agent-agy": "🚀", "agent-gemini": "🧠", "agent-hermes": "👑"};
    roster.innerHTML = agents.map(agent => {
        const connected = agent.switch_connected === true;
        const badgeClass = connected ? "badge-online" : "badge-supervisor";
        const badge = connected ? "Switch connected" : "Switch disconnected";
        return `<div class="agent-card">
            <div class="agent-avatar">${icons[agent.id] || "🤖"}</div>
            <div class="agent-info">
                <div class="agent-name">${escapeHtml(agent.name)}</div>
                <div class="agent-role">${escapeHtml(agent.runtime_mode)} · ${escapeHtml(agent.switch_transport)}</div>
            </div>
            <span class="badge ${badgeClass}">${badge}</span>
        </div>`;
    }).join("") || `<div class="empty-msg">No agent runtime state available.</div>`;
}

async function loadProjects() {
    try {
        const res = await apiFetch("/api/projects");
        if (!res.ok) throw new Error(`Project list request failed (${res.status})`);
        const data = await res.json();
        const list = document.getElementById("project-list");
        if (!data.projects || data.projects.length === 0) {
            list.innerHTML = `<div class="empty-msg" style="padding: 10px; font-size: 12px; color: #8fa0c0;">No projects yet. Click "+ New Project" above.</div>`;
            return;
        }

        list.innerHTML = data.projects.map(p => `
            <div class="project-item ${p.id === currentProjectId ? 'active' : ''}" onclick="selectProject('${escapeHtml(p.id)}')">
                <div class="project-item-title">${escapeHtml(p.name)}</div>
                <div class="project-item-meta">
                    <span class="badge ${p.current_state === 'COMPLETED' ? 'badge-online' : (p.current_state === 'AWAITING_APPROVAL' ? 'badge-supervisor' : 'badge-purple')}">${escapeHtml(p.current_state)}</span>
                    <span style="font-size: 10px; color: #566785;">${escapeHtml((p.created_at || '').substring(0, 10))}</span>
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
        const res = await apiFetch(`/api/projects/${projectId}`);
        if (!res.ok) throw new Error(`Project request failed (${res.status})`);
        const data = await res.json();
        currentProject = data;

        document.getElementById("active-project-title").innerText = data.name;
        document.getElementById("active-project-desc").innerText = `State: ${data.state} | Project ID: ${data.project_id} | Switch: ${data.discussion_transport || "not started"}`;
        document.getElementById("workflow-controls").style.display = "flex";

        updatePipelineSteps(data.state, data.approval);
        await loadProjectDetails(projectId);
        loadProjects(); // refresh active highlight
    } catch (e) {
        console.error("Select project error:", e);
    }
}

async function refreshCurrentProject() {
    if (!currentProjectId) return;
    try {
        const response = await apiFetch("/api/projects/" + currentProjectId);
        if (!response.ok) return;
        currentProject = await response.json();
        document.getElementById("active-project-desc").innerText = "State: " + currentProject.state + " | Project ID: " + currentProject.project_id + " | Switch: " + (currentProject.discussion_transport || "not started");
        updatePipelineSteps(currentProject.state, currentProject.approval);
        await loadProjectDetails(currentProjectId);
    } catch (e) {
        console.error("Project refresh error:", e);
    }
}

function updatePipelineSteps(state, approval = {}) {
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
    const approvedCount = approval.approved_count ?? 0;
    const taskCount = approval.task_count ?? 0;
    const approveButton = document.getElementById("btn-approve");
    const executeButton = document.getElementById("btn-execute");
    if (approveButton) approveButton.disabled = state !== "AWAITING_APPROVAL" || taskCount === 0;
    if (executeButton) executeButton.disabled = state !== "APPROVED" || approvedCount === 0 || approvedCount !== taskCount;
    if (state === "AWAITING_APPROVAL") {
        banner.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #f59e0b;">⚠️ <strong>OWNER APPROVAL REQUIRED:</strong> ${approvedCount} of ${taskCount} tasks have approval recorded.</span>
                <button class="btn btn-warning" onclick="triggerApprove()" style="padding: 4px 12px; font-size: 12px;">✅ Approve Plan</button>
            </div>
        `;
    } else if (state === "APPROVED") {
        banner.innerHTML = `<span style="color: #10b981;">✅ Owner approval recorded for ${approvedCount} of ${taskCount} tasks. Execution has not started.</span>`;
    } else if (state === "EXECUTING") {
        banner.innerHTML = `<span style="color: #f59e0b;">Execution is in progress. Results will appear as the backend records them.</span>`;
    } else if (state === "COMPLETED") {
        banner.innerHTML = `<span style="color: #10b981;">Project completed. Review the recorded test and compliance evidence.</span>`;
    } else if (state === "FAILED" || state === "ABORTED") {
        banner.innerHTML = `<span style="color: #f87171;">Project state: ${escapeHtml(state)}. Review the execution evidence and report.</span>`;
    } else {
        banner.innerHTML = `<span>Approval state: no approval request is recorded for this project yet.</span>`;
    }
}

async function loadProjectDetails(projectId) {
    if (!currentProject) return;
    const roomLabel = document.getElementById("room-name-lbl");
    const roomStatus = document.getElementById("switch-room-status");
    const chat = document.getElementById("chat-messages-container");
    roomLabel.textContent = currentProject.switch_room || "No room recorded";
    roomStatus.textContent = "Switch room: " + (currentProject.discussion_transport || "not started");

    const messages = currentProject.discussion_messages || [];
    if (messages.length) {
        chat.innerHTML = messages.map(m => {
            const name = String(m.sender_name || "Agent");
            const icon = name.includes("Codex") ? "💻" : (name.includes("AGY") ? "🚀" : (name.includes("Gemini") ? "🧠" : "👑"));
            const event = m.switch_event_id ? " · Switch event " + escapeHtml(m.switch_event_id) : "";
            return "<div class=\"chat-msg\"><div class=\"chat-msg-header\"><span class=\"chat-msg-sender\">" + icon + " " + escapeHtml(name) + "</span><span class=\"badge " + (m.sender_role === "SUPERVISOR" ? "badge-supervisor" : "badge-online") + "\">" + escapeHtml(m.sender_role) + "</span></div><div class=\"chat-msg-content\">" + escapeHtml(m.content).replace(/\n/g, "<br>") + "</div><small>Turn " + escapeHtml(m.turn_index) + event + "</small></div>";
        }).join("");
    } else {
        chat.innerHTML = "<div class=\"empty-msg\">No persisted discussion messages for this project.</div>";
    }

    if (currentProject.analyses && currentProject.analyses.length) {
        renderIndependentProposals(currentProject.analyses);
    }
    if (currentProject.tasks && currentProject.tasks.length) {
        renderSupervision({
            architecture_decision: currentProject.supervision_architecture,
            supervisor_runtime: currentProject.supervisor_runtime,
            approval: currentProject.approval,
            tasks: currentProject.tasks,
        });
    }
    renderExecutionLogs(currentProject.execution_logs || []);
    const md = document.getElementById("project-md-viewer");
    if (md) md.textContent = currentProject.project_md || "No PROJECT.md content is available.";
}

function renderExecutionLogs(logs) {
    const output = document.getElementById("terminal-output");
    const badge = document.getElementById("test-exit-code-badge");
    if (!logs.length) {
        output.textContent = "No execution or test results have been persisted for this project.";
        badge.textContent = "EXIT: —";
        return;
    }
    const latest = logs[logs.length - 1];
    let latestAudit = null;
    for (const log of logs) {
        try {
            const evidence = JSON.parse(log.diff_patch || "{}");
            if (evidence.ponytail_audit) latestAudit = evidence.ponytail_audit;
        } catch (_) {}
    }
    if (latestAudit) {
        const modules = new Set((latestAudit.details || []).flatMap(item => item.unauthorized_modules || []));
        document.getElementById("ponytail-packages").textContent = String(modules.size);
        document.getElementById("ponytail-compliance").textContent = latestAudit.passed ? "PASSED" : "FAILED";
    }
    badge.textContent = latest.container_id === "agenthive-test-runner" ? "EXIT: " + (latest.exit_code ?? "—") : "LATEST TASK: " + (latest.task_code || "—");
    output.textContent = logs.map(log => {
        let body = log.stdout || "";
        if (log.container_id !== "agenthive-test-runner") {
            try {
                const data = JSON.parse(body);
                body = data.report || data.execution_mode || body;
            } catch (_) {}
        }
        return "[" + (log.task_code || "test run") + "] exit=" + (log.exit_code ?? "—") + "\n" + body + (log.stderr ? "\nSTDERR:\n" + log.stderr : "");
    }).join("\n\n---\n\n");
}

// Workflow action buttons
async function triggerAnalyse() {
    if (!currentProjectId) return;
    const btn = document.getElementById("btn-analyse");
    btn.innerText = "Analyzing in Parallel...";
    try {
        const res = await apiFetch(`/api/projects/${currentProjectId}/analyse`, { method: "POST" });
        const data = await res.json();
        if (!res.ok || data.success === false) throw new Error(data.error || `Analysis failed (${res.status})`);
        alert(`Independent analysis recorded for ${data.analyses_count} agents.`);
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
    container.innerHTML = summary.map(s => {
        const name = String(s.agent || s.agent_name || "Agent");
        const icon = name.includes("Codex") ? "💻" : (name.includes("AGY") ? "🚀" : (name.includes("Gemini") ? "🧠" : "👑"));
        const stack = Array.isArray(s.tech_stack) ? s.tech_stack.join(", ") : (s.tech_stack || "");
        return "<div class=\"proposal-card\"><div style=\"display:flex;justify-content:space-between;align-items:center;margin-bottom:8px\"><span class=\"proposal-agent-name\">" + icon + " " + escapeHtml(name) + "</span><span class=\"badge badge-purple\">" + escapeHtml(s.complexity || "unknown") + " RISK</span></div><div class=\"proposal-item\"><span class=\"proposal-item-lbl\">Suggested Architecture:</span><p style=\"margin-top:4px;color:#f0f4fc;font-size:13px\">" + escapeHtml(s.architecture || "No proposal recorded") + "</p></div><div class=\"proposal-item\"><span class=\"proposal-item-lbl\">Tech Stack:</span><p style=\"margin-top:4px;color:#10b981;font-family:var(--font-mono);font-size:12px\">" + escapeHtml(stack) + "</p></div></div>";
    }).join("");
}

async function triggerDiscuss() {
    if (!currentProjectId) return;
    const btn = document.getElementById("btn-discuss");
    btn.innerText = "Debate in Progress...";
    try {
        const res = await apiFetch(`/api/projects/${currentProjectId}/discuss`, { method: "POST" });
        const data = await res.json();
        if (!res.ok || data.success === false) throw new Error(data.error || `Discussion failed (${res.status})`);
        alert(`Discussion completed in ${data.switch_transport || "unknown"} transport across ${data.turns_completed} turns.`);
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
        const res = await apiFetch(`/api/projects/${currentProjectId}/assign`, { method: "POST" });
        const data = await res.json();
        if (!res.ok || data.success === false) throw new Error(data.error || data.detail || `Task proposal failed (${res.status})`);
        const supervisorMode = data.supervisor_runtime?.runtime_mode || "unknown supervisor runtime";
        alert(`Task proposal recorded (${supervisorMode}); ${data.tasks.length} tasks require owner review.`);
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
    const runtimeMode = data.supervisor_runtime?.runtime_mode || "Supervision runtime not verified";
    const architecture = data.architecture_decision || "No architecture decision has been persisted.";
    const approval = data.approval || currentProject?.approval || {};
    const sources = data.discussion_sources || currentProject?.discussion_sources || [];
    const approvalButton = approval.state === "AWAITING_APPROVAL"
        ? "<button class=\"btn btn-warning\" onclick=\"triggerApprove()\" style=\"font-size:12px;padding:4px 12px\">Approve Plan</button>"
        : "<span class=\"badge badge-purple\">" + escapeHtml(approval.state || "approval state unknown") + "</span>";
    container.innerHTML = `
        <div class="dash-card" style="margin-bottom: 20px;">
            <div class="dash-card-header">
                <h3>👑 Supervisor Architecture & Arbitration</h3>
                <span class="badge badge-supervisor">${escapeHtml(runtimeMode)}</span>
            </div>
            <pre style="white-space: pre-wrap; font-family: var(--font-mono); font-size: 13px; color: #a5f3fc; line-height: 1.6;">${escapeHtml(architecture)}</pre>
            <h4>Linked discussion evidence</h4>
            <ul>${sources.length ? sources.map(source => `<li>Turn ${escapeHtml(source.turn_index)} · ${escapeHtml(source.sender_name)} · event ${escapeHtml(source.switch_event_id || 'unavailable')} · message ${escapeHtml(source.switch_message_id || 'unavailable')}</li>`).join("") : "<li>No persisted discussion sources.</li>"}</ul>
        </div>
        <div class="dash-card">
            <div class="dash-card-header">
                <h3>Work Breakdown Structure (WBS) & Role Assignments</h3>
                ${approvalButton}
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
                            <td style="padding: 8px; font-family: var(--font-mono);">${escapeHtml(t.task_code)}</td>
                            <td style="padding: 8px;">${escapeHtml(t.title)}</td>
                            <td style="padding: 8px; font-weight: 700; color: var(--accent-hover);">${escapeHtml(t.assigned_agent)}</td>
                            <td style="padding: 8px;"><span class="badge badge-purple">${escapeHtml(t.priority)}</span></td>
                            <td style="padding: 8px;"><span class="badge ${t.status === 'VERIFIED' ? 'badge-online' : 'badge-supervisor'}">${escapeHtml(t.status)}</span></td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}

async function triggerApprove() {
    if (!currentProjectId || !window.confirm("Record owner approval for this plan? This action will not execute tasks.")) return;
    try {
        const response = await apiFetch(`/api/projects/${currentProjectId}/approve`, { method: "POST" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `Approval failed (${response.status})`);
        alert(result.message || "Owner approval recorded. Execution remains a separate action.");
        await selectProject(currentProjectId);
    } catch (error) {
        alert("Approval was not recorded: " + (error.message || error));
    }
}

async function triggerExecute() {
    if (!currentProjectId || !window.confirm("Start the approved task execution and verification now?")) return;
    try {
        const response = await apiFetch(`/api/projects/${currentProjectId}/execute`, { method: "POST" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `Execution failed (${response.status})`);
        alert(result.message || "Execution finished. Review the persisted output and test results.");
        await selectProject(currentProjectId);
        switchTab("tab-execution");
    } catch (error) {
        alert("Execution did not complete: " + (error.message || error));
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
        const res = await apiFetch("/api/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, description })
        });
        const data = await res.json();
        if (!res.ok || data.success === false || !data.project_id) throw new Error(data.error || data.detail || `Project creation failed (${res.status})`);
        closeNewProjectModal();
        await loadProjects();
        await selectProject(data.project_id);
        alert(`🐝 Project '${data.name}' initialized! Click '1. Run Independent Analysis' to begin.`);
    } catch (e) {
        alert("Failed to create project: " + e);
    }
}
