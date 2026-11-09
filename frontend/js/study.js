import { APIError, request } from "./api-client.js";

const params = new URLSearchParams(window.location.search);
const LANGUAGE_ID = Number(params.get("id"));
const $ = id => document.getElementById(id);
const modeNames = { lang_to_pl: "obcy → PL", pl_to_lang: "PL → obcy", mix: "mix" };
let userId = null, session = null, answers = [], currentIdx = 0, baseRevision = 0;
let dirty = false, syncPromise = null, saveTimer = null, pendingSave = null;
let submitting = false, conflict = false, booting = false, starting = false, localSaved = false;
let pendingStartMemory = null;

function message(id, text, error = false) {
  $(id).textContent = text;
  $(id).className = error ? "msg error" : "msg";
}
function report(id, error) {
  message(id, error.message, true);
  if (error.status === 401) $("study-login").hidden = false;
}
function readStorage(key) {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
function removeStorage(key) { try { localStorage.removeItem(key); } catch { /* Storage may be disabled. */ } }
function draftKey() { return `langapp.study.${userId}.${session.session_id}`; }
function startKey() { return `langapp.study.start.${userId}.${LANGUAGE_ID}`; }
function pendingStart() {
  const pending = pendingStartMemory || readStorage(startKey());
  if (pending && Object.hasOwn(modeNames, pending.mode) && Number.isInteger(pending.count)
      && pending.count >= 1 && pending.count <= 50 && typeof pending.request_id === "string"
      && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(pending.request_id)
      && ["all", "due"].includes(pending.source || "all")) return {...pending, source: pending.source || "all"};
  return null;
}
function persistDraft() {
  if (!session || session.finished || !dirty) return;
  localSaved = writeStorage(draftKey(), {
    user_id: userId, session_id: session.session_id, revision: baseRevision,
    current_index: currentIdx, answers, pending_save: pendingSave,
  });
}
function setSessionURL(id) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("session", id); else url.searchParams.delete("session");
  history.replaceState(null, "", url);
}
function screen(name) {
  for (const value of ["config", "quiz", "result"]) $("screen-" + value).classList.toggle("hidden", value !== name);
}
function buttons() {
  $("btn-previous").disabled = submitting || conflict || currentIdx === 0;
  $("btn-next").disabled = submitting || conflict;
  $("btn-save").disabled = submitting || conflict || !dirty;
  $("btn-use-server").hidden = !conflict;
  $("quiz-answer").disabled = submitting;
  $("quiz-answer").readOnly = conflict;
  $("btn-next").textContent = submitting ? "Wysyłanie…" : currentIdx === session?.total - 1 ? "Zakończ quiz" : "Następne pytanie";
}
function renderQuestion() {
  const question = session.questions[currentIdx];
  $("quiz-progress").textContent = `Pytanie ${currentIdx + 1} / ${session.total}`;
  $("progress-fill").style.width = `${currentIdx / session.total * 100}%`;
  $("quiz-mode").textContent = modeNames[session.mode] + (session.source === "due" ? " · powtórka" : "");
  $("quiz-direction").textContent = question.direction === "lang_to_pl" ? "Przetłumacz na polski:" : "Przetłumacz na język obcy:";
  $("quiz-word").textContent = question.prompt;
  $("quiz-answer").value = answers[currentIdx].given;
  buttons();
  if (!submitting) $("quiz-answer").focus();
}
function validCache(cache, data) {
  return cache?.user_id === userId && cache.session_id === data.session_id
    && Number.isInteger(cache.revision) && cache.revision >= 0
    && Number.isInteger(cache.current_index) && cache.current_index >= 0 && cache.current_index < data.total
    && Array.isArray(cache.answers) && cache.answers.length === data.questions.length
    && cache.answers.every((answer, i) => answer && answer.word_id === data.questions[i].word_id && typeof answer.given === "string" && Array.from(answer.given).length <= 128);
}
function sameAnswers(left, right) {
  return left.length === right.length && left.every((answer, i) => answer.word_id === right[i].word_id && answer.given === right[i].given);
}
function adoptSession(data, discardLocal = false) {
  if (data.language_id !== LANGUAGE_ID) throw new APIError("Ten quiz należy do innego języka.");
  clearTimeout(saveTimer);
  session = data; baseRevision = data.revision; currentIdx = data.current_index;
  answers = data.questions.map(question => ({ word_id: question.word_id, given: data.answers.find(answer => answer.word_id === question.word_id)?.given || "" }));
  dirty = false; conflict = false; localSaved = false; pendingSave = null;
  setSessionURL(data.session_id);
  if (data.finished) { showResult(data.result); return; }
  if (discardLocal) removeStorage(draftKey());
  const cached = discardLocal ? null : readStorage(draftKey());
  if (validCache(cached, data)) {
    const alreadySaved = cached.current_index === currentIdx && sameAnswers(cached.answers, answers);
    if (alreadySaved) removeStorage(draftKey());
    else {
      const pending = cached.pending_save;
      const validPending = pending && validCache({...pending, user_id: userId, session_id: data.session_id}, data)
        && pending.revision === cached.revision;
      // If the server committed our previous save but its reply was lost, safely
      // rebase later local edits onto that acknowledged server snapshot.
      const acknowledged = validPending && pending.current_index === currentIdx && sameAnswers(pending.answers, answers);
      answers = cached.answers; currentIdx = cached.current_index; dirty = true;
      conflict = cached.revision !== baseRevision && !acknowledged;
      if (!acknowledged) {
        baseRevision = cached.revision;
        if (validPending) pendingSave = pending;
      }
      localSaved = true;
    }
  }
  screen("quiz"); renderQuestion();
  message("quiz-feedback", "");
  message("quiz-save-status", dirty ? "Przywrócono lokalną kopię odpowiedzi." : "Wczytano zapis z serwera.");
  if (conflict) message("quiz-feedback", "Quiz zmienił się w innej karcie. Lokalna kopia pozostała zachowana. Wczytaj zapis z serwera, aby kontynuować.", true);
  else if (dirty) scheduleSave();
}
function changed() {
  dirty = true; persistDraft(); buttons();
  message("quiz-save-status", localSaved ? "Zapisano lokalnie. Oczekiwanie na synchronizację…" : "Kopia lokalna niedostępna. Trwa próba zapisu na serwerze…");
  scheduleSave();
}
function captureInput() {
  if (answers[currentIdx].given !== $("quiz-answer").value) {
    answers[currentIdx].given = $("quiz-answer").value;
    changed();
  }
}
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { void flushDraft(); }, 600);
}
async function flushDraft() {
  if (syncPromise) return syncPromise;
  if (!session || session.finished || conflict) return !dirty;
  syncPromise = (async () => {
    while (dirty && !conflict) {
      // Retry the exact unacknowledged request before sending newer edits.
      const body = pendingSave || {revision: baseRevision, current_index: currentIdx, answers: answers.map(answer => ({...answer}))};
      pendingSave = body; persistDraft();
      try {
        const data = await request(`/api/study/sessions/${session.session_id}/draft`, "PUT", body);
        baseRevision = data.revision;
        pendingSave = null;
        dirty = body.current_index !== currentIdx || !sameAnswers(body.answers, answers);
        if (!dirty) removeStorage(draftKey()); else persistDraft();
      } catch (error) {
        if (error.status === 409) { conflict = true; report("quiz-feedback", error); }
        else {
          report("quiz-feedback", error);
          message("quiz-save-status", localSaved ? "Odpowiedzi są zapisane lokalnie. Ponów zapis po odzyskaniu połączenia." : "Odpowiedzi pozostają tylko w tej karcie. Nie zamykaj jej przed zapisem.", true);
        }
        buttons(); return false;
      }
    }
    message("quiz-save-status", "Zapisano na serwerze."); buttons();
    message("quiz-feedback", "");
    return !conflict;
  })();
  try { return await syncPromise; } finally { syncPromise = null; }
}
async function submitAll() {
  if (submitting || conflict || !session || session.finished) return;
  captureInput(); submitting = true; buttons();
  message("quiz-feedback", "");
  try {
    if (!await flushDraft()) return;
    const result = await request("/api/study/submit", "POST", {session_id: session.session_id, revision: baseRevision, answers});
    showResult(result);
  } catch (error) {
    if (error.status === 409) conflict = true;
    report("quiz-feedback", error);
    if (!conflict && error.status !== 401) message("quiz-feedback", error.message + " Odpowiedzi zostały zachowane. Kliknij ponownie „Zakończ quiz”.", true);
  } finally { submitting = false; buttons(); }
}
function showResult(data) {
  session.finished = true; dirty = false; conflict = false;
  clearTimeout(saveTimer); removeStorage(draftKey());
  screen("result");
  $("res-total").textContent = data.total;
  $("res-correct").textContent = data.correct;
  $("res-percent").textContent = data.percent;
  $("res-title").textContent = data.percent >= 80 ? "Świetnie!" : data.percent >= 50 ? "Dobrze, idziesz dalej." : "Jeszcze trochę powtórek.";
  $("res-list").replaceChildren();
  for (const result of data.results) {
    const row = document.createElement("div");
    row.className = "res-row " + (result.is_correct ? "ok" : "bad");
    const icon = document.createElement("span"); icon.className = "res-icon"; icon.textContent = result.is_correct ? "✓" : "✗";
    const text = document.createElement("span");
    text.textContent = `${result.prompt} → ${(result.accepted_answers || [result.expected]).join(" / ")}${result.is_correct ? "" : ` (wpisano: ${result.given || "—"})`}`;
    row.append(icon, text); $("res-list").append(row);
  }
}
function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, char => {
    const n = crypto.getRandomValues(new Uint8Array(1))[0] & 15;
    return (char === "x" ? n : (n & 3) | 8).toString(16);
  });
}
async function startQuiz() {
  if (starting || booting || !userId) return;
  const mode = $("cfg-mode").value, count = Number($("cfg-count").value), source = $("cfg-source").value;
  if (!Number.isInteger(count) || count < 1 || count > 50) { message("cfg-msg", "Wpisz liczbę słów od 1 do 50.", true); return; }
  let pending = pendingStart();
  if (!pending || pending.mode !== mode || pending.count !== count || pending.source !== source) pending = {mode, count, source, request_id: requestId()};
  writeStorage(startKey(), pending);
  pendingStartMemory = pending;
  starting = true; $("btn-start").disabled = true;
  message("cfg-msg", "Rozpoczynanie…");
  try {
    const data = await request("/api/study/start", "POST", {language_id: LANGUAGE_ID, mode: pending.mode, count: pending.count, source: pending.source, request_id: pending.request_id});
    adoptSession(data); removeStorage(startKey()); pendingStartMemory = null;
  } catch (error) { report("cfg-msg", error); }
  finally { starting = false; $("btn-start").disabled = false; }
}
async function loadSession(id, discardLocal = false) {
  const data = await request(`/api/study/sessions/${id}`);
  adoptSession(data, discardLocal);
}
async function initialize() {
  if (booting) return;
  booting = true; $("btn-start").disabled = true; $("btn-retry-load").hidden = true;
  try {
    const [me, vocabulary, active] = await Promise.all([
      request("/api/me"), request(`/api/user/languages/${LANGUAGE_ID}/words`), request(`/api/study/active?language_id=${LANGUAGE_ID}`),
    ]);
    userId = me.id;
    $("cfg-lang").textContent = `${vocabulary.language.flag} ${vocabulary.language.name_pl} — masz ${vocabulary.words.length} słów`;
    $("resume-session").replaceChildren();
    for (const quiz of active.sessions) {
      const option = document.createElement("option"); option.value = quiz.session_id;
      option.textContent = `${quiz.source === "due" ? "Powtórka · " : ""}${modeNames[quiz.mode]} · pytanie ${quiz.current_index + 1}/${quiz.total} · ${new Date(quiz.created_at + "Z").toLocaleString("pl-PL")}`;
      $("resume-session").append(option);
    }
    $("resume-panel").hidden = active.sessions.length === 0;
    const pending = pendingStart();
    const review = new URLSearchParams(window.location.search).get("review");
    if (["lang_to_pl", "pl_to_lang"].includes(review)) { $("cfg-source").value = "due"; $("cfg-mode").value = review; }
    else if (pending) { $("cfg-mode").value = pending.mode; $("cfg-count").value = pending.count; $("cfg-source").value = pending.source; message("cfg-msg", "Możesz ponowić poprzednią próbę rozpoczęcia quizu."); }
    updateSource();
    const id = Number(new URLSearchParams(window.location.search).get("session"));
    if (Number.isSafeInteger(id) && id > 0) await loadSession(id);
    $("btn-start").disabled = false;
  } catch (error) { report("cfg-msg", error); $("btn-retry-load").hidden = false; }
  finally { booting = false; }
}

function updateSource() {
  const due = $("cfg-source").value === "due";
  $("cfg-mode").querySelector('option[value="mix"]').disabled = due;
  if (due && $("cfg-mode").value === "mix") $("cfg-mode").value = "lang_to_pl";
  $("cfg-source-info").textContent = due ? "Tylko słowa zaplanowane na dziś lub zaległe. Możesz powtarzać nawet jedno słowo." : "Losowy quiz ze wszystkich Twoich słów (minimum 4 słowa w słowniku).";
}
$("cfg-source").addEventListener("change", updateSource);
$("btn-start").addEventListener("click", startQuiz);
$("btn-retry-load").addEventListener("click", initialize);
$("btn-resume").addEventListener("click", async () => {
  $("btn-resume").disabled = true;
  try { await loadSession(Number($("resume-session").value)); } catch (error) { report("cfg-msg", error); }
  finally { $("btn-resume").disabled = false; }
});
$("quiz-answer").addEventListener("input", () => { if (!submitting && !conflict) captureInput(); });
$("btn-next").addEventListener("click", event => {
  if (event.detail > 1 || submitting || conflict) return;
  captureInput();
  if (currentIdx === session.total - 1) { void submitAll(); return; }
  currentIdx++; changed(); renderQuestion();
});
$("btn-previous").addEventListener("click", event => {
  if (event.detail > 1 || submitting || conflict || currentIdx === 0) return;
  captureInput(); currentIdx--; changed(); renderQuestion();
});
$("quiz-answer").addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); if (!event.repeat) $("btn-next").click(); }
});
$("btn-save").addEventListener("click", () => { captureInput(); void flushDraft(); });
$("btn-use-server").addEventListener("click", async () => {
  if (!confirm("Wczytać zapis z serwera? Zastąpi to lokalne odpowiedzi w tym quizie.")) return;
  try { await loadSession(session.session_id, true); } catch (error) { report("quiz-feedback", error); }
});
$("btn-again").addEventListener("click", () => { session = null; setSessionURL(null); screen("config"); void initialize(); });
$("logout").addEventListener("click", async () => {
  try {
    if (session && !session.finished && dirty && !await flushDraft()
        && !confirm("Nie udało się zsynchronizować odpowiedzi. Wylogować mimo to? Niezsynchronizowana kopia lokalna zostanie usunięta.")) return;
    await request("/api/auth/logout", "POST");
    if (session) removeStorage(draftKey());
    window.location.href = "/";
  } catch (error) { report(session && !session.finished ? "quiz-feedback" : "cfg-msg", error); }
});
window.addEventListener("online", () => { if (dirty && !submitting && !conflict) void flushDraft(); });
window.addEventListener("beforeunload", event => {
  if (dirty) { persistDraft(); if (!localSaved) { event.preventDefault(); event.returnValue = ""; } }
});
if (Number.isSafeInteger(LANGUAGE_ID) && LANGUAGE_ID > 0) void initialize();
else { message("cfg-msg", "Nieprawidłowy język. Wróć do panelu i wybierz język.", true); }
