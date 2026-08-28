"use strict";

const state = {
  apiBase: `http://${window.location.hostname}:8765`, catalog: null, observations: [],
  selectedId: null, selectedDetail: null, activeJob: null, pollTimer: null, startedAt: null,
};

const nodes = {
  apiBase: document.querySelector("#api-base"), connectionDot: document.querySelector("#connection-dot"),
  connectionText: document.querySelector("#connection-text"), count: document.querySelector("#observation-count"),
  list: document.querySelector("#observation-list"), search: document.querySelector("#observation-search"),
  title: document.querySelector("#observation-title"), meta: document.querySelector("#observation-meta"),
  continuum: document.querySelector("#continuum-image"), magnetogram: document.querySelector("#magnetogram-image"),
  fitsCards: document.querySelector("#fits-cards"), analyze: document.querySelector("#analyze-button"),
  progress: document.querySelector("#analysis-progress"), progressLabel: document.querySelector("#progress-label"),
  progressValue: document.querySelector("#progress-value"), progressBar: document.querySelector("#progress-bar"),
  progressDetail: document.querySelector("#progress-detail"), result: document.querySelector("#analysis-result"),
  placeholder: document.querySelector("#analysis-placeholder"), predictedClass: document.querySelector("#predicted-class"),
  probabilities: document.querySelector("#probability-bars"), visualEvidence: document.querySelector("#visual-evidence"),
  fitsEvidence: document.querySelector("#fits-evidence"), caveat: document.querySelector("#analysis-caveat"),
  audit: document.querySelector("#audit-output"), toast: document.querySelector("#toast"),
};

async function api(path, options = {}) {
  const response = await fetch(`${state.apiBase}${path}`, {headers: {"Content-Type": "application/json"}, ...options});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
  return payload;
}

async function connect() {
  setConnection("loading", "正在连接观测服务");
  state.apiBase = nodes.apiBase.value.trim().replace(/\/$/, "");
  try {
    const [health, catalog] = await Promise.all([api("/health"), api("/workbench/catalog")]);
    if (!health.workbench) throw new Error("服务器未启用天文工作台");
    state.catalog = catalog; state.observations = catalog.observations;
    nodes.count.textContent = String(catalog.observation_count);
    renderObservationList(state.observations);
    setConnection("online", `${catalog.observation_count} 条观测 · 数据已核验`);
    if (state.observations.length) await selectObservation(state.observations[0].observation_id);
  } catch (error) {
    setConnection("error", "观测服务连接失败"); showToast(error.message, true);
  }
}

function setConnection(mode, message) {
  nodes.connectionDot.className = `status-dot ${mode}`; nodes.connectionText.textContent = message;
}

function renderObservationList(observations) {
  const fragment = document.createDocumentFragment();
  observations.forEach((observation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `observation-row${observation.observation_id === state.selectedId ? " selected" : ""}`;
    button.dataset.id = observation.observation_id;
    button.innerHTML = `<span class="observation-glyph"></span><span><strong>${escapeHtml(observation.observation_id)}</strong><small>HARP ${observation.harpnum} · ${formatTai(observation.observed_at_tai)}</small></span><em>4M</em>`;
    button.addEventListener("click", () => selectObservation(observation.observation_id));
    fragment.append(button);
  });
  nodes.list.replaceChildren(fragment);
}

async function selectObservation(observationId) {
  if (state.activeJob && ["QUEUED", "RUNNING"].includes(state.activeJob.status)) {
    showToast("当前 AI 分析尚未结束，请稍候再切换观测。", true); return;
  }
  state.selectedId = observationId; renderObservationList(filteredObservations());
  nodes.analyze.disabled = true; nodes.title.textContent = observationId;
  nodes.meta.textContent = "正在读取四模态观测…"; resetAnalysis();
  try {
    const detail = await api(`/workbench/observations/${encodeURIComponent(observationId)}`);
    state.selectedDetail = detail; renderObservation(detail); nodes.analyze.disabled = false;
  } catch (error) { showToast(`读取观测失败：${error.message}`, true); }
}

function renderObservation(detail) {
  nodes.title.textContent = detail.observation_id;
  nodes.meta.textContent = `HARP ${detail.harpnum} · ${formatTai(detail.observed_at_tai)} · ${detail.coordinate_context}`;
  nodes.continuum.src = `${state.apiBase}${detail.images.continuum}`;
  nodes.magnetogram.src = `${state.apiBase}${detail.images.magnetogram}`;
  nodes.fitsCards.innerHTML = Object.entries(detail.fits).map(([name, summary]) => {
    const title = name === "continuum" ? "连续谱 FITS" : "磁图 FITS";
    return `<article class="fits-card"><div><strong>${title}</strong><span>${summary.shape.join(" × ")} px</span></div><dl><dt>MEAN</dt><dd>${formatNumber(summary.mean)}</dd><dt>STD</dt><dd>${formatNumber(summary.std)}</dd><dt>RANGE</dt><dd>${formatNumber(summary.min)} — ${formatNumber(summary.max)}</dd><dt>FINITE</dt><dd>${(summary.finite_fraction * 100).toFixed(2)}%</dd></dl></article>`;
  }).join("");
}

async function startAnalysis() {
  if (!state.selectedId) return;
  nodes.analyze.disabled = true; nodes.result.hidden = true; nodes.placeholder.hidden = true;
  nodes.progress.hidden = false; state.startedAt = Date.now();
  updateProgress({status: "QUEUED", stage: "PREPARING_MODALITIES", progress: 5});
  try {
    state.activeJob = await api("/workbench/analyses", {method: "POST", body: JSON.stringify({observation_id: state.selectedId})});
    nodes.audit.textContent = JSON.stringify({job_id: state.activeJob.job_id, observation_id: state.selectedId, label_policy: state.catalog.label_policy}, null, 2);
    pollAnalysis();
  } catch (error) { failAnalysis(error.message); }
}

async function pollAnalysis() {
  try {
    const job = await api(`/workbench/jobs/${encodeURIComponent(state.activeJob.job_id)}`);
    state.activeJob = job; updateProgress(job);
    if (job.status === "SUCCEEDED") { renderAnalysis(job.result); return; }
    if (job.status === "FAILED") { failAnalysis(job.error?.message || "AI 分析失败"); return; }
    state.pollTimer = window.setTimeout(pollAnalysis, 1200);
  } catch (error) { failAnalysis(error.message); }
}

function updateProgress(job) {
  const labels = {PREPARING_MODALITIES: "正在准备四模态输入", QWEN_MULTIMODAL_REASONING: "Qwen-VL 正在联合分析图像与 FITS", EVIDENCE_READY: "证据与判读已生成", FAILED: "分析未完成"};
  const elapsed = state.startedAt ? Math.floor((Date.now() - state.startedAt) / 1000) : 0;
  nodes.progressLabel.textContent = labels[job.stage] || "正在分析";
  nodes.progressValue.textContent = `${job.progress}%`; nodes.progressBar.style.width = `${job.progress}%`;
  nodes.progressDetail.textContent = `已用时 ${elapsed} 秒 · 单样本分析 · ${job.status}`;
}

function renderAnalysis(result) {
  window.clearTimeout(state.pollTimer); nodes.progress.hidden = true; nodes.result.hidden = false;
  nodes.placeholder.hidden = true; nodes.analyze.disabled = false; nodes.predictedClass.textContent = result.label;
  nodes.probabilities.innerHTML = Object.entries(result.probabilities).sort((left, right) => right[1] - left[1]).map(([label, value]) => `<div class="probability-row"><div><span>${escapeHtml(label)}</span><strong>${(value * 100).toFixed(1)}%</strong></div><i><b style="width:${value * 100}%"></b></i></div>`).join("");
  renderEvidence(nodes.visualEvidence, result.visual_evidence, "模型未返回单独的视觉依据。");
  renderEvidence(nodes.fitsEvidence, result.fits_evidence, "模型未返回单独的数值依据。");
  nodes.caveat.textContent = result.caveat;
  nodes.audit.textContent = JSON.stringify({job_id: state.activeJob.job_id, observation_id: state.selectedId, model: result.model, status: result.scientific_status}, null, 2);
  showToast("当前观测的 AI 判读已完成");
}

function renderEvidence(node, evidence, fallback) {
  node.replaceChildren(...(evidence.length ? evidence : [fallback]).map((value) => {
    const item = document.createElement("li"); item.textContent = value; return item;
  }));
}

function failAnalysis(message) {
  window.clearTimeout(state.pollTimer); nodes.progress.hidden = true; nodes.placeholder.hidden = false;
  nodes.analyze.disabled = false; showToast(`分析失败：${message}`, true);
}

function resetAnalysis() {
  window.clearTimeout(state.pollTimer); state.activeJob = null; nodes.progress.hidden = true;
  nodes.result.hidden = true; nodes.placeholder.hidden = false; nodes.audit.textContent = "尚无本次分析记录";
}

function filteredObservations() {
  const query = nodes.search.value.trim().toLowerCase();
  if (!query) return state.observations;
  return state.observations.filter((observation) => `${observation.observation_id} ${observation.harpnum} ${observation.observed_at_tai}`.toLowerCase().includes(query));
}

function formatTai(value) {
  const match = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_TAI$/.exec(value);
  return match ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]} TAI` : value;
}

function formatNumber(value) {
  const number = Number(value);
  if (Math.abs(number) >= 10000 || (Math.abs(number) > 0 && Math.abs(number) < 0.01)) return number.toExponential(2);
  return number.toLocaleString("zh-CN", {maximumFractionDigits: 3});
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"})[char]);
}

function showToast(message, error = false) {
  nodes.toast.textContent = message; nodes.toast.className = `toast${error ? " error" : ""}`;
  nodes.toast.hidden = false; window.setTimeout(() => { nodes.toast.hidden = true; }, 4500);
}

nodes.search.addEventListener("input", () => renderObservationList(filteredObservations()));
nodes.analyze.addEventListener("click", startAnalysis);
document.querySelector("#settings-toggle").addEventListener("click", () => {
  const settings = document.querySelector("#settings"); settings.hidden = !settings.hidden;
});
document.querySelector("#reconnect").addEventListener("click", connect);
nodes.apiBase.value = state.apiBase;
connect();
