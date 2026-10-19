"use strict";

// ---------- helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const NAVY = "#003366", RED = "#E74C3C", BLUE = "#2E86AB";

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  let body = {};
  try { body = await res.json(); } catch (_) { /* non-JSON response */ }
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}
const post = (url, data) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });

function msg(text, kind = "info") {
  const el = $("#msg");
  if (!el) return;
  el.className = "msg " + (text ? kind : "");
  el.textContent = text || "";
}
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function table(cols, rows, rowClass) {
  const head = cols.map(c => `<th>${esc(c)}</th>`).join("");
  const body = rows.map(r => `<tr class="${rowClass ? rowClass(r) : ""}">${cols.map(c => `<td>${esc(typeof r[c] === "number" ? +r[c].toFixed(4) : r[c])}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
const plot = (...a) => { try { if (window.Plotly) return window.Plotly.newPlot(...a); } catch (e) { console.error(e); } };
const fmt = n => Number(n).toLocaleString("en-US");

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const pill = $("#status-pill");
    pill.textContent = s.model_ready ? `Model ready: ${s.best_model}` : s.data_loaded ? `Data: ${fmt(s.rows)} rows` : "No data loaded";
    pill.classList.toggle("ok", s.model_ready);
    return s;
  } catch (_) { return null; }
}

// ---------- Data page ----------
async function renderData() {
  const d = await api("/api/data/summary");
  $("#data-view").hidden = false;
  $("#data-metrics").innerHTML = [
    ["Rows", fmt(d.rows)], ["Columns", d.columns], ["Missing values", fmt(d.missing)], ["Churn rate", (d.churn_rate * 100).toFixed(1) + "%"],
  ].map(([l, v]) => `<div class="metric"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  $("#head-table").innerHTML = table(Object.keys(d.head[0]), d.head);
  $("#info-table").innerHTML = table(["column", "type", "non_null", "null", "unique"], d.column_info);
  plot("chart-pie", [{ type: "pie", labels: d.churn_counts.labels, values: d.churn_counts.values, hole: .45, marker: { colors: [BLUE, RED] } }],
    { margin: { t: 10, b: 10, l: 10, r: 10 }, height: 320 }, { responsive: true });
  plot("chart-corr", [{ type: "heatmap", z: d.correlation.matrix, x: d.correlation.labels, y: d.correlation.labels, colorscale: "RdBu", zmid: 0, reversescale: true }],
    { margin: { t: 10, l: 110, b: 110 }, height: 380 }, { responsive: true });
}

function initData() {
  const done = async text => { msg(text, "ok"); await renderData(); refreshStatus(); };
  $("#btn-upload").onclick = async () => {
    const f = $("#csv-file").files[0];
    if (!f) return msg("Choose a CSV file first.", "err");
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/data/upload", { method: "POST", body: fd }); await done(`${r.source} loaded (${fmt(r.rows)} rows).`); }
    catch (e) { msg(e.message, "err"); }
  };
  $("#btn-sample").onclick = async () => {
    try { const r = await api("/api/data/sample", { method: "POST" }); await done(`${r.source} loaded (${fmt(r.rows)} rows).`); }
    catch (e) { msg(e.message, "err"); }
  };
  refreshStatus().then(s => { if (s && s.data_loaded) renderData(); });
}

// ---------- Features page ----------
function showFeatures(r) {
  $("#feat-result").hidden = false;
  $("#feat-summary").textContent = `${r.n_features} features — ${fmt(r.train_rows)} training rows, ${fmt(r.test_rows)} test rows (80/20 stratified split).`;
  $("#feat-list").innerHTML = r.features.map(f => `<span>${esc(f)}</span>`).join("");
}
function initFeatures() {
  $("#btn-features").onclick = async e => {
    e.target.disabled = true; msg("Creating features…");
    try { const r = await post("/api/features"); showFeatures(r); msg(`${r.n_features} features created.`, "ok"); refreshStatus(); }
    catch (err) { msg(err.message, "err"); }
    e.target.disabled = false;
  };
  refreshStatus();
}

// ---------- Training page ----------
const METRICS = [["accuracy", "Accuracy"], ["precision", "Precision"], ["recall", "Recall"], ["f1", "F1"], ["auc", "AUC"], ["ks", "KS"]];

function renderResults(r) {
  const keys = Object.keys(r.metrics);
  if (!keys.length) return;
  $("#results").hidden = false;
  const rows = METRICS.map(([k, label]) => Object.fromEntries([["Metric", label], ...keys.map(m => [r.labels[m], r.metrics[m][k]])]));
  $("#cmp-table").innerHTML = table(["Metric", ...keys.map(m => r.labels[m])], rows);
  $("#best-line").textContent = r.best_model ? `Best model (highest AUC): ${r.best_model}` : "";
  const colors = { lr: BLUE, lgbm: RED };
  const traces = keys.map(k => ({ x: r.metrics[k].roc.fpr, y: r.metrics[k].roc.tpr, mode: "lines", name: `${r.labels[k]} (AUC ${r.metrics[k].auc.toFixed(3)})`, line: { color: colors[k], width: 2 } }));
  traces.push({ x: [0, 1], y: [0, 1], mode: "lines", name: "Random", line: { dash: "dash", color: "gray" } });
  plot("chart-roc", traces, { xaxis: { title: "False positive rate" }, yaxis: { title: "True positive rate" }, margin: { t: 10 }, height: 380, legend: { orientation: "h", y: -0.25 } }, { responsive: true });
  $("#cm-wrap").innerHTML = keys.map(k => `<div id="cm-${k}"></div>`).join("");
  keys.forEach(k => {
    const m = r.metrics[k].confusion_matrix;
    plot(`cm-${k}`, [{ type: "heatmap", z: m, x: ["Stay", "Churn"], y: ["Stay", "Churn"], colorscale: [[0, "#eef2f7"], [1, NAVY]], showscale: false, text: m.map(r => r.map(String)), texttemplate: "%{text}" }],
      { title: { text: r.labels[k], font: { size: 14 } }, xaxis: { title: "Predicted" }, yaxis: { title: "Actual", autorange: "reversed" }, margin: { t: 40, l: 60, b: 50, r: 10 }, height: 300 }, { responsive: true });
  });
}

function initTraining() {
  const btn = $("#btn-train");
  let timer = null;
  async function poll() {
    const r = await api("/api/train/results");
    if (r.job.status === "running") { msg(r.job.message, "info"); return; }
    clearInterval(timer); timer = null; btn.disabled = false;
    if (r.job.status === "error") msg(r.job.error, "err");
    else if (r.job.status === "done") { msg(`Training complete. ${r.job.message}`, "ok"); renderResults(r); refreshStatus(); }
  }
  btn.onclick = async () => {
    const models = [["#m-lr", "lr"], ["#m-lgbm", "lgbm"]].filter(([s]) => $(s).checked).map(([, k]) => k);
    if (!models.length) return msg("Select at least one model.", "err");
    btn.disabled = true; msg("Starting…", "info");
    try { await post("/api/train", { models, smote: $("#m-smote").checked }); timer = setInterval(poll, 1500); }
    catch (e) { msg(e.message, "err"); btn.disabled = false; }
  };
  api("/api/train/results").then(r => { if (r.job.status === "running") { btn.disabled = true; timer = setInterval(poll, 1500); } else renderResults(r); });
  refreshStatus();
}

// ---------- Prediction page ----------
function initPrediction() {
  document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
    $("#tab-single").hidden = t.dataset.tab !== "single";
    $("#tab-batch").hidden = t.dataset.tab !== "batch";
  });
  refreshStatus().then(s => { if (s && !s.model_ready) msg("Train a model first (Training page).", "err"); });

  $("#form-single").onsubmit = async e => {
    e.preventDefault(); msg("");
    const data = Object.fromEntries(new FormData(e.target));
    try {
      const r = await post("/api/predict", data);
      $("#single-result").hidden = false;
      plot("chart-gauge", [{ type: "indicator", mode: "gauge+number", value: r.probability * 100, number: { suffix: "%" }, title: { text: "Churn probability" },
        gauge: { axis: { range: [0, 100] }, bar: { color: RED }, steps: [{ range: [0, 30], color: "#27AE60" }, { range: [30, 60], color: "#F39C12" }, { range: [60, 100], color: "#fadbd8" }] } }],
        { height: 300, margin: { t: 60, b: 20, l: 30, r: 30 } }, { responsive: true });
      const v = $("#verdict"), high = r.prediction === 1;
      v.className = "verdict " + (high ? "high" : "low");
      v.innerHTML = high
        ? `<h3>⚠️ High churn risk</h3><p>Customer is likely to <b>churn</b> (${(r.probability * 100).toFixed(1)}%).</p><p><b>Action:</b> immediate retention contact + offer.</p>`
        : `<h3>✅ Low churn risk</h3><p>Customer is likely to <b>stay</b> (churn probability ${(r.probability * 100).toFixed(1)}%).</p><p><b>Action:</b> maintain engagement.</p>`;
      v.innerHTML += `<p class="muted">Model: ${esc(r.model)} · Risk level: ${esc(r.risk_level)}</p>`;
    } catch (err) { msg(err.message, "err"); }
  };

  $("#btn-batch").onclick = async e => {
    const f = $("#batch-file").files[0];
    if (!f) return msg("Choose a CSV file first.", "err");
    const fd = new FormData(); fd.append("file", f);
    e.target.disabled = true; msg("Scoring…", "info");
    try {
      const r = await api("/api/predict/batch", { method: "POST", body: fd });
      msg("");
      $("#batch-summary").textContent = `${fmt(r.count)} customers scored — ${fmt(r.high_risk)} high risk.` + (r.count > 200 ? " Showing the top 200; download for all rows." : "");
      $("#batch-table").innerHTML = table(r.columns, r.rows, row => "risk-" + row.risk_level);
      $("#btn-download").hidden = false;
    } catch (err) { msg(err.message, "err"); }
    e.target.disabled = false;
  };
}

// ---------- boot ----------
const pages = { data: initData, features: initFeatures, training: initTraining, prediction: initPrediction };
document.addEventListener("DOMContentLoaded", () => (pages[document.body.dataset.page] || refreshStatus)());
