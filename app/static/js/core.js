"use strict";
/* Shared helpers for every page: fetch with CSRF, formatting, charts theme, result panel. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const TIER_COLOR = { Low: "#22c58b", Medium: "#f6b93b", High: "#ef5b5b" };
const csrf = () => $('meta[name="csrf-token"]').content;

async function api(url, opts = {}) {
  opts.headers = { ...(opts.headers || {}), "X-CSRF-Token": csrf() };
  const res = await fetch(url, opts);
  if (res.status === 401) { location.href = "/login"; throw new Error("Sign in required."); }
  let body = {};
  try { body = await res.json(); } catch (_) { /* download or empty body */ }
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}
const send = (method) => (url, data) => api(url, {
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}),
});
const post = send("POST");
const patch = send("PATCH");

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => (n === null || n === undefined ? "–" : Number(n).toLocaleString("en-US"));
const pct = (n, d = 1) => (n === null || n === undefined ? "–" : `${Number(n).toFixed(d)}%`);
const icon = (name, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

function msg(host, text, kind = "info") {
  const el = typeof host === "string" ? $(host) : host;
  if (!el) return;
  el.className = "msg " + (text ? kind : "");
  el.textContent = text || "";
  el.setAttribute("role", kind === "err" ? "alert" : "status");
}

function table(cols, rows) {
  const head = cols.map((c) => `<th>${esc(c)}</th>`).join("");
  const body = rows.map((r) => `<tr>${cols.map((c) => {
    const v = r[c];
    return `<td>${esc(typeof v === "number" && !Number.isInteger(v) ? +v.toFixed(4) : v)}</td>`;
  }).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ---------- charts (Plotly, dark theme) ---------- */
function plot(id, data, layout = {}, config = {}) {
  const el = document.getElementById(id);
  if (!window.Plotly) {
    if (el) el.innerHTML = '<div class="empty"><b>Charts could not load</b>Check your internet connection and reload.</div>';
    return;
  }
  const base = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#aebbd6", family: "Segoe UI, system-ui, sans-serif", size: 12 },
    margin: { t: 10, r: 10, b: 40, l: 45 },
    xaxis: { gridcolor: "#14264b", zerolinecolor: "#14264b", linecolor: "#243b6b" },
    yaxis: { gridcolor: "#14264b", zerolinecolor: "#14264b", linecolor: "#243b6b" },
    legend: { orientation: "h", font: { color: "#aebbd6" } },
  };
  const merged = { ...base, ...layout,
    xaxis: { ...base.xaxis, ...(layout.xaxis || {}) }, yaxis: { ...base.yaxis, ...(layout.yaxis || {}) } };
  Plotly.newPlot(id, data, merged, { responsive: true, displayModeBar: false, ...config });
}

/* ---------- prediction result panel (dashboard, prediction page, customer drawer) ---------- */
function ringSvg(value, color) {
  const c = 2 * Math.PI * 40;
  return `<div class="ring"><svg viewBox="0 0 100 100" aria-hidden="true">
    <circle cx="50" cy="50" r="40" fill="none" stroke="#1d2f57" stroke-width="9"/>
    <circle cx="50" cy="50" r="40" fill="none" stroke="${color}" stroke-width="9" stroke-linecap="round"
      stroke-dasharray="${(c * value) / 100} ${c}"/></svg><b>${Math.round(value)}%</b></div>`;
}

function renderResult(host, r, opts = {}) {
  const color = TIER_COLOR[r.tier];
  const title = { High: "High Risk of Churn", Medium: "Medium Risk of Churn", Low: "Low Risk of Churn" }[r.tier];
  const factors = (r.factors || []).map((f) => `<li><span class="${f.direction === "raises" ? "up" : "down"}">${f.direction === "raises" ? "▲" : "▼"}</span>
      <span>${esc(f.label)} (${esc(f.value)}) ${f.direction === "raises" ? "raises" : "lowers"} the risk</span></li>`).join("");
  const actions = (r.actions || []).map((a) => `<li>${esc(a)}</li>`).join("");
  host.className = `panel result ${r.tier}`;
  host.hidden = false;
  host.innerHTML = `
    <div class="head"><span class="ico">${icon(r.tier === "Low" ? "check-circle" : "warning")}</span>
      <div><h3>Prediction Result</h3><small>${title}</small></div></div>
    <div class="ring-row">${ringSvg(r.probability, color)}
      <p>The model gives this customer a <b>${r.probability.toFixed(1)}%</b> probability of churning.</p></div>
    ${factors ? `<h4 style="margin:0 0 8px;font-size:14px">Main reasons</h4><ul class="factors">${factors}</ul>` : ""}
    <div class="actions-box"><h4>${icon("bulb", "sm")}Recommended Actions</h4><ul>${actions}</ul>
      <p class="note">Suggestions only. Nothing is sent to the customer without a person's approval.</p></div>
    ${opts.onAdd ? `<button class="btn ghost block" type="button" id="add-campaign">${icon("calendar", "sm")}Add to Retention Campaign</button>` : ""}`;
  if (opts.onAdd) $("#add-campaign", host).onclick = opts.onAdd;
}

/* ---------- shell: model status, user menu ---------- */
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("#ms-dot").classList.toggle("on", s.model.ready);
    const t = $("#ms-text");
    t.textContent = s.model.ready ? "Online" : "Not trained";
    t.classList.toggle("on-text", s.model.ready);
    const stamp = (s.last_run && s.last_run.finished_at) || s.model.trained_at;
    $("#ms-updated").textContent = stamp ? `Last updated: ${stamp} UTC` : "";
    $("#last-updated").textContent = stamp ? `Last updated: ${stamp} UTC` : "";
    return s;
  } catch (_) { return null; }
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = $("#user-btn"), menu = $("#user-menu");
  btn.onclick = (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; btn.setAttribute("aria-expanded", String(!menu.hidden)); };
  document.addEventListener("click", () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); });
  refreshStatus();
});
