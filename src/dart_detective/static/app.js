/* 공시 탐정사무소 — 프론트엔드.
 *
 * 역할 분리:
 *   프론트   화면 전환 / 애니메이션 / 선택 UI / 열어본 탭
 *   Backend  게임 진행 상태 · Evidence · 검색 · 학습 용어 · Decision · Future Unlock
 * 프론트는 게임 상태를 스스로 만들지 않는다. 항상 서버 응답의 state를 반영한다.
 *
 * 장애 격리:
 *   research/hint(Agent 호출)가 실패해도 메인 루프(문서 열람 → 단서 수집 → 판단 → Replay)는
 *   계속 진행된다. Agent 실패는 조수 말풍선 안에서만 표시된다.
 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const S = {
  sessionId: null,
  briefing: null,
  state: null,
  evidence: [],      // 수집한 단서 상세
  terms: [],         // 금융용어 목록(잠금 여부 포함)
  docCache: {},      // document_id -> open_document 응답
  lastEvidence: null,
  decisionRecord: null,
};

/* ------------------------------------------------------------------ 유틸 */
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

async function api(path, options) {
  try {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return { ok: false, error: data.detail || `HTTP ${res.status}` };
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: "서버에 연결하지 못했습니다 (" + err.message + ")" };
  }
}

const act = (action, payload = {}) =>
  api(`/sessions/${S.sessionId}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...payload }),
  });

function show(id) {
  $$(".screen").forEach((s) => s.classList.toggle("active", s.id === id));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openDrawer(id) {
  $$(".drawer").forEach((d) => d.classList.toggle("open", d.id === id));
  $("#backdrop").classList.add("on");
}
function closeDrawers() {
  $$(".drawer").forEach((d) => d.classList.remove("open"));
  $("#backdrop").classList.remove("on");
}

/* ------------------------------------------------------------------ 상태 반영 */
function applyState(state) {
  if (!state) return;
  S.state = state;

  const box = $("#pointsBox");
  if (state.points_enabled) {
    box.hidden = false;
    $("#pointsText").textContent = state.investigation_points;
    $("#pointsBar").style.width = Math.max(0, Math.min(100, state.investigation_points)) + "%";
  } else {
    box.hidden = true;
  }
  $("#btnBoard").dataset.count = state.found_evidence.length;
  $("#btnNotebook").dataset.count = (S.terms.filter((t) => t.unlocked) || []).length;
}

async function refreshEvidence() {
  const r = await api(`/sessions/${S.sessionId}/evidence`);
  if (!r.ok) return;
  S.evidence = r.data.evidence;
  $("#deskProgress").textContent = `단서 ${S.evidence.length} / ${r.data.total}`;
  renderBoard();
}

async function refreshTerms() {
  const r = await act("term");
  if (!r.ok) return;
  const found = new Set(S.state ? S.state.found_evidence : []);
  S.terms = r.data.response.terms.map((t) => ({
    ...t,
    unlocked: t.source_evidence_ids.some((e) => found.has(e)),
  }));
  applyState(r.data.state);
  renderTerms();
}

/* ------------------------------------------------------------------ 화면 0. 사건 선택 */
async function loadCases() {
  const r = await api("/cases");
  const grid = $("#caseGrid");
  if (!r.ok) {
    grid.innerHTML = `<div class="card">사건 목록을 불러오지 못했습니다.<br><span class="tiny muted">${esc(r.error)}</span></div>`;
    return;
  }
  grid.innerHTML = "";
  r.data.cases.forEach((c, i) => {
    const b = document.createElement("button");
    b.className = "case-card";
    b.innerHTML = `
      <span class="folder-tab">CASE ${String(i + 1).padStart(2, "0")}</span>
      <h3>${esc(c.case_title || c.case_id)}</h3>
      <div class="small muted">${esc(c.company || "")} · 시점 ${esc(c.simulation_date || "")}</div>
      <div class="row mt-s">
        <span class="pill optional">난이도 ${esc(c.difficulty || "normal")}</span>
        <span class="pill finance">문서 ${c.n_available_documents ?? "-"}</span>
        <span class="pill critical">단서 ${c.n_evidence ?? "-"}</span>
      </div>`;
    b.onclick = () => startCase(c.case_id);
    grid.appendChild(b);
  });
}

/* ------------------------------------------------------------------ 화면 1. 사건 파일 */
async function startCase(caseId) {
  const r = await api("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId, points_enabled: $("#optPoints").checked }),
  });
  if (!r.ok) { toast(r.error, "bad"); return; }

  S.sessionId = r.data.session_id;
  S.briefing = r.data.briefing;
  S.docCache = {};
  S.evidence = [];
  S.lastEvidence = null;
  S.decisionRecord = null;
  applyState(r.data.state);

  const b = S.briefing;
  $("#topSub").textContent = `${b.company.listed_name} · 조사 시점 ${b.simulation_date}`;
  $("#cfNo").textContent = `CASE ${b.case_id.replace("CASE-", "")}`;
  $("#cfTitle").textContent = `${b.company.listed_name} — ${b.case_title}`;
  $("#cfDate").textContent = `📅 ${b.simulation_date}`;
  $("#cfIntro").textContent = b.intro;
  $("#cfMission").textContent = b.mission;

  ["btnNotebook", "btnBoard", "btnAssistant", "btnReset"].forEach((id) => ($("#" + id).hidden = false));
  $("#chat").innerHTML = "";
  botSay("안녕! 나는 조수 단서야. 서류를 읽다 막히면 왼쪽 버튼으로 불러줘.");

  await refreshTerms();
  await refreshEvidence();
  show("screen-casefile");
}

/* ------------------------------------------------------------------ 화면 2. 조사실 */
function renderDesk() {
  const grid = $("#deskGrid");
  grid.innerHTML = "";
  const clips = ["📎", "📌", "🔖", "📁", "🗒️", "📄"];
  S.briefing.documents.forEach((d, i) => {
    const opened = (S.state.opened_documents || []).includes(d.document_id);
    const inDoc = S.evidence.filter((e) => e.document_id === d.document_id).length;
    const b = document.createElement("button");
    b.className = "doc-card" + (opened ? " opened" : "");
    b.innerHTML = `
      <span class="clip">${clips[i % clips.length]}</span>
      <span class="date">${esc(d.document_date)}</span>
      <h4>${esc(d.title)}</h4>
      <div class="tiny muted">${esc(d.source_type)} · ${esc(d.role || "")}</div>
      <div class="excerpt">${esc(d.display_excerpt)}</div>
      ${inDoc ? `<span class="found">단서 ${inDoc}개 수집</span>` : ""}`;
    b.onclick = () => openDocument(d.document_id);
    grid.appendChild(b);
  });
}

/* ------------------------------------------------------------------ 화면 3. 공시 읽기 */
async function openDocument(documentId, collect) {
  const payload = { document_id: documentId };
  if (collect) payload.collect = collect;
  const r = await act("open_document", payload);
  if (!r.ok) { toast(r.error, "bad"); return; }

  S.docCache[documentId] = r.data.response;
  applyState(r.data.state);
  await refreshEvidence();

  const doc = r.data.response;
  $("#docTitle").textContent = doc.title;
  $("#docMeta").textContent = `${doc.document_date} · 형광펜 문장 ${doc.evidence_options.length}개`;
  $("#docBody").innerHTML = renderDocBody(doc.original_text, doc.evidence_options);
  $$("#docBody mark.clue").forEach((m) => {
    m.onclick = () => collectClue(documentId, m.dataset.eid, m);
  });
  show("screen-doc");
}

function renderDocBody(text, options) {
  const spans = [];
  options.forEach((o) => {
    const i = text.indexOf(o.source_text);
    if (i >= 0) spans.push({ s: i, e: i + o.source_text.length, o });
  });
  spans.sort((a, b) => a.s - b.s);

  let out = "", cur = 0;
  for (const sp of spans) {
    if (sp.s < cur) continue;                       // 겹치는 하이라이트는 앞선 것만 남긴다
    out += esc(text.slice(cur, sp.s));
    out += `<mark class="clue${sp.o.collected ? " collected" : ""}" data-eid="${sp.o.evidence_id}">` +
           esc(text.slice(sp.s, sp.e)) + "</mark>";
    cur = sp.e;
  }
  return out + esc(text.slice(cur));
}

async function collectClue(documentId, evidenceId, markEl) {
  if (markEl.classList.contains("collected")) return;
  const before = new Set(S.state.found_evidence);
  const r = await act("open_document", { document_id: documentId, collect: [evidenceId] });
  if (!r.ok) { toast(r.error, "bad"); return; }

  applyState(r.data.state);
  const opt = (r.data.response.evidence_options || []).find((o) => o.evidence_id === evidenceId);
  markEl.classList.add("collected");
  flyToNotebook(markEl, opt ? opt.text : "단서");
  await refreshEvidence();

  if (opt) {
    S.lastEvidence = opt;
    toast("🔍 단서 획득 — " + opt.text.slice(0, 40), "good");
  }
  const newly = S.state.found_evidence.filter((e) => !before.has(e));
  await unlockTermsFor(newly);
}

function flyToNotebook(fromEl, label) {
  const target = $("#btnNotebook").getBoundingClientRect();
  const src = fromEl.getBoundingClientRect();
  const card = document.createElement("div");
  card.className = "fly-card";
  card.textContent = "🔍 " + label.slice(0, 22);
  card.style.left = src.left + "px";
  card.style.top = src.top + "px";
  document.body.appendChild(card);
  requestAnimationFrame(() => {
    card.style.transform =
      `translate(${target.left - src.left}px, ${target.top - src.top}px) scale(.35)`;
    card.style.opacity = "0";
  });
  setTimeout(() => card.remove(), 800);
}

async function unlockTermsFor(newEvidenceIds) {
  if (!newEvidenceIds.length) return;
  const wasUnlocked = new Set(S.terms.filter((t) => t.unlocked).map((t) => t.term));
  await refreshTerms();
  const nowUnlocked = S.terms.filter((t) => t.unlocked && !wasUnlocked.has(t.term));
  nowUnlocked.forEach((t) => {
    toast("📖 금융용어 발견 — " + t.term, "good");
    const row = $(`[data-term="${CSS.escape(t.term)}"]`);
    if (row) row.classList.add("sparkle");
  });
}

/* ------------------------------------------------------------------ 화면 4. 금융수첩 */
function renderTerms() {
  const list = $("#termList");
  list.innerHTML = "";
  S.terms.forEach((t) => {
    const learned = (S.state.learned_terms || []).includes(t.term);
    const row = document.createElement("button");
    row.className = "term-row " + (t.unlocked ? "found" : "locked");
    row.dataset.term = t.term;
    row.innerHTML = `<span>${t.unlocked ? "📖" : "🔒"}</span>
      <strong>${esc(t.term)}</strong>
      <span class="state">${t.unlocked ? (learned ? "학습함" : "발견") : "잠김"}</span>`;
    if (t.unlocked) row.onclick = () => showTerm(t.term);
    list.appendChild(row);
  });
  $("#btnNotebook").dataset.count = S.terms.filter((t) => t.unlocked).length;
}

async function showTerm(term) {
  const r = await act("term", { term });
  if (!r.ok) { toast(r.error, "bad"); return; }
  applyState(r.data.state);
  const t = r.data.response.term;
  $("#termDetail").innerHTML = `
    <div class="term-detail">
      <h4>📖 ${esc(t.term)}</h4>
      <div class="small">${esc(t.short_definition)}</div>
      <div class="why"><strong class="small">이번 사건에서는</strong>
        <div class="small">${esc(t.why_it_matters_here)}</div></div>
    </div>`;
  renderTerms();
}

/* ------------------------------------------------------------------ 화면 5. 사건 단서판 */
const BOARD_OF = { finance: "fin", investment: "fin", business: "biz", timeline: "biz", risk: "rsk" };

function renderBoard() {
  const cols = { fin: $("#boardFin"), biz: $("#boardBiz"), rsk: $("#boardRsk") };
  Object.values(cols).forEach((c) => (c.innerHTML = ""));
  S.evidence.forEach((e) => {
    const key = BOARD_OF[e.category] || "fin";
    const note = document.createElement("div");
    note.className = "sticky-note " + key;
    note.innerHTML = `${esc(e.text)}
      <span class="why">${esc(e.educational_reason)}</span>`;
    cols[key].appendChild(note);
  });
  Object.entries(cols).forEach(([k, c]) => {
    if (!c.children.length) c.innerHTML = `<div class="tiny muted">아직 없음</div>`;
  });
  $("#btnBoard").dataset.count = S.evidence.length;
}

/* ------------------------------------------------------------------ 화면 6. AI 탐정 조수 */
function botSay(html, extraClass = "") {
  const el = document.createElement("div");
  el.className = "msg bot " + extraClass;
  el.innerHTML = html;
  $("#chat").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return el;
}
function userSay(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.textContent = text;
  $("#chat").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function askHint() {
  const pending = botSay("음... 어디를 봐야 할지 생각 중이야 🐾");
  const r = await act("hint");
  if (!r.ok) {
    pending.className = "msg bot warn";
    pending.innerHTML = `힌트를 못 가져왔어(${esc(r.error)}). 그래도 조사는 계속할 수 있어 — ` +
                        `단서판에서 비어 있는 칸을 먼저 채워볼까?`;
    return;
  }
  applyState(r.data.state);
  const h = r.data.response;
  pending.innerHTML =
    `<span class="tiny muted">힌트 Level ${h.level} / 3</span>
     <div class="answer mt-s">${esc(h.hint)}</div>` +
    (h.remaining_critical.length
      ? `<div class="cites">아직 못 찾은 핵심 단서 ${h.remaining_critical.length}개</div>` : "");
}

function explainNumber() {
  const e = S.lastEvidence || S.evidence[S.evidence.length - 1];
  if (!e) {
    botSay("아직 모은 단서가 없어! 서류에서 형광펜 문장을 먼저 눌러줘 ✏️", "warn");
    return;
  }
  // 이 답변은 Case Pack 데이터라 LLM 없이도 항상 동작한다.
  const doc = S.briefing.documents.find((d) => d.document_id === e.document_id);
  const where = doc ? `${doc.document_id} ${doc.title}` : (e.document_id || "수집한 공시");
  botSay(`<div class="answer"><strong>${esc(e.text)}</strong></div>
          <div class="answer mt-s">${esc(e.educational_reason)}</div>
          <div class="cites">출처 ${esc(where)}</div>`);
}

async function askFree(question) {
  userSay(question);
  const pending = botSay("공시를 뒤져보는 중... 🔎");
  const r = await act("research", { question });
  if (!r.ok) {
    pending.className = "msg bot warn";
    pending.innerHTML = `지금은 검색을 못 했어(${esc(r.error)}). 조사실로 돌아가서 서류를 직접 읽어도 돼!`;
    return;
  }
  applyState(r.data.state);
  const res = r.data.response;
  const cites = (res.evidence || []).slice(0, 4)
    .map((c) => `<code>[${esc(c.document_id)}] ${esc(c.quote_or_fact.slice(0, 110))}</code>`).join("");
  pending.innerHTML =
    `<div class="answer">${esc(res.answer)}</div>` +
    (res.uncertainty ? `<div class="cites">❓ ${esc(res.uncertainty)}</div>` : "") +
    (cites ? `<div class="cites"><strong>근거 공시</strong>${cites}</div>` : "") +
    `<span class="badge ${esc(res.validation.status)}">${esc(res.validation.status)}</span>`;

  if (res.newly_collected && res.newly_collected.length) {
    toast(`🔍 조사 중 단서 ${res.newly_collected.length}개 발견`, "good");
    await refreshEvidence();
    await refreshTerms();
  }
}

/* ------------------------------------------------------------------ 화면 7. 판단 */
function renderDecision() {
  const wrap = $("#decEvidence");
  if (!S.evidence.length) {
    wrap.innerHTML = `<div class="card mt-s">아직 단서가 없습니다. 조사실에서 서류를 읽어보세요.</div>`;
  } else {
    wrap.innerHTML = `<div class="mt-s">` + S.evidence.map((e) =>
      `<div class="sticky-note ${BOARD_OF[e.category] || "fin"}">
         <span class="pill ${esc(e.category)}">${esc(e.category)}</span>
         <span class="pill ${esc(e.importance)}">${esc(e.importance)}</span><br>${esc(e.text)}
       </div>`).join("") + `</div>`;
  }

  const grid = $("#optionGrid");
  grid.innerHTML = "";
  S.briefing.decision_options.forEach((o) => {
    const b = document.createElement("button");
    b.className = "option-card";
    b.innerHTML = `<strong>${esc(o.label)}</strong><span>${esc(o.description)}</span>`;
    b.onclick = () => submitDecision(o.option_id);
    grid.appendChild(b);
  });
  $("#decResult").hidden = S.decisionRecord === null;
  if (S.decisionRecord) renderDecisionResult(S.decisionRecord);
  show("screen-decision");
}

async function submitDecision(optionId) {
  const r = await act("decision", { option_id: optionId });
  if (!r.ok) { toast(r.error, "bad"); return; }
  applyState(r.data.state);
  S.decisionRecord = r.data.response;
  renderDecisionResult(S.decisionRecord);
  $("#decResult").hidden = false;
  $("#decResult").scrollIntoView({ behavior: "smooth" });
  toast("⚖️ 판단이 기록되었습니다", "good");
}

function renderDecisionResult(rec) {
  const cov = $("#covList");
  cov.innerHTML = "";
  Object.entries(rec.investigation_summary).forEach(([label, v]) => {
    if (label === "critical_coverage") return;
    const ratio = v.total ? v.checked / v.total : 0;
    const cls = ratio >= 1 ? "full" : ratio > 0 ? "part" : "none";
    const verdict = ratio >= 1 ? "충분히 조사" : ratio > 0 ? "일부 조사" : "조사 부족";
    cov.insertAdjacentHTML("beforeend", `
      <div class="cov-row ${cls}">
        <span class="label">${esc(label)}</span>
        <span class="track"><i style="width:${Math.round(ratio * 100)}%"></i></span>
        <span class="verdict">${verdict}</span>
      </div>`);
  });
  const cc = rec.investigation_summary.critical_coverage;
  cov.insertAdjacentHTML("beforeend",
    `<div class="tiny muted mt-s">핵심 단서 ${cc.checked} / ${cc.total} 확인</div>`);

  $("#fbList").innerHTML = rec.feedback.map((f) => `<li>${esc(f)}</li>`).join("");
  $("#decNote").textContent = rec.note;
}

/* ------------------------------------------------------------------ 화면 8. Replay */
async function openReplay() {
  const r = await act("replay");
  if (!r.ok) {
    $("#replayLock").classList.add("shake");
    setTimeout(() => $("#replayLock").classList.remove("shake"), 600);
    toast(r.error, "warn");
    show("screen-replay");
    return;
  }
  applyState(r.data.state);
  const res = r.data.response;

  $("#replayLock").hidden = true;
  $("#replayOpen").hidden = false;

  const tl = $("#timeline");
  tl.innerHTML = "";
  const items = [{
    mine: true,
    date: res.simulation_date,
    title: "당신의 선택",
    body: res.your_decision,
    changes: [],
  }].concat(res.future_events.map((e) => ({
    mine: false,
    date: e.date,
    title: e.report_nm || "실제 공시",
    body: e.event,
    changes: e.changed_fields || [],
  })));

  items.forEach((it, i) => {
    const el = document.createElement("div");
    el.className = "tl-item" + (it.mine ? " mine" : "");
    el.style.animationDelay = i * 0.45 + "s";
    el.innerHTML = `
      <span class="tl-date">${esc(it.date)}</span>
      <div class="tl-card">
        <h4>${it.mine ? "🕵️ " : "🏢 "}${esc(it.title)}</h4>
        <div class="small">${esc(it.body)}</div>
        ${it.changes.map((c) =>
          `<div class="tl-change">${esc(c.field)} : ${esc(c.before)} → ${esc(c.after)}</div>`).join("")}
      </div>`;
    tl.appendChild(el);
  });

  show("screen-replay");
  toast("🔓 Reality Replay 잠금 해제", "good");
}

/* ------------------------------------------------------------------ 화면 9. 완료 */
function renderComplete() {
  $("#cpTitle").textContent = `${S.briefing.company.listed_name} — ${S.briefing.case_title}`;

  const learned = S.state.learned_terms || [];
  $("#cpTerms").innerHTML = S.terms.map((t) =>
    `<span class="chip ${t.unlocked ? "" : "off"}">${t.unlocked ? "📖" : "🔒"} ${esc(t.term)}</span>`
  ).join("") + (learned.length
    ? `<div class="tiny muted mt-s">그중 ${learned.length}개는 수첩에서 자세히 읽었습니다.</div>` : "");

  const sum = S.decisionRecord ? S.decisionRecord.investigation_summary : {};
  const done = (label) => sum[label] && sum[label].checked > 0;
  const acts = [
    ["정보 탐색", (S.state.opened_documents || []).length > 0],
    ["숫자 비교", done("재무여력 조사") || done("투자규모 조사")],
    ["위험 확인", done("위험 조사")],
    ["판단 수정 가능성 확인", done("판단 수정 가능성")],
  ];
  $("#cpInvest").innerHTML = acts.map(([k, ok]) =>
    `<span class="chip ${ok ? "" : "off"}">${ok ? "✔" : "·"} ${k}</span>`).join("");

  show("screen-complete");
}

/* ------------------------------------------------------------------ 이벤트 배선 */
function wire() {
  $("#btnStart").onclick = () => { renderDesk(); show("screen-desk"); };
  $("#btnBackCases").onclick = () => show("screen-cases");
  $("#btnBackDesk").onclick = () => { renderDesk(); show("screen-desk"); };
  $("#btnBackDesk2").onclick = () => { renderDesk(); show("screen-desk"); };
  $("#btnGoDecision").onclick = renderDecision;
  $("#btnGoReplay").onclick = openReplay;
  $("#btnGoComplete").onclick = renderComplete;
  $("#btnOtherCase").onclick = () => { closeDrawers(); show("screen-cases"); };

  $("#btnNotebook").onclick = () => { renderTerms(); openDrawer("drawerNotebook"); };
  $("#btnBoard").onclick = () => { renderBoard(); openDrawer("drawerBoard"); };
  $("#btnAssistant").onclick = () => openDrawer("drawerAssistant");
  $("#backdrop").onclick = closeDrawers;
  $$("[data-close]").forEach((b) => (b.onclick = closeDrawers));

  $("#qHint").onclick = askHint;
  $("#qTerm").onclick = () => { renderTerms(); openDrawer("drawerNotebook"); };
  $("#qNumber").onclick = explainNumber;
  $("#askForm").onsubmit = (e) => {
    e.preventDefault();
    const q = $("#askInput").value.trim();
    if (!q) return;
    $("#askInput").value = "";
    askFree(q);
  };

  const reset = async () => {
    if (!S.sessionId) return;
    const r = await api(`/sessions/${S.sessionId}/reset`, { method: "POST" });
    if (!r.ok) { toast(r.error, "bad"); return; }
    S.sessionId = r.data.session_id;
    S.briefing = r.data.briefing;
    S.docCache = {}; S.evidence = []; S.lastEvidence = null; S.decisionRecord = null;
    $("#replayLock").hidden = false;
    $("#replayOpen").hidden = true;
    $("#decResult").hidden = true;
    $("#termDetail").innerHTML = "";
    $("#chat").innerHTML = "";
    botSay("처음부터 다시 시작할게. 이번엔 어떤 서류부터 볼까? 🐾");
    const st = await api(`/sessions/${S.sessionId}/state`);
    if (st.ok) applyState(st.data);
    await refreshTerms();
    await refreshEvidence();
    closeDrawers();
    show("screen-casefile");
    toast("↺ 사건을 처음부터 다시 시작합니다", "good");
  };
  $("#btnReset").onclick = reset;
  $("#btnReplayAgain").onclick = reset;

  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawers(); });
}

wire();
loadCases();
