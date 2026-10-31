"use strict";
/* Page logic. One file, one init function per page (chosen from <body data-page>). */

/* ---------- shared: customer form ---------- */
async function applySchema(form) {
  try {
    const { columns } = await api("/api/schema");
    $$("[data-col]", form).forEach((el) => {
      const used = columns.includes(el.dataset.col);
      el.hidden = !used;
      $$("input,select", el).forEach((i) => (i.disabled = !used));
    });
  } catch (_) { /* keep every field visible */ }
}
const formJson = (form) => Object.fromEntries($$("input:not(:disabled),select:not(:disabled)", form).map((i) => [i.name, i.value]));

function wirePredict(formId, goId, resultId, msgSel) {
  const form = $("#" + formId);
  applySchema(form);
  $("#" + goId).onclick = async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true; msg(msgSel, "");
    try { renderResult($("#" + resultId), await post("/api/predict", formJson(form))); }
    catch (err) { msg(msgSel, err.message, "err"); }
    btn.disabled = false;
  };
}

/* ---------- dashboard ---------- */
const REASON_COLORS = ["#ef6a6a", "#f59a76", "#f6c14b", "#3b82f6", "#5b5bd6", "#7f8db3"];

function donut(tiers) {
  const order = ["Low", "Medium", "High"], total = order.reduce((a, t) => a + tiers[t], 0);
  const r = 70, c = 2 * Math.PI * r;
  let offset = 0;
  const arcs = total ? order.map((t) => {
    const len = (tiers[t] / total) * c, arc = `<circle cx="90" cy="90" r="${r}" fill="none" stroke="${TIER_COLOR[t]}" stroke-width="22"
      stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-offset}"/>`;
    offset += len; return arc;
  }).join("") : `<circle cx="90" cy="90" r="${r}" fill="none" stroke="#1d2f57" stroke-width="22"/>`;
  const legend = order.map((t) => `<div class="item"><span class="sw" style="background:${TIER_COLOR[t]}"></span><span>${t} Risk</span>
    <b>${total ? ((tiers[t] / total) * 100).toFixed(1) : "0.0"}%</b><small>${fmt(tiers[t])}</small></div>`).join("");
  $("#donut").innerHTML = `<div class="donut"><svg viewBox="0 0 180 180" role="img" aria-label="Customers by risk level">${arcs}</svg>
    <div class="center"><b>${fmt(total)}</b><small>Active customers<br>scored</small></div></div><div class="legend">${legend}</div>`;
}

function reasons(list, host = "#reasons") {
  const max = Math.max(...list.map((x) => x.share), 0.0001);
  $(host).innerHTML = list.length ? list.map((x, i) => `<div class="reason"><span>${esc(x.label)}</span>
    <div class="bar"><i style="width:${(x.share / max) * 100}%;background:${REASON_COLORS[i % REASON_COLORS.length]}"></i></div>
    <b>${(x.share * 100).toFixed(1)}%</b></div>`).join("") : '<div class="empty">No model yet.</div>';
}

async function initDashboard() {
  const seg = $("#seg");
  async function load() {
    const d = await api("/api/dashboard?segment=" + seg.value), k = d.kpis;
    $("#k-total").textContent = fmt(k.total);
    $("#k-total-n").textContent = `${fmt(k.active)} still active`;
    $("#k-high").textContent = k.high_risk === null ? "–" : fmt(k.high_risk);
    const hn = $("#k-high-n");
    hn.className = "note";
    if (k.high_delta !== null && k.high_delta !== 0) { hn.textContent = `${k.high_delta > 0 ? "+" : ""}${k.high_delta} since the previous run`; hn.classList.add(k.high_delta > 0 ? "up" : "down"); }
    else hn.textContent = d.scored ? `At or above ${d.threshold}% probability` : "Not scored yet";
    $("#k-churn").textContent = pct(k.historical_churn_rate);
    $("#k-ret").textContent = pct(k.retention_rate);
    const nr = $("#not-ready");
    nr.hidden = d.scored;
    if (!d.scored) $("#not-ready-text").textContent = d.model_ready ? "No scoring run yet. Ask an administrator to run scoring." : "No trained model yet. An administrator trains one on the Data & Upload page.";
    const s = d.segment;
    $("#seg-sub").textContent = `${s.title}: customers (bars) and share who left (line)`;
    plot("chart-trend", [
      { type: "bar", x: s.labels, y: s.customers, name: "Customers", marker: { color: "#4553d8" }, hovertemplate: "%{y:,} customers<extra></extra>" },
      { type: "scatter", mode: "lines+markers", x: s.labels, y: s.churn_rate, name: "Churn rate", yaxis: "y2", line: { color: "#5b9dff", width: 3 }, marker: { size: 9 }, hovertemplate: "%{y}% left<extra></extra>" },
    ], { xaxis: { type: "category" }, yaxis: { rangemode: "tozero", title: { text: "Customers" } },
         yaxis2: { overlaying: "y", side: "right", showgrid: false, rangemode: "tozero", ticksuffix: "%", title: { text: "Churn rate" } },
         margin: { t: 10, r: 60, b: 40, l: 60 }, legend: { orientation: "h", x: 1, xanchor: "right", y: 1.15 } });
    donut(d.tiers);
    reasons(d.reasons);
  }
  seg.onchange = () => load().catch((e) => msg("#quick-msg", e.message, "err"));
  load().catch((e) => msg("#quick-msg", e.message, "err"));
  wirePredict("quick-form", "quick-go", "quick-result", "#quick-msg");
}

/* ---------- prediction ---------- */
function initPrediction() {
  wirePredict("single-form", "single-go", "single-result", "#msg");
  $$(".tab").forEach((t) => (t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
    $("#tab-single").hidden = t.dataset.tab !== "single";
    $("#tab-batch").hidden = t.dataset.tab !== "batch";
  }));
  const go = $("#batch-go");
  if (!go) return;
  go.onclick = async () => {
    const f = $("#batch-file").files[0];
    if (!f) return msg("#msg", "Choose a CSV file first.", "err");
    const fd = new FormData(); fd.append("file", f);
    go.disabled = true; msg("#msg", "Scoring…", "info");
    try {
      const r = await api("/api/predict/batch", { method: "POST", body: fd });
      msg("#msg", "");
      $("#batch-summary").textContent = `${fmt(r.count)} customers scored, ${fmt(r.high_risk)} at 60% or more.` + (r.count > 200 ? " Showing the top 200. Download the file for all rows." : "");
      $("#batch-table").innerHTML = table(r.columns, r.rows);
      $("#batch-dl").hidden = false;
    } catch (err) { msg("#msg", err.message, "err"); }
    go.disabled = false;
  };
}

/* ---------- insights ---------- */
function initInsights() {
  let page = 1, current = null;
  const body = $("#cust-table tbody");
  async function load() {
    const q = new URLSearchParams({ page, tier: $("#f-tier").value, products: $("#f-products").value, country: $("#f-country").value });
    const d = await api("/api/customers?" + q);
    body.innerHTML = d.items.length ? d.items.map((c) => `<tr class="click" data-id="${c.id}" tabindex="0">
      <td>${esc(c.ref)}</td><td>${esc(c.country)}</td><td class="num">${fmt(c.products)}</td><td>${c.active === null ? "–" : c.active ? "Yes" : "No"}</td>
      <td><span class="probbar"><i style="width:${c.probability}%;background:${TIER_COLOR[c.tier]}"></i></span>${c.probability.toFixed(1)}%</td>
      <td><span class="badge ${c.tier}">${c.tier}</span></td><td>${esc(c.top_factor)}</td></tr>`).join("")
      : `<tr><td colspan="7"><div class="empty"><b>${d.scored ? "No customers match these filters" : "No scores yet"}</b>${d.scored ? "Change a filter to see more." : "Scores appear after the first scoring run."}</div></td></tr>`;
    $("#pg-info").textContent = d.total ? `Page ${d.page} of ${d.pages} · ${fmt(d.total)} customers` : "";
    $("#pg-prev").disabled = page <= 1; $("#pg-next").disabled = page >= d.pages;
  }
  const reload = () => load().catch((e) => (body.innerHTML = `<tr><td colspan="7"><div class="msg err">${esc(e.message)}</div></td></tr>`));
  ["#f-tier", "#f-products", "#f-country"].forEach((s) => ($(s).onchange = () => { page = 1; reload(); }));
  $("#pg-prev").onclick = () => { page--; reload(); };
  $("#pg-next").onclick = () => { page++; reload(); };

  async function open(id) {
    const d = await api("/api/customers/" + id);
    current = Number(id);
    $("#dr-title").textContent = d.ref;
    $("#dr-profile").innerHTML = Object.entries(d.profile).map(([k, v]) => `<div><dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(typeof v === "number" ? fmt(v) : v)}</dd></div>`).join("");
    const res = $("#dr-result");
    if (d.scored) renderResult(res, d, { onAdd: () => { $("#dr-form").hidden = false; $("#dr-form").scrollIntoView({ behavior: "smooth" }); } });
    else { res.className = "panel"; res.innerHTML = '<div class="empty">This customer has no score yet.</div>'; }
    history(d.history);
    $("#dr-form").hidden = true; msg("#dr-msg", "");
    $("#drawer").hidden = false; $("#dr-close").focus();
  }
  const history = (h) => ($("#dr-history").innerHTML = h.length ? h.map((a) => `<li><b>${esc(a.type)}</b> · ${esc(a.status)}<small>${esc(a.by)} · ${esc(a.created_at)} UTC${a.notes ? " · " + esc(a.notes) : ""}</small></li>`).join("") : '<li class="muted">No actions logged yet.</li>');
  const openFrom = (tr) => tr && open(tr.dataset.id).catch((e) => alert(e.message));
  body.onclick = (e) => openFrom(e.target.closest("tr.click"));
  body.onkeydown = (e) => { if (e.key === "Enter") openFrom(e.target.closest("tr.click")); };
  $("#dr-close").onclick = () => ($("#drawer").hidden = true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });
  $("#dr-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    try { await post("/api/retention/actions", { customer_id: current, ...f }); msg("#dr-msg", "Action logged. Nothing was sent to the customer.", "ok"); e.target.reset(); await open(current); $("#dr-form").hidden = false; msg("#dr-msg", "Action logged. Nothing was sent to the customer.", "ok"); }
    catch (err) { msg("#dr-msg", err.message, "err"); }
  };
  reload();
}

/* ---------- analytics ---------- */
async function initAnalytics() {
  const m = await api("/api/model");
  if (!m.ready) $("#an-empty").hidden = false;
  else {
    $("#an-body").hidden = false;
    const keys = Object.keys(m.metrics);
    if (keys.length) {
      const names = { accuracy: "Accuracy", precision: "Precision", recall: "Recall", f1: "F1", auc: "AUC", ks: "KS" };
      const rows = Object.entries(names).map(([k, label]) => Object.fromEntries([["Metric", label], ...keys.map((x) => [m.labels[x], m.metrics[x][k]])]));
      $("#cmp-table").innerHTML = table(["Metric", ...keys.map((x) => m.labels[x])], rows);
      $("#an-sub").textContent = `Active model: ${m.best_model} (highest AUC). Trained ${m.trained_at} UTC on ${fmt(m.train_rows)} customers, tested on ${fmt(m.test_rows)} unseen ones.`;
      const colors = { lr: "#5b8cff", lgbm: "#ef6a6a" };
      const traces = keys.map((k) => ({ x: m.metrics[k].roc.fpr, y: m.metrics[k].roc.tpr, mode: "lines", name: `${m.labels[k]} (AUC ${m.metrics[k].auc.toFixed(3)})`, line: { color: colors[k], width: 2 } }));
      traces.push({ x: [0, 1], y: [0, 1], mode: "lines", name: "Random", line: { dash: "dash", color: "#5f7399" } });
      plot("chart-roc", traces, { xaxis: { title: "False positive rate" }, yaxis: { title: "True positive rate" }, legend: { orientation: "h", y: -0.25 }, margin: { t: 10, r: 10, b: 60, l: 55 } });
      $("#cm-wrap").innerHTML = keys.map((k) => `<div id="cm-${k}" style="height:260px"></div>`).join("");
      keys.forEach((k) => { const z = m.metrics[k].confusion_matrix;
        plot(`cm-${k}`, [{ type: "heatmap", z, x: ["Stay", "Leave"], y: ["Stay", "Leave"], colorscale: [[0, "#10224a"], [1, "#2f6bff"]], showscale: false, text: z.map((r) => r.map(String)), texttemplate: "%{text}" }],
          { title: { text: m.labels[k], font: { size: 13, color: "#eaf0fb" } }, xaxis: { title: "Predicted" }, yaxis: { title: "Actual", autorange: "reversed" }, margin: { t: 36, l: 60, b: 50, r: 10 } }); });
    } else $("#cmp-table").innerHTML = '<div class="empty">Metrics are saved when a model is trained.</div>';
    reasons(m.importance, "#importance");
  }
  const monthEl = $("#rep-month");
  if (monthEl) {
    monthEl.value = new Date().toISOString().slice(0, 7);
    const loadReport = async () => {
      $("#rep-dl").href = "/api/reports/monthly.csv?month=" + monthEl.value;
      try {
        const r = await api("/api/reports/monthly?month=" + monthEl.value), s = r.snapshot, a = r.activity;
        const rows = [["Customers in portfolio", fmt(r.customers_total)], ["Historical churn rate", pct(r.historical_churn_rate)],
          ...(s ? [["Customers scored", fmt(s.scored)], [`High risk (at or above ${r.alert_threshold}%)`, fmt(s.high_risk)], ["Average churn probability", s.average_probability === null ? "–" : pct(s.average_probability)], ["Model", s.model]] : [["Scoring", "No scoring run up to this month"]]),
          ["Scoring runs this month", fmt(a.scoring_runs)], ["Alerts raised", fmt(a.alerts_created)], ["Alerts acknowledged", fmt(a.alerts_acknowledged)],
          ["Retention actions logged", fmt(a.retention_actions_logged)], ["Retention actions done", fmt(a.retention_actions_done)],
          ...r.churn_by_products.map((p) => [`Churn rate, ${p.products} product(s)`, `${pct(p.churn_rate)} of ${fmt(p.customers)} customers`])];
        $("#rep-body").innerHTML = `<table><tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${esc(v)}</td></tr>`).join("")}</tbody></table>`;
      } catch (e) { $("#rep-body").innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
    };
    monthEl.onchange = loadReport; loadReport();
  }
}

/* ---------- retention ---------- */
function initRetention() {
  const alBody = $("#al-table tbody"), acBody = $("#ac-table tbody");
  async function load() {
    const [al, ac] = await Promise.all([api("/api/alerts"), api("/api/retention/actions")]);
    alBody.innerHTML = al.items.length ? al.items.map((a) => `<tr><td>${esc(a.ref)}</td><td class="num">${a.probability.toFixed(1)}%</td><td>${esc(a.rm || "Unassigned")}</td><td>${esc(a.created_at)} UTC</td>
      <td><span class="badge ${a.status === "new" ? "new" : "neutral"}">${a.status}</span></td>
      <td>${a.status === "new" ? `<button class="btn ghost small" data-ack="${a.id}">Acknowledge</button>` : ""}</td></tr>`).join("")
      : '<tr><td colspan="6"><div class="empty"><b>No alerts</b>Alerts appear after a scoring run finds customers above the threshold.</div></td></tr>';
    acBody.innerHTML = ac.items.length ? ac.items.map((a) => `<tr><td>${esc(a.ref)}</td><td>${esc(a.type)}</td><td>${esc(a.notes)}</td><td>${esc(a.by)}</td><td>${esc(a.created_at)} UTC</td>
      <td><span class="badge ${a.status === "done" ? "Low" : "neutral"}">${a.status}</span></td>
      <td><button class="btn ghost small" data-act="${a.id}" data-to="${a.status === "done" ? "planned" : "done"}">${a.status === "done" ? "Reopen" : "Mark done"}</button></td></tr>`).join("")
      : '<tr><td colspan="7"><div class="empty"><b>No actions logged yet</b>Open a customer in Customer Insights and choose Add to Retention Campaign.</div></td></tr>';
  }
  const run = (p) => p.then(load).catch((e) => msg("#msg", e.message, "err"));
  alBody.onclick = (e) => { const id = e.target.dataset.ack; if (id) run(post(`/api/alerts/${id}/ack`)); };
  acBody.onclick = (e) => { const id = e.target.dataset.act; if (id) run(patch(`/api/retention/actions/${id}`, { status: e.target.dataset.to })); };
  const ex = $("#ex-go");
  if (ex) ex.onclick = () => { ex.href = "/api/export/high-risk.csv?" + new URLSearchParams({ tier: $("#ex-tier").value, products: $("#ex-products").value, country: $("#ex-country").value }); };
  run(Promise.resolve());
}

/* ---------- data & upload ---------- */
async function renderData() {
  const d = await api("/api/data/summary");
  $("#data-view").hidden = false;
  $("#data-metrics").innerHTML = [["Customers", fmt(d.rows)], ["Columns", d.columns], ["Missing values", fmt(d.missing)], ["Churn rate", pct(d.churn_rate === null ? null : d.churn_rate * 100)]]
    .map(([l, v]) => `<div class="panel kpi"><div><div class="label">${l}</div><div class="value">${v}</div></div></div>`).join("");
  $("#head-table").innerHTML = table(Object.keys(d.head[0]), d.head);
  plot("chart-pie", [{ type: "pie", labels: d.churn_counts.labels, values: d.churn_counts.values, hole: 0.55, marker: { colors: ["#3b82f6", "#ef5b5b"] }, textfont: { color: "#fff" } }], { margin: { t: 10, b: 10, l: 10, r: 10 } });
  plot("chart-corr", [{ type: "heatmap", z: d.correlation.matrix, x: d.correlation.labels, y: d.correlation.labels, colorscale: "RdBu", zmid: 0, reversescale: true }], { margin: { t: 10, l: 110, b: 110, r: 10 } });
}

function initData() {
  const loaded = async (r) => { msg("#msg", `${r.source}: ${fmt(r.rows)} customers read (${fmt(r.new)} new).`, "ok"); await renderData(); refreshStatus(); };
  $("#btn-upload").onclick = async () => {
    const f = $("#csv-file").files[0];
    if (!f) return msg("#msg", "Choose a CSV file first.", "err");
    const fd = new FormData(); fd.append("file", f);
    try { await loaded(await api("/api/data/upload", { method: "POST", body: fd })); } catch (e) { msg("#msg", e.message, "err"); }
  };
  $("#btn-sample").onclick = async () => { try { await loaded(await post("/api/data/sample")); } catch (e) { msg("#msg", e.message, "err"); } };
  $("#btn-features").onclick = async (e) => {
    const b = e.currentTarget;
    b.disabled = true; msg("#msg", "Creating features…");
    try {
      const r = await post("/api/features");
      $("#feat-summary").textContent = `${r.n_features} features. ${fmt(r.train_rows)} customers to learn from, ${fmt(r.test_rows)} kept aside to test.`;
      $("#feat-list").innerHTML = r.features.map((f) => `<span>${esc(f)}</span>`).join("");
      msg("#msg", "Features are ready. Next, train the models.", "ok");
    } catch (err) { msg("#msg", err.message, "err"); }
    b.disabled = false;
  };
  const btn = $("#btn-train");
  let timer = null;
  async function poll() {
    const r = await api("/api/model");
    if (r.job.status === "running") return msg("#msg", r.job.message, "info");
    clearInterval(timer); timer = null; btn.disabled = false;
    if (r.job.status === "error") msg("#msg", r.job.error, "err");
    else if (r.job.status === "done") { msg("#msg", `Training complete. ${r.job.message}. Customers were scored with the new model.`, "ok"); refreshStatus(); }
  }
  btn.onclick = async () => {
    const models = [["#m-lr", "lr"], ["#m-lgbm", "lgbm"]].filter(([s]) => $(s).checked).map(([, k]) => k);
    if (!models.length) return msg("#msg", "Select at least one model.", "err");
    btn.disabled = true; msg("#msg", "Starting…", "info");
    try { await post("/api/train", { models, smote: $("#m-smote").checked }); timer = setInterval(() => poll().catch(() => {}), 1500); }
    catch (e) { msg("#msg", e.message, "err"); btn.disabled = false; }
  };
  renderData().catch(() => {});
}

/* ---------- administration ---------- */
function initAdmin() {
  const run = (p, ok) => p.then((r) => { if (ok) msg("#msg", ok(r), "ok"); }).catch((e) => msg("#msg", e.message, "err"));
  async function loadAll() {
    const [thr, jobs, users, audit] = await Promise.all([api("/api/admin/settings"), api("/api/admin/jobs"), api("/api/admin/users"), api("/api/admin/audit?limit=80")]);
    $("#thr").value = thr.alert_threshold;
    $("#jobs tbody").innerHTML = jobs.items.map((j) => `<tr><td>${j.id}</td><td>${esc(j.started_at)}</td><td>${esc(j.trigger)}</td><td>${esc(j.model_name || "–")}</td><td class="num">${fmt(j.customers_scored)}</td><td class="num">${fmt(j.high_risk_count)}</td><td class="num">${j.duration_s ?? "–"}</td><td><span class="badge ${j.status === "done" ? "Low" : j.status === "failed" ? "High" : "neutral"}">${j.status}</span></td></tr>`).join("") || '<tr><td colspan="8"><div class="empty">No scoring run yet.</div></td></tr>';
    $("#users tbody").innerHTML = users.items.map((u) => `<tr><td>${esc(u.username)}<br><small class="muted">${esc(u.name)}</small></td><td>${esc(users.roles[u.role])}</td><td>${esc(u.branch || "–")}</td>
      <td><button class="btn ghost small" data-uid="${u.id}" data-active="${u.active ? 0 : 1}">${u.active ? "Deactivate" : "Activate"}</button></td></tr>`).join("");
    $("#audit tbody").innerHTML = audit.items.map((a) => `<tr><td>${esc(a.ts)}</td><td>${esc(a.user || "–")}</td><td>${esc(a.action)}</td><td>${esc(a.customer || "")}</td></tr>`).join("");
  }
  $("#thr-save").onclick = () => run(post("/api/admin/settings", { alert_threshold: $("#thr").value }), (r) => `Threshold saved: ${r.alert_threshold}%. It applies from the next scoring run.`);
  $("#score-go").onclick = async (e) => {
    const b = e.currentTarget;
    b.disabled = true; msg("#msg", "Scoring…", "info");
    await run(post("/api/admin/score"), (r) => `Scored ${fmt(r.customers_scored)} customers in ${r.duration_s} s. ${fmt(r.high_risk)} at or above the threshold.`);
    b.disabled = false; loadAll();
  };
  $("#users").onclick = (e) => { const id = e.target.dataset.uid; if (id) run(post(`/api/admin/users/${id}/active`, { active: e.target.dataset.active === "1" })).then(loadAll); };
  $("#user-form").onsubmit = (e) => { e.preventDefault(); run(post("/api/admin/users", Object.fromEntries(new FormData(e.target))), () => "User added.").then(() => { e.target.reset(); loadAll(); }); };
  loadAll().catch((e) => msg("#msg", e.message, "err"));
}

document.addEventListener("DOMContentLoaded", () => {
  const init = { dashboard: initDashboard, prediction: initPrediction, insights: initInsights, analytics: initAnalytics, retention: initRetention, data: initData, admin: initAdmin }[document.body.dataset.page];
  if (init) Promise.resolve(init()).catch((e) => msg("#msg", e.message, "err"));
});
