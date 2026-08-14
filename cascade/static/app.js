const $ = (id) => document.getElementById(id);
let lastSystem = null;
let selectedToolId = null;
let selectedGoalId = null;
let togglingToolId = null;
let showCypher = false;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.error?.message || `HTTP ${res.status}`;
    } catch {
      detail = `HTTP ${res.status}`;
    }
    showError(detail);
    throw new Error(detail);
  }
  clearError();
  return res.json();
}

function showError(detail) {
  $("error-detail").textContent = detail || "";
  $("error-banner").classList.remove("hidden");
}
function clearError() { $("error-banner").classList.add("hidden"); }

function setLoading(isLoading) {
  $("goals-loading").classList.toggle("hidden", !isLoading);
  $("goals-empty").classList.add("hidden");
  $("goal-list").classList.toggle("hidden", isLoading);
}

async function checkDbHealth() {
  const pill = $("db-status");
  try {
    const h = await fetch("/api/healthz").then((r) => r.json());
    if (h.db === "ok") {
      pill.className = "status-pill status-ok";
      pill.textContent = "CognoDB connected";
      clearError();
      return true;
    }
  } catch {}
  pill.className = "status-pill status-bad";
  pill.textContent = "CognoDB unreachable";
  showError("The backend cannot reach the CognoDB instance.");
  return false;
}

async function loadSystem() {
  setLoading(true);
  try {
    const data = await api("/api/system");
    lastSystem = data;
    renderTools(data.tools || []);
    renderGoals(data);
    updateInspector();
  } catch {
    renderTools([]);
    renderGoals(null);
  }
}

function renderTools(tools) {
  const list = $("tool-list");
  list.innerHTML = "";
  tools.forEach((t) => {
    const li = document.createElement("li");
    const isOffline = t.status === "OFFLINE";
    const isSelected = selectedToolId === t.id;
    const isLoading = togglingToolId === t.id;
    li.className = "tool-item" + (isOffline ? " offline" : "") + (isSelected ? " selected" : "") + (isLoading ? " loading" : "");
    li.innerHTML = `
      <button class="tool-toggle" aria-pressed="${isOffline}" ${isLoading ? "disabled" : ""}>
        <span class="toggle-track"><span class="toggle-knob"></span></span>
      </button>
      <div class="tool-info">
        <div class="tool-name">${t.name}</div>
        <div class="tool-meta">
          <span class="tag tag-kind">${t.kind}</span>
          <span class="tag ${isOffline ? "tag-offline" : "tag-online"}">${t.status}</span>
        </div>
      </div>
    `;
    const toggleBtn = li.querySelector(".tool-toggle");
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!isLoading) toggleTool(t);
    });
    li.addEventListener("click", () => {
      selectedToolId = t.id;
      selectedGoalId = null;
      renderTools(tools);
      updateInspector();
    });
    list.appendChild(li);
  });
}

async function toggleTool(tool) {
  const next = tool.status === "ONLINE" ? "OFFLINE" : "ONLINE";
  togglingToolId = tool.id;
  renderTools(lastSystem?.tools || []);
  try {
    await api(`/api/tools/${tool.id}/status?status=${next}`, { method: "POST" });
    await loadSystem();
  } finally {
    togglingToolId = null;
    if (lastSystem) renderTools(lastSystem.tools || []);
  }
}

function renderGoals(data) {
  const list = $("goal-list");
  const empty = $("goals-empty");
  list.innerHTML = "";

  if (!data) {
    setLoading(false);
    empty.classList.remove("hidden");
    empty.querySelector(".empty-title").textContent = "Cannot load system state";
    return;
  }

  const blockedById = new Map((data.blocked_goals || []).map((b) => [b.goal_id, b]));
  const blockedCount = blockedById.size;
  const total = (data.goals || []).length;
  const complete = (data.counts?.goals?.complete || 0);
  const active = total - blockedCount - complete;

  $("goals-summary").textContent = `${blockedCount} blocked · ${active} active · ${complete} complete`;

  if (blockedCount === 0 && active === 0) {
    setLoading(false);
    list.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");
  list.classList.remove("hidden");
  setLoading(false);

  const ordered = (data.goals || []).slice().sort((a, b) => {
    const sa = blockedById.has(a.id) ? 0 : (a.status === "COMPLETE" ? 2 : 1);
    const sb = blockedById.has(b.id) ? 0 : (b.status === "COMPLETE" ? 2 : 1);
    return sa - sb || a.name.localeCompare(b.name);
  });

  ordered.forEach((g) => {
    const blocked = blockedById.get(g.id);
    const isSelected = selectedGoalId === g.id;
    const statusClass = blocked ? "blocked" : (g.status === "COMPLETE" ? "complete" : "active");
    const li = document.createElement("li");
    li.className = "goal-item" + (isSelected ? " selected" : "");
    li.innerHTML = `
      <div class="goal-row">
        <div class="goal-title">${g.name}</div>
        <span class="tag tag-${statusClass}">${blocked ? "BLOCKED" : (g.status === "COMPLETE" ? "COMPLETE" : "ACTIVE")}</span>
      </div>
      ${blocked ? `<div class="goal-cause">Blocked by ${blocked.root_cause_tool}</div>` : ""}
    `;
    li.addEventListener("click", () => {
      selectedGoalId = g.id;
      selectedToolId = null;
      renderGoals(data);
      updateInspector();
    });
    list.appendChild(li);
  });
}

async function updateInspector() {
  const title = $("inspector-title");
  const subtitle = $("inspector-subtitle");
  const body = $("inspector-body");
  const cypherPre = $("inspector-cypher");
  const cypherBtn = $("toggle-cypher");

  if (!lastSystem) {
    cypherBtn.disabled = true;
    return;
  }

  if (selectedToolId) {
    const tool = lastSystem.tools.find((t) => t.id === selectedToolId);
    title.textContent = tool ? tool.name : "Tool";
    subtitle.textContent = "Tool usage and blast radius.";
    body.innerHTML = `<div class="inspector-loading">Loading tool details…</div>`;
    cypherBtn.disabled = false;
    cypherPre.textContent = TOOL_USAGE_CYPHER + "\n\n" + BLAST_RADIUS_CYPHER;
    try {
      const [usage, blast] = await Promise.allSettled([
        api(`/api/tools/${encodeURIComponent(selectedToolId)}/usage`),
        tool?.status === "OFFLINE" ? api(`/api/blast-radius?tool_id=${encodeURIComponent(selectedToolId)}`) : Promise.resolve({ blocked_goals: [] }),
      ]);
      renderToolDetail(
        tool,
        usage.status === "fulfilled" ? usage.value : [],
        blast.status === "fulfilled" ? blast.value : { blocked_goals: [] },
      );
    } catch {
      body.innerHTML = `<div class="panel-empty">Could not load tool details.</div>`;
    }
    return;
  }

  if (selectedGoalId) {
    const goal = lastSystem.goals.find((g) => g.id === selectedGoalId);
    const blocked = (lastSystem.blocked_goals || []).find((b) => b.goal_id === selectedGoalId);
    title.textContent = goal ? goal.name : "Goal";
    subtitle.textContent = "Goal graph, critical path, and failure chain.";
    body.innerHTML = `<div class="inspector-loading">Loading goal details…</div>`;
    cypherBtn.disabled = false;
    cypherPre.textContent = GOAL_COMPOSITION_CYPHER + "\n\n" + BLAST_RADIUS_CYPHER + "\n\n" + CRITICAL_PATH_CYPHER;
    try {
      const [composition, blast, crit] = await Promise.allSettled([
        api(`/api/goals/${encodeURIComponent(selectedGoalId)}/composition`),
        blocked ? api(`/api/blast-radius?tool_id=${encodeURIComponent(blocked.root_cause_tool_id)}`) : Promise.resolve({ blocked_goals: [] }),
        api(`/api/critical-path?goal_id=${encodeURIComponent(selectedGoalId)}`),
      ]);
      renderGoalDetail(
        goal,
        blocked,
        composition.status === "fulfilled" ? composition.value : [],
        blast.status === "fulfilled" ? blast.value : { blocked_goals: [] },
        crit.status === "fulfilled" ? crit.value : { critical_path: [] },
      );
    } catch {
      body.innerHTML = `<div class="panel-empty">Could not load goal details.</div>`;
    }
    return;
  }

  title.textContent = "Inspector";
  subtitle.textContent = "Select a goal or tool to see its graph.";
  cypherBtn.disabled = true;
  cypherPre.textContent = "";
  body.innerHTML = `
    <div class="inspector-placeholder">
      <div class="placeholder-title">Explore the graph</div>
      <p class="placeholder-desc">Each goal decomposes into tasks. Each task is assigned to an agent and may call an external tool.</p>
      <div class="placeholder-steps">
        <div class="step"><span class="step-num">1</span> Click a <strong>goal</strong> to see its task graph, critical path, and bottleneck.</div>
        <div class="step"><span class="step-num">2</span> Click a <strong>tool</strong> to see which agents and goals depend on it.</div>
        <div class="step"><span class="step-num">3</span> Toggle a tool offline to see the blast radius.</div>
      </div>
    </div>
  `;
}

function renderToolDetail(tool, usage, blastData) {
  const body = $("inspector-body");
  if (!tool) {
    body.innerHTML = `<div class="panel-empty">Tool not found.</div>`;
    return;
  }

  let html = "";

  html += `<div class="detail-header">`;
  html += `<div class="detail-title">${tool.name}</div>`;
  html += `<div class="detail-meta"><span class="tag tag-kind">${tool.kind}</span><span class="tag ${tool.status === "OFFLINE" ? "tag-offline" : "tag-online"}">${tool.status}</span></div>`;
  html += `</div>`;

  html += `<div class="path-section"><div class="path-section-title">Used by</div><div class="path-section-desc">Agents and goals that depend on this tool.</div>`;
  if (usage.length === 0) {
    html += `<div class="panel-empty">No tasks require this tool.</div>`;
  } else {
    html += `<div class="usage-list">`;
    const byAgent = {};
    usage.forEach((u) => {
      const agent = u.agent_name || "Unassigned";
      if (!byAgent[agent]) byAgent[agent] = [];
      byAgent[agent].push(u);
    });
    Object.entries(byAgent).forEach(([agent, items]) => {
      html += `<div class="usage-group">`;
      html += `<div class="usage-agent">${agent}</div>`;
      items.forEach((u) => {
        html += `<div class="usage-task"><span class="usage-task-name">${u.task_name}</span><span class="usage-goal">${u.goal_name}</span></div>`;
      });
      html += `</div>`;
    });
    html += `</div>`;
  }
  html += `</div>`;

  const blocked = blastData.blocked_goals || [];
  if (blocked.length > 0) {
    html += `<div class="path-section"><div class="path-section-title">Blast radius</div><div class="path-section-desc">Goals blocked because this tool is offline.</div>`;
    html += `<div class="blocked-list">`;
    blocked.forEach((b) => {
      html += `<div class="blocked-item"><span class="blocked-name">${b.goal_name}</span><span class="blocked-step">Blocked at “${b.failing_step}” · ${b.hops} hops</span></div>`;
    });
    html += `</div>`;
    html += `</div>`;
  }

  body.innerHTML = html;
}

function renderGoalDetail(goal, blocked, composition, blastData, critData) {
  const body = $("inspector-body");
  if (!goal) {
    body.innerHTML = `<div class="panel-empty">Goal not found.</div>`;
    return;
  }

  const statusClass = blocked ? "blocked" : (goal.status === "COMPLETE" ? "complete" : "active");
  const statusText = blocked ? "BLOCKED" : (goal.status === "COMPLETE" ? "COMPLETE" : "ACTIVE");

  let html = "";
  html += `<div class="detail-header">`;
  html += `<div class="detail-title">${goal.name}</div>`;
  html += `<div class="detail-meta"><span class="tag tag-${statusClass}">${statusText}</span></div>`;
  html += `</div>`;

  // Build task graph top-down: if A depends on B, B is drawn below A.
  const taskMap = Object.fromEntries(composition.map((c) => [c.task_id, c]));
  const children = {};
  composition.forEach((c) => {
    children[c.task_id] = c.depends_on || [];
  });

  // Find root: task explicitly flagged by the backend.
  const rootId = composition.find((c) => c.is_root)?.task_id;

  // Critical path highlight.
  const criticalIds = new Set();
  (critData.critical_path || []).forEach((s) => criticalIds.add(s.id));
  const bottleneckId = critData.bottleneck?.id;

  // Failure path highlight.
  const failureIds = new Set();
  let failingTaskId = null;
  if (blocked && blastData) {
    const entry = blastData.blocked_goals.find((b) => b.goal_id === goal.id);
    if (entry) {
      entry.failure_chain.forEach((node) => failureIds.add(node.id || node.name));
      // The last task in the chain is the failing leaf.
      const last = entry.failure_chain[entry.failure_chain.length - 1];
      failingTaskId = last?.id;
    }
  }

  html += `<div class="path-section"><div class="path-section-title">Task graph</div><div class="path-section-desc">Goal → task → agent → tool. Critical path is highlighted; the bottleneck is marked.</div>`;
  if (!rootId) {
    html += `<div class="panel-empty">No tasks found for this goal.</div>`;
  } else {
    html += `<div class="task-tree">`;
    html += renderTaskNode(rootId, taskMap, children, criticalIds, bottleneckId, failureIds, failingTaskId, 0);
    html += `</div>`;
  }
  html += `</div>`;

  if (critData.bottleneck) {
    html += `<div class="path-note">Critical path: ${formatMs(critData.predicted_latency_ms)} total. Bottleneck is “${critData.bottleneck.name}” (${formatMs(critData.bottleneck.estimated_ms)}).</div>`;
  }

  if (blocked) {
    const entry = (blastData.blocked_goals || []).find((b) => b.goal_id === goal.id);
    if (entry) {
      html += `<div class="path-note failure-note">Blocked by ${entry.root_cause_tool}: ${entry.hops} hops from the offline tool, failing at “${entry.failing_step}”.</div>`;
    }
  }

  body.innerHTML = html;
}

function renderTaskNode(taskId, taskMap, children, criticalIds, bottleneckId, failureIds, failingTaskId, depth) {
  const task = taskMap[taskId];
  if (!task) return "";

  const isCritical = criticalIds.has(taskId);
  const isBottleneck = taskId === bottleneckId;
  const isFailure = failureIds.has(taskId);
  const isFailing = taskId === failingTaskId;

  let cls = "tree-node";
  if (isBottleneck) cls += " tree-bottleneck";
  else if (isFailing) cls += " tree-failing";
  else if (isFailure) cls += " tree-failure-path";
  else if (isCritical) cls += " tree-critical";

  let html = `<div class="tree-row" style="padding-left:${depth * 1.5}rem">`;
  html += `<div class="${cls}">`;
  html += `<div class="tree-task-name">${task.task_name}${isBottleneck ? '<span class="bottleneck-badge">bottleneck</span>' : ""}${isFailing ? '<span class="failing-badge">failure point</span>' : ""}</div>`;
  html += `<div class="tree-task-meta">`;
  if (task.agent_name) html += `<span class="tree-agent">${task.agent_name}</span>`;
  if (task.tool_name) html += `<span class="tree-tool ${task.tool_status === "OFFLINE" ? "tree-tool-offline" : ""}">${task.tool_name}${task.tool_status === "OFFLINE" ? " [OFFLINE]" : ""}</span>`;
  html += `<span class="tree-time">${formatMs(task.estimated_ms)}</span>`;
  html += `</div>`;
  html += `</div>`;
  html += `</div>`;

  (children[taskId] || []).forEach((childId) => {
    html += renderTaskNode(childId, taskMap, children, criticalIds, bottleneckId, failureIds, failingTaskId, depth + 1);
  });

  return html;
}

function formatMs(ms) {
  if (ms == null) return "–";
  if (ms >= 1000) return (ms / 1000).toFixed(1) + "s";
  return ms + "ms";
}

const BLAST_RADIUS_CYPHER = `MATCH (tool:Tool {id: $tool_id, status: 'OFFLINE'})<-[:REQUIRES]-(failedTask:Task)
MATCH p = (goal:Goal)-[:HAS_TASK]->(rootTask:Task)-[:DEPENDS_ON*0..4]->(failedTask)
WHERE goal.status <> 'COMPLETE'
RETURN goal.name, failedTask.name, length(p) AS hops
ORDER BY hops`;

const CRITICAL_PATH_CYPHER = `MATCH (goal:Goal {id: $goal_id})-[:HAS_TASK]->(rootTask:Task)
MATCH p = (rootTask)-[:DEPENDS_ON*0..6]->(leafTask:Task)
WHERE NOT (leafTask)-[:DEPENDS_ON]->(:Task)
WITH p, reduce(total = 0, n IN nodes(p) | total + n.estimated_ms) AS total_ms
ORDER BY total_ms DESC LIMIT 1
RETURN total_ms, [n IN nodes(p) | n.name] AS path`;

const GOAL_COMPOSITION_CYPHER = `MATCH (g:Goal {id: $goal_id})-[:HAS_TASK]->(root:Task)
MATCH (root)-[:DEPENDS_ON*0..6]->(t:Task)
OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(a:Agent)
OPTIONAL MATCH (t)-[:REQUIRES]->(tool:Tool)
RETURN t.name, a.name, tool.name, tool.status, (t.id = root.id) AS is_root`;

const TASK_DEPENDENCIES_CYPHER = `MATCH (t:Task)-[:DEPENDS_ON]->(dep:Task)
WHERE t.id IN $task_ids
RETURN t.id, dep.id`;

const TOOL_USAGE_CYPHER = `MATCH (tool:Tool {id: $tool_id})<-[:REQUIRES]-(t:Task)
OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(a:Agent)
MATCH (g:Goal)-[:HAS_TASK]->(t)
RETURN t.name, a.name, g.name`;

function toggleCypher() {
  showCypher = !showCypher;
  $("inspector-cypher").classList.toggle("hidden", !showCypher);
  $("toggle-cypher").textContent = showCypher ? "Hide Cypher" : "Show Cypher";
}

async function bootstrap() {
  if (!(await checkDbHealth())) return;
  await loadSystem();
}

$("refresh-btn").addEventListener("click", async () => { if (await checkDbHealth()) await loadSystem(); });
$("error-retry").addEventListener("click", async () => { if (await checkDbHealth()) await loadSystem(); });
$("toggle-cypher").addEventListener("click", toggleCypher);

bootstrap();
