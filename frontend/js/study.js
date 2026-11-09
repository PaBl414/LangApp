import { formatError } from "./api-errors.js";

const params = new URLSearchParams(window.location.search);
const LANGUAGE_ID = parseInt(params.get("id"), 10);
if (!LANGUAGE_ID) window.location.href = "/dashboard";

let LANG = null;
let session = null;     // { session_id, total, questions }
let answers = [];       // [{ word_id, given }]
let currentIdx = 0;

const screenConfig = document.getElementById("screen-config");
const screenQuiz   = document.getElementById("screen-quiz");
const screenResult = document.getElementById("screen-result");

// Wylogowanie
document.getElementById("logout").addEventListener("click", async () => {
  try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) {}
  window.location.href = "/";
});

// Załaduj język (z /api/user/languages/{id}/words — pobieramy tylko nagłówek)
(async () => {
  const res = await fetch(`/api/user/languages/${LANGUAGE_ID}/words`, { credentials: "same-origin" });
  if (!res.ok) { window.location.href = "/dashboard"; return; }
  const data = await res.json();
  LANG = data.language;
  document.getElementById("cfg-lang").textContent = `${LANG.flag} ${LANG.name_pl} — masz ${data.words.length} słów`;
})();

// === Start quizu ===
document.getElementById("btn-start").addEventListener("click", async () => {
  const mode = document.getElementById("cfg-mode").value;
  const count = parseInt(document.getElementById("cfg-count").value, 10);
  const msg = document.getElementById("cfg-msg");
  msg.textContent = "";

  const res = await fetch("/api/study/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language_id: LANGUAGE_ID, mode, count }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    msg.classList.add("error");
    msg.textContent = formatError(data, `Błąd (HTTP ${res.status}).`);
    return;
  }

  session = data;
  answers = new Array(data.questions.length).fill(null).map((_, i) => ({
    word_id: data.questions[i].word_id,
    given: "",
  }));
  currentIdx = 0;
  document.getElementById("quiz-mode").textContent =
    ({ lang_to_pl: "obcy → PL", pl_to_lang: "PL → obcy", mix: "mix" })[data.mode] || data.mode;

  screenConfig.classList.add("hidden");
  screenQuiz.classList.remove("hidden");
  renderQuestion();
  document.getElementById("quiz-answer").focus();
});

// === Render pytania ===
function renderQuestion() {
  const q = session.questions[currentIdx];
  document.getElementById("quiz-progress").textContent =
    `Pytanie ${currentIdx + 1} / ${session.total}`;
  document.getElementById("progress-fill").style.width =
    `${((currentIdx) / session.total) * 100}%`;

  document.getElementById("quiz-direction").textContent =
    q.direction === "lang_to_pl" ? "Przetłumacz na polski:" : "Przetłumacz na język obcy:";
  document.getElementById("quiz-word").textContent = q.prompt;
  document.getElementById("quiz-answer").value = "";
  document.getElementById("quiz-feedback").textContent = "";
  document.getElementById("btn-next").textContent = "Zatwierdź";
  document.getElementById("quiz-answer").focus();
}

// === Zatwierdź / następne ===
document.getElementById("btn-next").addEventListener("click", () => {
  const q = session.questions[currentIdx];
  const given = document.getElementById("quiz-answer").value.trim();
  answers[currentIdx].given = given;

  if (currentIdx < session.total - 1) {
    currentIdx++;
    renderQuestion();
  } else {
    submitAll();
  }
});

// Enter w polu = klik w przycisk
document.getElementById("quiz-answer").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    document.getElementById("btn-next").click();
  }
});

// === Submit ===
async function submitAll() {
  document.getElementById("progress-fill").style.width = "100%";
  const res = await fetch("/api/study/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: session.session_id, answers }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(formatError(data, `Błąd (HTTP ${res.status}).`));
    return;
  }
  showResult(data);
}

// === Ekran wyniku ===
function showResult(data) {
  screenQuiz.classList.add("hidden");
  screenResult.classList.remove("hidden");
  document.getElementById("res-total").textContent = data.total;
  document.getElementById("res-correct").textContent = data.correct;
  document.getElementById("res-percent").textContent = data.percent;
  document.getElementById("res-title").textContent =
    data.percent >= 80 ? "Świetnie!" :
    data.percent >= 50 ? "Dobrze, idziesz dalej." :
    "Jeszcze trochę powtórek.";

  const list = document.getElementById("res-list");
  list.innerHTML = "";
  data.results.forEach(r => {
    const row = document.createElement("div");
    row.className = "res-row " + (r.is_correct ? "ok" : "bad");
    row.innerHTML = `
      <span class="res-icon">${r.is_correct ? "✓" : "✗"}</span>
      <span class="res-prompt">${escapeHtml(r.prompt)}</span>
      <span class="res-arrow">→</span>
      <span class="res-expected">${escapeHtml(r.expected)}</span>
      ${r.is_correct ? "" : `<span class="res-given">(wpisano: ${escapeHtml(r.given || "—")})</span>`}
    `;
    list.appendChild(row);
  });
}

document.getElementById("btn-again").addEventListener("click", () => {
  screenResult.classList.add("hidden");
  screenConfig.classList.remove("hidden");
  document.getElementById("cfg-msg").textContent = "";
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
