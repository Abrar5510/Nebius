const state = {
  health: null,
  jobs: [],
  job: null,
  selectedId: null,
  events: [],
  lastSeq: 0,
  library: null,
  stageDefs: [],
  view: "runs",
  refreshing: false,
  stageSignature: "",
  eventSignature: "",
  librarySignature: "",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function titleize(value) {
  return String(value ?? "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function pct(value) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(Number(value) * 100)}%`;
}

function timeShort(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function duration(stage) {
  if (!stage.started_at || !stage.finished_at) return "";
  const ms = new Date(stage.finished_at) - new Date(stage.started_at);
  if (!Number.isFinite(ms)) return "";
  return ms < 1000 ? `${Math.max(0, Math.round(ms))}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function toast(message, bad = false) {
  const node = document.createElement("div");
  node.className = "toast";
  if (bad) node.style.borderColor = "rgba(255,112,112,.4)";
  node.textContent = message;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new Error((data && data.error) || `${response.status} ${response.statusText}`);
  }
  return data;
}

function stageDefs() {
  return state.stageDefs.length ? state.stageDefs : [];
}

function stageDef(name) {
  return stageDefs().find((stage) => stage.name === name);
}

function outputFor(name) {
  const stage = state.job?.stages?.find((item) => item.name === name);
  return stage?.output || {};
}

function setView(view) {
  state.view = view;
  $$(".view").forEach((node) => {
    node.hidden = node.id !== `view-${view}`;
  });
  $$(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  $("#crumb-current").textContent = view === "runs" ? "RUNS" : view === "library" ? "LIBRARY" : "SYSTEM";
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "library") renderLibrary();
  if (view === "system") renderSystem();
}

function renderHealth() {
  const health = state.health;
  const badge = $("#health-pill");
  if (!health) {
    badge.innerHTML = '<span class="pulse"></span> offline';
    badge.classList.add("is-bad");
    return;
  }
  badge.classList.remove("is-bad");
  badge.innerHTML = `<span class="pulse"></span>${esc(health.mode)} · ${esc(health.storage)} · ${esc(health.database)}`;
  $("#mode-label").textContent = `${health.mode} mode · ${health.execution}`;
  $("#hero-jobs").textContent = String(health.jobs ?? 0).padStart(2, "0");
  const skillCount = Object.keys(state.library?.skills || {}).length;
  $("#hero-skills").textContent = String(skillCount).padStart(2, "0");
}

function renderJobPicker() {
  const picker = $("#job-picker");
  if (!state.jobs.length) {
    picker.innerHTML = '<option value="">No runs yet</option>';
    return;
  }
  picker.innerHTML = state.jobs
    .map((job) => {
      const label = `${job.skill} · ${job.status} · ${job.id.slice(-6)}`;
      return `<option value="${esc(job.id)}" ${job.id === state.selectedId ? "selected" : ""}>${esc(label)}</option>`;
    })
    .join("");
}

function renderJobHeader() {
  const job = state.job;
  $("#run-again").disabled = !job;
  if (!job) {
    $("#job-title").textContent = "No run selected";
    $("#job-meta").textContent = "Start a synthetic capture to see the whole pipeline move.";
    $("#job-state").className = "job-state";
    $("#job-state").innerHTML = '<span class="status-dot"></span><span>idle</span>';
    $("#progress-text").textContent = "0 of 10 stages";
    $("#progress-pct").textContent = "0%";
    $("#progress-fill").style.width = "0%";
    $("#run-id").textContent = "";
    return;
  }
  $("#job-title").textContent = titleize(job.skill);
  $("#job-meta").textContent = `${job.robot.toUpperCase()} · capture ${job.capture_id} · ${timeShort(job.created_at)}`;
  $("#job-state").className = `job-state ${job.status}`;
  $("#job-state").innerHTML = `<span class="status-dot"></span><span>${esc(job.status)}</span>`;
  const total = job.stage_count || job.stages.length || 1;
  const done = job.progress || 0;
  const progress = Math.round((done / total) * 100);
  $("#progress-text").textContent = `${done} of ${total} stages`;
  $("#progress-pct").textContent = `${progress}%`;
  $("#progress-fill").style.width = `${progress}%`;
  $("#run-id").textContent = job.id;
}

function renderStages() {
  const job = state.job;
  const list = $("#stage-list");
  if (!job) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-glyph">⌁</div>
        <h3>Watch a skill assemble itself</h3>
        <p>Each box is a real stage in the build plan, from understanding the narration to publishing a LoRA.</p>
        <button class="button button-primary" data-action="demo">Run the cup demo <span class="arrow">↗</span></button>
      </div>`;
    return;
  }
  const signature = JSON.stringify([
    job.id,
    ...job.stages.map((stage) => [stage.name, stage.status, stage.error, stage.output?.summary, stage.started_at, stage.finished_at]),
  ]);
  if (signature === state.stageSignature) return;
  state.stageSignature = signature;

  list.innerHTML = job.stages
    .map((stage) => {
      const def = stageDef(stage.name) || {
        letter: "·",
        title: titleize(stage.name),
        description: "",
      };
      const summary = stage.error || stage.output?.summary || def.description;
      const status = stage.status;
      const badge = status === "succeeded" ? "done" : status;
      const elapsed = duration(stage);
      const inspect = status === "pending" ? "" : `<button class="stage-open" data-stage="${esc(stage.name)}">inspect</button>`;
      return `
        <div class="stage is-${esc(status)}">
          <div class="stage-marker"><div class="stage-letter">${esc(def.letter)}</div></div>
          <div class="stage-content">
            <div class="stage-head">
              <span class="stage-title">${esc(def.title)}</span>
              <span class="stage-badge">${esc(badge)}</span>
              <span class="stage-time">${esc(elapsed)}</span>
            </div>
            <p class="stage-summary">${esc(summary)}</p>
          </div>
          ${inspect}
        </div>`;
    })
    .join("");
}

function renderMetrics() {
  const extract = outputFor("extract");
  const understand = outputFor("understand");
  const multiply = outputFor("multiply");
  const evaluate = outputFor("evaluate");
  const verify = outputFor("verify");
  const objects = extract.object_count ?? (understand.objects ? understand.objects.length : null);
  $("#metric-objects").textContent = objects === null || objects === undefined ? "—" : String(objects).padStart(2, "0");
  $("#metric-frames").textContent = extract.num_frames ? String(extract.num_frames) : "—";
  const clips = multiply.counts?.training_clips;
  $("#metric-clips").textContent = clips ? Number(clips).toLocaleString() : "—";
  const best = evaluate.best_sim_overall;
  $("#metric-success").textContent = best === undefined ? "—" : pct(best);
  $("#metric-robot").textContent = `robot: ${state.job?.robot || "—"}`;
  $("#metric-verification").textContent =
    verify.checks_passed !== undefined ? `verify: ${verify.checks_passed}/${verify.checks_total}` : "verify: —";
}

function renderAblation() {
  const evaluate = outputFor("evaluate");
  const rows = evaluate.rows || [];
  const container = $("#ablation");
  if (!rows.length) {
    container.innerHTML = '<p class="muted">The evaluation stage will fill this table. Held-out axes: pose, instance, lighting, scene.</p>';
    return;
  }
  const cells = rows
    .map((row) => {
      const highlight = String(row.policy).includes("Transfer") ? "highlight" : "";
      return `<tr class="${highlight}">
        <td title="${esc(row.data)}">${esc(row.policy)}</td>
        <td>${pct(row.pose)}</td>
        <td>${pct(row.instance)}</td>
        <td>${pct(row.lighting)}</td>
        <td>${pct(row.scene)}</td>
      </tr>`;
    })
    .join("");
  container.innerHTML = `
    <table class="ablation-table">
      <thead><tr><th>policy</th><th>pose</th><th>inst</th><th>light</th><th>scene</th></tr></thead>
      <tbody>${cells}</tbody>
    </table>
    <p class="muted small" style="margin-top:10px">Sim success on held-out variations · real robot pending</p>`;
}

function renderSafety() {
  const deploy = outputFor("deploy");
  const layers = deploy.safety_layers || [];
  const list = $("#safety-list");
  if (!layers.length) {
    list.innerHTML = `
      <li><span class="check">□</span> motion envelope</li>
      <li><span class="check">□</span> Cosmos monitor</li>
      <li><span class="check">□</span> twin dry run</li>
      <li><span class="check">□</span> physical e-stop</li>`;
    $("#safety-note").textContent = "Nothing moves until the twin replay passes.";
    return;
  }
  const labels = {
    motion_envelope: "motion envelope armed",
    cosmos_monitor: "Cosmos monitor armed",
    twin_dry_run: "twin dry run passed",
    physical_estop: "physical e-stop required",
  };
  list.innerHTML = layers
    .map((layer) => `<li><span class="check on">✓</span> ${esc(labels[layer] || layer)}</li>`)
    .join("");
  $("#safety-note").textContent = "The arm is packaged. A human must confirm the e-stop before the first real run.";
}

function renderEvents() {
  const signature = JSON.stringify(state.events.map((event) => event.seq));
  $("#event-count").textContent = `${state.events.length} event${state.events.length === 1 ? "" : "s"}`;
  if (signature === state.eventSignature) return;
  state.eventSignature = signature;
  const list = $("#event-list");
  if (!state.events.length) {
    list.innerHTML = '<p class="event-feed-empty">The orchestrator writes one event per stage transition. They appear here as the worker runs.</p>';
    return;
  }
  list.innerHTML = [...state.events]
    .reverse()
    .slice(0, 80)
    .map((event) => {
      const kind = String(event.kind || "").split(".").pop();
      return `<div class="event-row">
        <span class="event-time">${esc(timeShort(event.created_at))}</span>
        <span class="event-kind ${esc(kind)}">${esc(kind)}</span>
        <span class="event-msg">${esc(event.message)}</span>
      </div>`;
    })
    .join("");
}

function renderLibrary() {
  const skills = state.library?.skills || {};
  const entries = Object.entries(skills);
  const signature = JSON.stringify(entries);
  if (signature !== state.librarySignature) {
    state.librarySignature = signature;
    const card = ([name, entry]) => `
      <article class="skill-card" data-skill="${esc(name)}">
        <div class="skill-top">
          <span class="skill-name">${esc(name)}</span>
          <span class="skill-version">v${esc(entry.latest)}</span>
        </div>
        <p>${esc(entry.instruction || entry.task_name || "A reusable robot skill.")}</p>
        <div class="skill-tags">
          <span class="tag accent">${esc((entry.versions || []).length)} version${(entry.versions || []).length === 1 ? "" : "s"}</span>
          ${(entry.robot_embodiments || []).map((robot) => `<span class="tag">${esc(robot)}</span>`).join("")}
          <span class="tag">adapt on install</span>
        </div>
      </article>`;
    const empty = `<div class="skill-card ghost"><div class="skill-name">The library is empty</div><p>Run the cup demo to publish the first skill.</p></div>`;
    $("#skill-grid").innerHTML = entries.length ? entries.map(card).join("") : empty;
    $("#skill-grid-mini").innerHTML = entries.length ? entries.slice(0, 3).map(card).join("") : empty;
  }
  $("#hero-skills").textContent = String(entries.length).padStart(2, "0");
}

function renderSystem() {
  const health = state.health || {};
  const pairs = [
    ["mode", health.mode],
    ["execution", health.execution],
    ["storage", health.storage],
    ["database", health.database],
    ["captures", health.captures],
    ["jobs", health.jobs],
    ["stages", (health.stages || []).length],
  ];
  $("#system-health").innerHTML = pairs
    .map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`)
    .join("");
  $("#stage-dag").innerHTML = stageDefs()
    .map(
      (stage) => `<li>
        <span class="dag-letter">[${esc(stage.letter)}]</span>
        <span><span class="dag-title">${esc(stage.title)}</span><span class="dag-desc">${esc(stage.description)}</span></span>
      </li>`
    )
    .join("");
}

function renderAll() {
  renderHealth();
  renderJobPicker();
  renderJobHeader();
  renderStages();
  renderMetrics();
  renderAblation();
  renderSafety();
  renderEvents();
  renderLibrary();
  if (state.view === "system") renderSystem();
}

async function loadEvents() {
  if (!state.selectedId) return;
  const data = await fetchJSON(`/api/jobs/${encodeURIComponent(state.selectedId)}/events?after=${state.lastSeq}`);
  const incoming = data.events || [];
  if (incoming.length) {
    state.events.push(...incoming);
    state.lastSeq = incoming[incoming.length - 1].seq;
    if (state.events.length > 500) state.events = state.events.slice(-500);
  }
}

async function loadSelectedJob() {
  if (!state.selectedId) return;
  state.job = await fetchJSON(`/api/jobs/${encodeURIComponent(state.selectedId)}`);
  state.stageDefs = state.job.stage_defs || state.stageDefs;
  await loadEvents();
}

async function selectJob(id, { reset = true } = {}) {
  state.selectedId = id;
  state.stageSignature = "";
  state.eventSignature = "";
  if (reset) {
    state.events = [];
    state.lastSeq = 0;
  }
  if (id) {
    history.replaceState(null, "", `#job=${encodeURIComponent(id)}`);
    await loadSelectedJob();
  } else {
    state.job = null;
  }
  renderAll();
}

async function refresh({ quiet = false } = {}) {
  if (state.refreshing) return;
  state.refreshing = true;
  try {
    const [health, library, jobsData] = await Promise.all([
      fetchJSON("/api/health"),
      fetchJSON("/api/library"),
      fetchJSON("/api/jobs?limit=25"),
    ]);
    state.health = health;
    state.stageDefs = health.stage_defs || state.stageDefs;
    state.library = library;
    state.jobs = jobsData.jobs || [];

    if (!state.selectedId && state.jobs.length) {
      state.selectedId = state.jobs[0].id;
    }
    if (state.selectedId) {
      await loadSelectedJob();
    }
    renderAll();
  } catch (error) {
    if (!quiet) console.error(error);
    const badge = $("#health-pill");
    badge.classList.add("is-bad");
    badge.innerHTML = '<span class="pulse"></span> disconnected';
    if (!quiet) toast(`Could not refresh: ${error.message}`, true);
  } finally {
    state.refreshing = false;
  }
}

async function startDemo() {
  const buttons = $$("[data-action='demo'], #demo-button, #run-again");
  buttons.forEach((button) => (button.disabled = true));
  try {
    const payload = await fetchJSON("/api/demo", {
      method: "POST",
      body: JSON.stringify({ robot: "so101" }),
    });
    toast("Capture queued. Watch the stages move.");
    await selectJob(payload.job.id);
    await refresh({ quiet: true });
  } catch (error) {
    toast(`Could not start demo: ${error.message}`, true);
  } finally {
    buttons.forEach((button) => (button.disabled = false));
    $("#run-again").disabled = !state.job;
  }
}

function collectArtifacts(value, prefix = "", found = new Set()) {
  if (typeof value === "string") {
    if (value.startsWith("jobs/") || value.startsWith("captures/") || value.startsWith("library/")) {
      found.add(value);
    }
  } else if (Array.isArray(value)) {
    value.forEach((item) => collectArtifacts(item, prefix, found));
  } else if (value && typeof value === "object") {
    Object.values(value).forEach((item) => collectArtifacts(item, prefix, found));
  }
  return [...found];
}

function openDrawer(kicker, title, body) {
  $("#drawer-kicker").textContent = kicker;
  $("#drawer-title").textContent = title;
  $("#drawer-body").innerHTML = body;
  $("#drawer").hidden = false;
  $("#drawer-backdrop").hidden = false;
  document.body.style.overflow = "hidden";
}

function closeDrawer() {
  $("#drawer").hidden = true;
  $("#drawer-backdrop").hidden = true;
  document.body.style.overflow = "";
}

function openStage(stageName) {
  const stage = state.job?.stages?.find((item) => item.name === stageName);
  const def = stageDef(stageName) || { title: titleize(stageName), description: "" };
  if (!stage) return;
  const artifacts = collectArtifacts(stage.output);
  const checks = stage.output?.checks || [];
  const checksHtml = checks.length
    ? `<div class="drawer-section"><h3>Checks</h3><div class="drawer-checks">${checks
        .map(
          (check) => `<div class="drawer-check ${check.passed ? "pass" : "fail"}">
            <span>${esc(check.name)}</span><span>${check.passed ? "pass" : "fail"} · ${esc(check.detail)}</span>
          </div>`
        )
        .join("")}</div></div>`
    : "";
  const artifactsHtml = artifacts.length
    ? `<div class="drawer-section"><h3>Artifacts</h3><div class="artifact-list">${artifacts
        .map(
          (key) => `<a class="artifact-link" href="/api/artifact?key=${encodeURIComponent(key)}" target="_blank" rel="noopener">
            <span>${esc(key)}</span><span>open ↗</span>
          </a>`
        )
        .join("")}</div></div>`
    : "";
  const output = { ...stage.output };
  delete output.summary;
  openDrawer(
    `STAGE ${def.letter || ""} · ${stage.status}`,
    def.title,
    `<div class="drawer-section"><h3>What happened</h3><p class="muted">${esc(
      stage.error || stage.output?.summary || def.description
    )}</p></div>
     ${checksHtml}
     ${artifactsHtml}
     <div class="drawer-section"><h3>Output</h3><pre class="json-view">${esc(JSON.stringify(output, null, 2))}</pre></div>`
  );
}

async function openSkill(name, version = null) {
  try {
    const query = version ? `?version=${encodeURIComponent(version)}` : "";
    const skill = await fetchJSON(`/api/library/${encodeURIComponent(name)}${query}`);
    const files = (skill.files || [])
      .map(
        (file) => `<div class="drawer-check"><span>${esc(file.path)}</span><span>${Math.max(1, Math.round(file.bytes / 1024))} KB</span></div>`
      )
      .join("");
    openDrawer(
      `SKILL · v${skill.version}`,
      name,
      `<div class="drawer-section"><h3>Instruction</h3><p class="muted">${esc(skill.instruction)}</p></div>
       <div class="drawer-section"><h3>Package</h3><div class="drawer-checks">${files}</div></div>
       <div class="drawer-section"><h3>Privacy</h3><p class="muted small">Faces blurred at capture. Raw video is not in the package. Only the object-centric demo and LoRA are shared.</p></div>
       <div class="drawer-section"><h3>Manifest</h3><pre class="json-view">${esc(JSON.stringify(skill, null, 2))}</pre></div>`
    );
  } catch (error) {
    toast(`Could not open skill: ${error.message}`, true);
  }
}

function bind() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  $$("[data-view]").forEach((button) => {
    if (!button.classList.contains("nav-item")) {
      button.addEventListener("click", () => setView(button.dataset.view));
    }
  });
  $("#demo-button").addEventListener("click", startDemo);
  $("#refresh-button").addEventListener("click", () => refresh());
  $("#run-again").addEventListener("click", startDemo);
  $("#job-picker").addEventListener("change", (event) => {
    if (event.target.value) selectJob(event.target.value);
  });
  $("#stage-list").addEventListener("click", (event) => {
    const demo = event.target.closest("[data-action='demo']");
    if (demo) {
      startDemo();
      return;
    }
    const button = event.target.closest(".stage-open");
    if (button) openStage(button.dataset.stage);
  });
  $("#skill-grid").addEventListener("click", (event) => {
    const card = event.target.closest(".skill-card[data-skill]");
    if (card) openSkill(card.dataset.skill);
  });
  $("#skill-grid-mini").addEventListener("click", (event) => {
    const card = event.target.closest(".skill-card[data-skill]");
    if (card) openSkill(card.dataset.skill);
  });
  $("#drawer-close").addEventListener("click", closeDrawer);
  $("#drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });
}

async function init() {
  bind();
  const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
  const hashJob = hash.get("job");
  if (hashJob) state.selectedId = hashJob;
  await refresh();
  setInterval(() => {
    if (!document.hidden) refresh({ quiet: true });
  }, 1400);
}

init();
