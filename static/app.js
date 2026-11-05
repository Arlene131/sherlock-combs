import { mountMascots, setMood } from "/static/mascot.js";

const STORAGE_KEY = "sherlock-combs-chat-v1";
const ISSUE_LABELS = {
  dandruff: "Ketombe", hair_fall: "Rontok", dry: "Kering", frizzy: "Frizzy", oily: "Berminyak",
  thin: "Tipis", flat: "Lepek", side_puff: "Samping mekar", unmanageable_curls: "Ikal susah diatur",
  post_color: "Pasca-coloring", beard: "Jenggot", general: "Umum",
};
const SUGGESTIONS = [
  "Muka aku bulat, rambut lurus tebal. Cocoknya potong gaya apa?",
  "Undertone aku warm dan rambut belum pernah dicat, warna apa yang cocok?",
  "Rambutku rontok dan berketombe, perawatannya apa ya?",
  "Pengen rambut silver, tapi rambutku pernah di-smoothing. Bisa nggak?",
  "Jam buka berapa?",
];

const emptyProfile = () => ({ face_shape: null, hair_texture: null, hair_thickness: null,
  undertone: null, hair_condition: [], issues: [] });

let state = { history: [], profile: emptyProfile(), rendered: [] };

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const input = $("#input");
const sendBtn = $("#send-btn");
const mainMascot = $("#main-mascot");
const miniMascot = document.querySelector(".mini-mascot");
const mascotStatus = $("#mascot-status");
const MOOD_TEXT = {
  idle: "Siap bantu kamu", thinking: "Hmm, lagi mikir…", talking: "Nih, aku jelasin ya",
  happy: "Semoga membantu!", camera: "Siap-siap, cekrek!",
};
let moodTimer = null;

/** Change Sherlock's expression in the sidebar and the chat header. */
function mood(name, { revertAfter } = {}) {
  clearTimeout(moodTimer);
  [mainMascot, miniMascot].forEach((el) => el && setMood(el, name));
  mascotStatus.textContent = MOOD_TEXT[name] || "";
  if (revertAfter) moodTimer = setTimeout(() => mood("idle"), revertAfter);
}

function save() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) { /* storage optional */ }
}
function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) state = { ...state, ...JSON.parse(raw) };
  } catch (_) { /* ignore */ }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Minimal, safe markdown: paragraphs, bullet/numbered lists, **bold**, *italic*.
function renderMarkdown(text) {
  const inline = (s) => escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<em>$2</em>");
  const lines = text.split(/\r?\n/);
  let html = "", list = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const line of lines) {
    const bullet = line.match(/^\s*[-*•]\s+(.*)/);
    const num = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (bullet || num) {
      const tag = bullet ? "ul" : "ol";
      if (list !== tag) { close(); html += `<${tag}>`; list = tag; }
      html += `<li>${inline((bullet || num)[1])}</li>`;
    } else if (line.trim() === "") {
      close();
    } else {
      close();
      html += `<p>${inline(line)}</p>`;
    }
  }
  close();
  return html;
}

function addMessage(msg) {
  const el = document.createElement("div");
  el.className = `msg ${msg.role === "user" ? "user" : "bot"}`;
  fillMessage(el, msg);
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

const STAGE_LABELS = { faq_check: "cek FAQ", profiling_rules: "profiling (lokal)", profiling_llm: "profiling (LLM)",
  retrieval: "retrieval", generation: "jawaban" };

function fillMessage(el, msg) {
  if (msg.role === "user") {
    el.textContent = msg.content;
  } else {
    el.innerHTML = renderMarkdown(msg.content);
    if (msg.recommendations?.length) {
      const cards = document.createElement("div");
      cards.className = "cards";
      for (const r of msg.recommendations) {
        cards.insertAdjacentHTML("beforeend", `<div class="card">
          <span class="kind">${r.type === "service" ? "Jasa" : "Produk"} · ${escapeHtml(r.id)}</span>
          <span class="name">${escapeHtml(r.name)}</span>
          <span class="price">${escapeHtml(r.price_label)}</span></div>`);
      }
      el.appendChild(cards);
    }
    if (msg.examples?.length) {
      const box = document.createElement("div");
      box.className = "examples";
      box.innerHTML = `<span class="examples-label">Lihat contoh:</span>` + msg.examples.map((e) =>
        `<a class="example-chip" href="${escapeHtml(e.url)}" target="_blank" rel="noopener">${escapeHtml(e.label)}
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>`
      ).join("");
      el.appendChild(box);
    }
    if (msg.sources?.length) {
      // Transparency for demos: which chunks were retrieved and their similarity scores.
      const det = document.createElement("details");
      det.className = "sources";
      const route = { faq: "FAQ (tanpa LLM)", ask: "bertanya balik", rag: "RAG" }[msg.route] || msg.route;
      const timings = msg.timings ? Object.entries(msg.timings)
        .map(([k, v]) => `${STAGE_LABELS[k] || k} ${v}s`).join(" · ") : "";
      det.innerHTML = `<summary>Sumber jawaban · ${escapeHtml(route || "")}</summary><ul>${
        msg.sources.map((s) => `<li>${escapeHtml(s.id)} — ${escapeHtml(s.title)} (skor ${Number(s.score).toFixed(3)}${
          s.filters?.length ? `, filter: ${escapeHtml(s.filters.join(", "))}` : ""})</li>`).join("")}</ul>${
        timings ? `<p class="timings">Waktu proses: ${escapeHtml(timings)}</p>` : ""}`;
      el.appendChild(det);
    }
  }
}

function renderAll() {
  messagesEl.innerHTML = "";
  if (!state.rendered.length) {
    addMessage({ role: "assistant", content:
      "Greetings! Aku Sherlock dari Sherlock Combs.\n" +
      "Aku bisa bantu pilih gaya rambut sesuai bentuk wajah, warna sesuai undertone kulit, " +
      "dan perawatan untuk kondisi rambutmu. Mau mulai dari mana?" });
  }
  state.rendered.forEach(addMessage);
  renderSuggestions();
  renderProfile();
}

function renderSuggestions() {
  const box = $("#suggestions");
  box.innerHTML = "";
  if (state.rendered.length) return;
  for (const s of SUGGESTIONS) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = s;
    b.onclick = () => send(s);
    box.appendChild(b);
  }
}

function renderProfile() {
  document.querySelectorAll("[data-field]").forEach((sel) => {
    const field = sel.dataset.field;
    const value = state.profile[field];
    sel.value = Array.isArray(value) ? (value[0] || "") : (value || "");
  });
  $("#issues").innerHTML = (state.profile.issues || [])
    .map((i) => `<span>${escapeHtml(ISSUE_LABELS[i] || i)}</span>`).join("");
  const p = state.profile;
  const filled = [p.face_shape, p.hair_texture, p.hair_thickness, p.undertone, p.hair_condition?.length]
    .filter(Boolean).length;
  $("#profile-count").textContent = `${filled}/5`;
}

/** Chunk ids used in earlier answers, so "ada opsi lain?" gets new suggestions. */
function seenIds() {
  const ids = state.rendered.filter((m) => m.role === "assistant" && m.route === "rag")
    .flatMap((m) => (m.sources || []).map((s) => s.id));
  return [...new Set(ids)].slice(-40);
}

async function send(text) {
  const message = text.trim();
  if (!message) return;
  input.value = "";
  autosize();
  sendBtn.disabled = true;

  const userMsg = { role: "user", content: message };
  state.rendered.push(userMsg);
  addMessage(userMsg);
  renderSuggestions();
  const bubble = addMessage({ role: "assistant", content: "" });
  bubble.classList.add("typing");
  bubble.textContent = "Sherlock lagi mikir";
  mood("thinking");
  let streamed = "";

  // Events arrive as NDJSON lines: status -> profile -> delta… -> done
  const handle = (ev) => {
    if (ev.type === "status" && !streamed) {
      bubble.textContent = ev.text.replace("…", "");
    } else if (ev.type === "profile") {
      state.profile = ev.profile;
      renderProfile();
    } else if (ev.type === "delta") {
      if (!streamed) mood("talking");
      streamed += ev.text;
      bubble.classList.remove("typing");
      bubble.innerHTML = renderMarkdown(streamed);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else if (ev.type === "done") {
      bubble.classList.remove("typing");
      const botMsg = { role: "assistant", content: ev.answer, recommendations: ev.recommendations,
        examples: ev.examples, sources: ev.sources, route: ev.route, timings: ev.debug?.timings_s };
      if (ev.intent && ev.route === "rag") state.lastIntent = ev.intent;
      fillMessage(bubble, botMsg);
      mood(["error", "blocked"].includes(ev.route) ? "idle" : "happy", { revertAfter: 4000 });
      state.rendered.push(botMsg);
      state.history.push({ role: "user", content: message }, { role: "assistant", content: ev.answer });
      state.history = state.history.slice(-12);
      state.profile = ev.profile;
      renderProfile();
      save();
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  };

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: state.history, profile: state.profile,
        seen_ids: seenIds(), last_intent: state.lastIntent || null }),
    });
    if (res.status === 429) throw new Error("Terlalu banyak pesan dalam 1 menit, tunggu sebentar ya");
    if (res.status === 400) throw new Error("Pesannya terlalu panjang, maksimal 500 karakter");
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) handle(JSON.parse(line));
      }
    }
    if (buffer.trim()) handle(JSON.parse(buffer));
  } catch (err) {
    bubble.classList.remove("typing");
    bubble.textContent = err.message.startsWith("HTTP") ? `Maaf, terjadi kesalahan (${err.message}). Coba lagi ya.` : err.message + ".";
    mood("idle");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

function autosize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
}

// ---- events ----
$("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); }
});

document.querySelectorAll("[data-field]").forEach((sel) => {
  sel.addEventListener("change", () => {
    const field = sel.dataset.field;
    if (field === "hair_condition") state.profile[field] = sel.value ? [sel.value] : [];
    else state.profile[field] = sel.value || null;
    save();
  });
});

$("#reset-btn").addEventListener("click", () => {
  state = { history: [], profile: emptyProfile(), rendered: [], lastIntent: null };
  save();
  renderAll();
});

function toggleProfile(open) {
  $("#profile-panel").classList.toggle("open", open);
  $("#scrim").classList.toggle("show", open);
  $("#toggle-profile").setAttribute("aria-expanded", String(open));
}
$("#toggle-profile").addEventListener("click", () => toggleProfile(!$("#profile-panel").classList.contains("open")));
$("#close-profile").addEventListener("click", () => toggleProfile(false));
$("#scrim").addEventListener("click", () => toggleProfile(false));

async function scanFace() {
  toggleProfile(false);
  let face;
  try {
    face = await import("/static/face.js");
  } catch (err) {
    addMessage({ role: "assistant", content: "Fitur kamera gagal dimuat. Kamu bisa pilih bentuk wajah manual di panel profil." });
    return;
  }
  const { startFaceScan, FACE_LABELS } = face;
  mood("camera");
  const shape = await startFaceScan();
  mood("idle");
  if (!shape) return;
  state.profile.face_shape = shape;
  renderProfile();
  save();
  send(`Hasil deteksi kamera: bentuk wajahku ${FACE_LABELS[shape]}.`);
}
$("#face-scan-btn").addEventListener("click", scanFace);
$("#composer-camera").addEventListener("click", scanFace);

// ---- intro: "Hello", then the page is cut open like gift paper (once per browser session) ----
function playIntro() {
  const splash = $("#splash");
  let seen = false;
  try { seen = sessionStorage.getItem("sc-intro") === "1"; } catch (_) { /* storage optional */ }
  if (seen || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  try { sessionStorage.setItem("sc-intro", "1"); } catch (_) { /* ignore */ }

  const timers = [];
  const finish = () => { timers.forEach(clearTimeout); splash.classList.remove("is-on"); };
  splash.classList.add("is-on");
  timers.push(setTimeout(() => splash.classList.add("is-cutting"), 2300));   // scissors cut down the middle
  timers.push(setTimeout(() => splash.classList.add("is-open"), 3350));      // halves slide apart
  timers.push(setTimeout(finish, 4300));
  splash.querySelector(".splash-skip").addEventListener("click", finish);
}

mountMascots();
playIntro();
load();
renderAll();
