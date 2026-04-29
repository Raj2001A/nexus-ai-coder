const API_BASE = window.location.origin;
const WS_SCHEME = window.location.protocol === "https:" ? "wss" : "ws";
const WS_BASE = `${WS_SCHEME}://${window.location.host}`;

let activeWebSocket = null;
let isProcessing = false;

document.addEventListener("DOMContentLoaded", () => {
    setupTextareaAutoResize();
    setupDropZone();
    setupKeyboardShortcuts();
    resetInspectionPanels();
    loadCollectionStats();
    loadRunHistory();
    loadAnalyticsSummary();
    loadCurrentGitPatch();
});

function sendTask() {
    const input = document.getElementById("task-input");
    const task = input.value.trim();

    if (!task || isProcessing) {
        return;
    }

    const welcome = document.getElementById("welcome-card");
    if (welcome) {
        welcome.style.display = "none";
    }

    addMessage(task, "user");
    input.value = "";
    input.style.height = "auto";

    resetPipeline();
    resetInspectionPanels();
    setProcessing(true);

    const ws = new WebSocket(`${WS_BASE}/ws/chat`);
    activeWebSocket = ws;

    ws.onopen = () => {
        updateConnectionStatus("connected", "Connected");
        ws.send(JSON.stringify({ task }));
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleWSMessage(msg);
    };

    ws.onerror = () => {
        addTraceEntry("error", "Connection error. Check that the backend is running.");
        setProcessing(false);
        updateConnectionStatus("error", "Error");
    };

    ws.onclose = () => {
        activeWebSocket = null;
        if (isProcessing) {
            setProcessing(false);
        }
        updateConnectionStatus("ready", "Ready");
    };
}

function handleWSMessage(msg) {
    switch (msg.type) {
        case "status":
            updatePipelineNode(msg.agent, "active", "Running...");
            if (msg.iteration) {
                document.getElementById("iter-value").textContent = msg.iteration;
            }
            break;

        case "result":
            updatePipelineNode(msg.agent, "completed", "Done");
            addTraceEntry(msg.agent, msg.data || "");

            if (msg.agent === "rag") {
                renderRetrievedContext(msg.items || []);
            }

            if (msg.agent === "reviewer" && msg.passed === false) {
                updatePipelineNode(msg.agent, "failed", "Retrying");
                updatePipelineNode("executor", "", "Waiting for retry...");
            }
            break;

        case "complete":
            addMessage(msg.final_answer, "agent");
            renderTrustMetrics(msg.trust_metrics || {});
            renderChangedFiles(msg.changed_files || []);
            renderVerificationRuns(msg.verification_runs || []);
            setProcessing(false);
            loadRunHistory();
            loadAnalyticsSummary();
            loadCurrentGitPatch();
            addTraceEntry(
                "system",
                `Completed in ${msg.iterations} iteration(s). ${msg.passed ? "Review approved." : "Max retries reached."}`
            );
            break;

        case "error":
            addMessage(`Error: ${msg.message}`, "agent");
            addTraceEntry("error", msg.message);
            setProcessing(false);
            break;
    }
}

async function ingestDirectory() {
    const dirInput = document.getElementById("directory-input");
    const directory = dirInput.value.trim();

    if (!directory) {
        return;
    }

    const btn = document.getElementById("ingest-btn");
    btn.disabled = true;
    btn.textContent = "Ingesting...";
    setIngestLog("Ingesting codebase...");

    try {
        const response = await fetch(`${API_BASE}/ingest/directory`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ directory, collection: "codebase", overwrite: false }),
        });
        const data = await response.json();

        if (response.ok) {
            setIngestLog("Ingestion complete.");
            updateStats(data.stats);
        } else {
            setIngestLog(`Error: ${data.detail}`);
        }
    } catch (err) {
        setIngestLog(`Connection error: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = "Ingest";
    }
}

async function uploadZip(file) {
    setIngestLog("Uploading and ingesting ZIP...");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("collection", "codebase");
    formData.append("overwrite", "false");

    try {
        const response = await fetch(`${API_BASE}/ingest/upload`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();

        if (response.ok) {
            setIngestLog("ZIP ingested successfully.");
            updateStats(data.stats);
        } else {
            setIngestLog(`Error: ${data.detail}`);
        }
    } catch (err) {
        setIngestLog(`Upload failed: ${err.message}`);
    }
}

async function loadCollectionStats() {
    try {
        const response = await fetch(`${API_BASE}/collections`);
        const data = await response.json();
        updateStats(data);
    } catch {
        // Backend may not be running yet.
    }
}

async function loadRunHistory() {
    try {
        const response = await fetch(`${API_BASE}/runs?limit=10`);
        const data = await response.json();
        renderRunHistory(data.runs || []);
    } catch {
        // Backend may not be running yet.
    }
}

async function loadAnalyticsSummary() {
    try {
        const response = await fetch(`${API_BASE}/analytics/summary?limit=25&scope=active`);
        const data = await response.json();
        renderAssistantInsights(data);
    } catch {
        // Backend may not be running yet.
    }
}

async function loadCurrentGitPatch(path = "") {
    try {
        const suffix = path ? `?path=${encodeURIComponent(path)}` : "";
        const response = await fetch(`${API_BASE}/review/git-patch${suffix}`);
        const data = await response.json();
        renderGitPatch(data);
    } catch {
        // Backend may not be running yet.
    }
}

async function loadRunDetail(runId) {
    try {
        const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
        const data = await response.json();
        renderTrustMetrics(data.trust_metrics || {});
        renderRetrievedContext(data.retrieved_context || []);
        renderChangedFiles(data.changed_files || []);
        renderVerificationRuns(data.verification_runs || []);
        addTraceEntry("system", `Loaded persisted run ${runId}.`);
    } catch (err) {
        addTraceEntry("error", `Failed to load run ${runId}: ${err.message}`);
    }
}

function addMessage(content, type) {
    const container = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = `message message-${type}`;

    if (type === "agent") {
        div.innerHTML = renderMarkdown(content);
    } else {
        div.textContent = content;
    }

    container.appendChild(div);
    scrollToBottom();
}

function renderMarkdown(text) {
    let html = escapeHtml(text);

    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
        return `<pre><code>${code}</code></pre>`;
    });
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/\n/g, "<br>");

    return html;
}

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function scrollToBottom() {
    const container = document.getElementById("chat-container");
    container.scrollTop = container.scrollHeight;
}

function setProcessing(active) {
    isProcessing = active;
    const btn = document.getElementById("send-btn");
    const input = document.getElementById("task-input");

    if (active) {
        btn.innerHTML = '<span class="spinner"></span>';
        btn.disabled = true;
        input.disabled = true;
    } else {
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>';
        btn.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

function resetPipeline() {
    const nodes = document.querySelectorAll(".pipeline-node");
    nodes.forEach((node) => {
        node.className = "pipeline-node";
        node.querySelector(".node-status").textContent = "Waiting";
    });
    document.getElementById("iter-value").textContent = "0";
    document.getElementById("trace-log").innerHTML = '<p class="trace-empty">Agent outputs will appear here.</p>';
}

function updatePipelineNode(agent, state, statusText) {
    const node = document.getElementById(`node-${agent}`);
    if (!node) {
        return;
    }

    node.classList.remove("active", "completed", "failed");
    if (state) {
        node.classList.add(state);
    }
    if (statusText) {
        node.querySelector(".node-status").textContent = statusText;
    }
}

function addTraceEntry(agent, content) {
    const log = document.getElementById("trace-log");
    const emptyMsg = log.querySelector(".trace-empty");
    if (emptyMsg) {
        emptyMsg.remove();
    }

    const entry = document.createElement("div");
    entry.className = `trace-entry trace-${agent}`;

    const text = String(content || "");
    const truncated = text.length > 500 ? `${text.substring(0, 500)}... [truncated]` : text;

    entry.innerHTML = `
        <span class="trace-agent">${escapeHtml(agent)}</span>
        ${escapeHtml(truncated).replace(/\n/g, "<br>")}
    `;

    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function updateStats(stats) {
    if (!stats) {
        return;
    }

    renderActiveProject(stats);
    document.getElementById("stat-chunks").textContent = stats.total_chunks || "0";
    document.getElementById("stat-files").textContent = (stats.sample_files || []).length || "0";

    const fileList = document.getElementById("file-list");
    const sampleFiles = stats.sample_files || [];
    fileList.innerHTML = "";

    if (!sampleFiles.length) {
        fileList.innerHTML = '<p class="panel-empty">No indexed files yet.</p>';
        return;
    }

    sampleFiles.forEach((filePath) => {
        const div = document.createElement("div");
        div.className = "file-list-item";
        div.textContent = filePath;
        fileList.appendChild(div);
    });
}

function renderActiveProject(stats) {
    document.getElementById("project-name").textContent = stats.active_project_name || "No active project";
    document.getElementById("project-path").textContent = stats.active_project_dir || "Ingest a directory or ZIP to begin.";
    document.getElementById("project-source").textContent = stats.active_project_source || "-";
    document.getElementById("project-collection").textContent = stats.active_collection || "-";
}

function resetInspectionPanels() {
    renderTrustMetrics({});
    renderRetrievedContext([]);
    renderChangedFiles([]);
    renderVerificationRuns([]);
    renderGitPatch({});
}

function renderTrustMetrics(metrics) {
    const container = document.getElementById("trust-metrics");
    container.innerHTML = "";

    const entries = [
        ["Retrieved", metrics.retrieved_chunks],
        ["Changed", metrics.changed_files],
        ["Verified", metrics.verification_total],
        ["Passed", metrics.verification_passed],
        ["Failed", metrics.verification_failed],
        ["Iterations", metrics.iterations],
        ["Git", metrics.git_available ? (metrics.git_branch || "repo") : "none"],
        ["Dirty", metrics.git_dirty_files],
    ].filter(([, value]) => value !== undefined && value !== null);

    if (!entries.length) {
        container.innerHTML = '<p class="panel-empty">No trust metrics available yet.</p>';
        return;
    }

    entries.forEach(([label, value]) => {
        const card = document.createElement("div");
        card.className = "metric-card";
        card.innerHTML = `
            <span class="metric-value">${escapeHtml(String(value))}</span>
            <span class="metric-label">${escapeHtml(label)}</span>
        `;
        container.appendChild(card);
    });
}

function renderRetrievedContext(items) {
    const container = document.getElementById("retrieval-list");
    container.innerHTML = "";

    if (!items.length) {
        container.innerHTML = '<p class="panel-empty">No retrieved context yet.</p>';
        return;
    }

    items.forEach((item) => {
        const block = document.createElement("div");
        block.className = "inspection-item";
        block.innerHTML = `
            <div class="inspection-head">
                <span class="inspection-path">${escapeHtml(item.file_path || "unknown")}</span>
                <span class="inspection-meta">${escapeHtml((item.language || "text").toUpperCase())}</span>
            </div>
            <div class="inspection-subhead">Chunk ${escapeHtml(String(item.chunk_index))} / ${escapeHtml(String(item.total_chunks))}</div>
            <pre class="inspection-preview"><code>${escapeHtml(item.preview || "")}</code></pre>
        `;
        container.appendChild(block);
    });
}

function renderChangedFiles(files) {
    const container = document.getElementById("changes-list");
    container.innerHTML = "";

    if (!files.length) {
        container.innerHTML = '<p class="panel-empty">No file changes recorded for this run.</p>';
        return;
    }

    files.forEach((file) => {
        const wrapper = document.createElement("details");
        wrapper.className = "inspection-item inspection-item-detail";

        const diffContent = file.diff_preview
            ? `<pre class="inspection-preview"><code>${escapeHtml(file.diff_preview)}</code></pre>`
            : '<p class="inspection-note">No text diff available for this file.</p>';

        const gitSummary = file.git_diff_summary
            ? `${escapeHtml(String(file.git_diff_summary.insertions ?? "-"))} / ${escapeHtml(String(file.git_diff_summary.deletions ?? "-"))}`
            : null;

        wrapper.innerHTML = `
            <summary class="inspection-summary">
                <span class="inspection-path">${escapeHtml(file.path)}</span>
                <span class="inspection-badges">
                    <span class="status-pill status-${escapeHtml(file.status)}">${escapeHtml(file.status)}</span>
                    <span class="inspection-meta">${escapeHtml((file.language || "file").toUpperCase())}</span>
                    ${file.git_status ? `<span class="inspection-meta">${escapeHtml(file.git_status)}</span>` : ""}
                </span>
            </summary>
            <div class="inspection-subhead">${escapeHtml(String(file.size_bytes || 0))} bytes${gitSummary ? ` · git +/${gitSummary}` : ""}</div>
            ${diffContent}
        `;
        container.appendChild(wrapper);
    });
}

function renderVerificationRuns(runs) {
    const container = document.getElementById("verification-list");
    container.innerHTML = "";

    if (!runs.length) {
        container.innerHTML = '<p class="panel-empty">No verification runs recorded for this run.</p>';
        return;
    }

    runs.forEach((run) => {
        const wrapper = document.createElement("details");
        wrapper.className = "inspection-item inspection-item-detail";

        const outputParts = [];
        if (run.stdout) {
            outputParts.push(`<div class="inspection-subhead">STDOUT</div><pre class="inspection-preview"><code>${escapeHtml(run.stdout)}</code></pre>`);
        }
        if (run.stderr) {
            outputParts.push(`<div class="inspection-subhead">STDERR</div><pre class="inspection-preview"><code>${escapeHtml(run.stderr)}</code></pre>`);
        }
        if (!outputParts.length) {
            outputParts.push('<p class="inspection-note">No output captured.</p>');
        }

        const runtimeLabel = run.runtime ? String(run.runtime).toUpperCase() : (run.kind || "run").toUpperCase();
        const statusClass = run.success ? "status-created" : "status-deleted";
        const statusLabel = run.success ? "passed" : "failed";
        const classification = run.classification ? `<span class="inspection-meta">${escapeHtml(String(run.classification))}</span>` : "";

        wrapper.innerHTML = `
            <summary class="inspection-summary">
                <span class="inspection-path">${escapeHtml(run.target || "verification run")}</span>
                <span class="inspection-badges">
                    <span class="status-pill ${statusClass}">${escapeHtml(statusLabel)}</span>
                    <span class="inspection-meta">${escapeHtml(runtimeLabel)}</span>
                    ${classification}
                </span>
            </summary>
            <div class="inspection-subhead">Exit code ${escapeHtml(String(run.exit_code ?? "-"))}</div>
            ${outputParts.join("")}
        `;
        container.appendChild(wrapper);
    });
}

function renderGitPatch(payload) {
    const container = document.getElementById("git-patch-panel");
    container.innerHTML = "";

    if (!payload.git_available) {
        container.innerHTML = '<p class="panel-empty">No git patch available for the active project.</p>';
        return;
    }

    if (!payload.patch) {
        container.innerHTML = '<p class="panel-empty">Git repository detected, but there is no current diff.</p>';
        return;
    }

    const wrapper = document.createElement("details");
    wrapper.className = "inspection-item inspection-item-detail";
    wrapper.open = false;
    wrapper.innerHTML = `
        <summary class="inspection-summary">
            <span class="inspection-path">Working tree diff</span>
            <span class="inspection-badges">
                ${payload.truncated ? '<span class="inspection-meta">TRUNCATED</span>' : ""}
            </span>
        </summary>
        <pre class="inspection-preview"><code>${escapeHtml(payload.patch)}</code></pre>
    `;
    container.appendChild(wrapper);
}

function renderAssistantInsights(data) {
    const container = document.getElementById("assistant-insights");
    container.innerHTML = "";

    const insights = data.improvement_insights || [];
    const summary = data.summary || {};

    if (!insights.length) {
        container.innerHTML = `
            <div class="insight-card">
                <div class="insight-title">No major issues detected</div>
                <div class="insight-body">Recent runs do not show a dominant improvement signal yet.</div>
            </div>
        `;
        return;
    }

    const summaryCard = document.createElement("div");
    summaryCard.className = "insight-card";
    const passRate = Number(summary.pass_rate || 0) * 100;
    summaryCard.innerHTML = `
        <div class="insight-title">Recent performance</div>
        <div class="insight-body">
            ${escapeHtml(`${summary.total_runs ?? 0} runs · ${passRate.toFixed(0)}% pass`)}
        </div>
        <div class="insight-meta">
            ${escapeHtml(`avg ${Number(summary.avg_iterations || 0).toFixed(1)} iteration(s)`)}
        </div>
    `;
    container.appendChild(summaryCard);

    insights.forEach((insight) => {
        const card = document.createElement("div");
        card.className = "insight-card";
        card.innerHTML = `
            <div class="insight-top">
                <span class="insight-severity insight-${escapeHtml(insight.severity || "low")}">${escapeHtml((insight.severity || "low").toUpperCase())}</span>
                <span class="insight-category">${escapeHtml(insight.category || "general")}</span>
            </div>
            <div class="insight-title">${escapeHtml(insight.title || "Insight")}</div>
            <div class="insight-body">${escapeHtml(insight.reason || "")}</div>
            <div class="insight-meta">${escapeHtml(insight.recommended_action || "")}</div>
        `;
        container.appendChild(card);
    });
}

function renderRunHistory(runs) {
    const container = document.getElementById("run-history-list");
    container.innerHTML = "";

    if (!runs.length) {
        container.innerHTML = '<p class="panel-empty">No persisted runs yet.</p>';
        return;
    }

    runs.forEach((run) => {
        const button = document.createElement("button");
        button.className = "run-history-item";
        button.type = "button";
        button.addEventListener("click", () => loadRunDetail(run.run_id));

        const trust = run.trust_metrics || {};
        button.innerHTML = `
            <span class="run-history-top">
                <span class="run-history-status ${run.review_passed ? "status-created" : "status-deleted"}">
                    ${escapeHtml(run.review_passed ? "PASS" : "FAIL")}
                </span>
                <span class="run-history-time">${escapeHtml(formatTimestamp(run.created_at))}</span>
            </span>
            <span class="run-history-task">${escapeHtml(run.task || "Untitled run")}</span>
            <span class="run-history-meta">
                ${escapeHtml(`${trust.changed_files ?? 0} changed · ${trust.verification_total ?? 0} verified`)}
            </span>
        `;
        container.appendChild(button);
    });
}

function formatTimestamp(value) {
    if (!value) {
        return "-";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString();
}

function setIngestLog(message) {
    document.getElementById("ingest-log").textContent = message;
}

function updateConnectionStatus(state, text) {
    const badge = document.getElementById("connection-status");
    const dot = badge.querySelector(".status-dot");
    const label = badge.querySelector(".status-text");

    label.textContent = text;
    dot.style.background =
        state === "connected" ? "var(--accent-green)" :
        state === "error" ? "var(--accent-red)" :
        "var(--accent-green)";
}

function setupTextareaAutoResize() {
    const textarea = document.getElementById("task-input");
    textarea.addEventListener("input", () => {
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    });
}

function setupKeyboardShortcuts() {
    const textarea = document.getElementById("task-input");
    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendTask();
        }
    });
}

function setupDropZone() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");

    dropZone.addEventListener("dragover", (event) => {
        event.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (event) => {
        event.preventDefault();
        dropZone.classList.remove("drag-over");

        const file = event.dataTransfer.files[0];
        if (file && file.name.endsWith(".zip")) {
            uploadZip(file);
        }
    });

    fileInput.addEventListener("change", (event) => {
        const file = event.target.files[0];
        if (file) {
            uploadZip(file);
        }
    });
}
