import { request } from "./api-client.js";
import { continueTarget, wordCount } from "./learning-ui.js";
import { confirmAction, notify } from "./ui.js";

const $ = id => document.getElementById(id);
const modes = {lang_to_pl: "obcy → PL", pl_to_lang: "PL → obcy", mix: "mix"};
let version = 0, timezone = "Europe/Warsaw", nextOffset = null, historyBusy = false;
let allLanguages = [], ownedLanguages = new Set(), languageBusy = false;
const historyIds = new Set();

function node(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}
function status(id, text, error = false) {
  $(id).textContent = text; $(id).className = error ? "msg error" : "msg";
}
function report(id, error) {
  status(id, error.message, true);
  if (error.status === 401) $("dashboard-login").hidden = false;
}
function link(text, href) { const result = node("a", "ghost", text); result.href = href; return result; }
function percent(value) { return value === null ? "—" : `${value}%`; }
function dateTime(value) {
  if (!value) return "Data niedostępna";
  return new Intl.DateTimeFormat("pl-PL", {dateStyle: "short", timeStyle: "short", timeZone: timezone}).format(new Date(value));
}

function renderDue(groups, summary) {
  $("due-count").textContent = `(${summary.due_reviews})`;
  $("due-list").replaceChildren();
  if (!groups.length) {
    $("due-list").append(node("p", "empty", summary.practiced_words ? "Na dziś wszystko powtórzone. Kolejny quiz rozpoczniesz z karty języka." : "Ukończ pierwszy quiz. Na podstawie odpowiedzi zaplanujemy powtórki."));
  }
  for (const group of groups) {
    const row = node("article", "learning-row");
    const description = node("div");
    description.append(node("strong", "", `${group.flag} ${group.name_pl}`), node("p", "muted", `${modes[group.direction]} · do powtórzenia: ${group.count}`));
    row.append(description, link("Powtórz", `/study?id=${group.language_id}&review=${group.direction}`));
    $("due-list").append(row);
  }
}
function renderDifficult(words) {
  $("difficult-list").replaceChildren();
  if (!words.length) $("difficult-list").append(node("p", "empty", "Nie ma obecnie słów wymagających szczególnej uwagi."));
  for (const word of words) {
    const row = node("article", "learning-row");
    const description = node("div");
    description.append(node("strong", "", `${word.word} → ${word.translation_pl}`), node("p", "muted", `${word.language_name} · poprawnie ${word.correct}/${word.attempts} (${word.accuracy}%)`));
    row.append(description, link("Otwórz słownik", `/language?id=${word.language_id}`));
    $("difficult-list").append(row);
  }
}
function appendHistory(items) {
  for (const item of items) {
    if (historyIds.has(item.id)) continue;
    historyIds.add(item.id);
    const row = node("article", "learning-row");
    const description = node("div");
    description.append(node("strong", "", `${item.language_name} · ${item.correct}/${item.total} (${percent(item.percent)})`), node("p", "muted", `${dateTime(item.finished_at)} · ${modes[item.mode]} · ${item.source === "due" ? "Powtórka" : "Quiz"}`));
    row.append(description, link("Zobacz wynik", `/study?id=${item.language_id}&session=${item.id}`));
    $("history-list").append(row);
  }
}
function historyButton() {
  $("btn-history-more").hidden = nextOffset === null;
  $("btn-history-more").disabled = historyBusy;
}
function renderLanguages(languages) {
  ownedLanguages = new Set(languages.map(language => language.id));
  $("my-languages").replaceChildren();
  if (!languages.length) $("my-languages").append(node("p", "empty", "Nie masz jeszcze języka. Wybierz „Dodaj język”, aby rozpocząć."));
  for (const language of languages) {
    const tile = node("article", "tile");
    const open = link(`${language.flag} ${language.name_pl}`, `/language?id=${language.id}`);
    open.className = "language-title";
    const remove = node("button", "ghost small danger", "Usuń");
    remove.type = "button";
    remove.setAttribute("aria-label", `Usuń język ${language.name_pl}`);
    remove.addEventListener("click", async () => {
      remove.disabled = true;
      try {
        if (!await confirmAction({title: `Usunąć język ${language.name_pl}?`, message: "Usuniesz jego słowa, historię i postęp. Tej operacji nie można cofnąć.", label: "Usuń język"})) return;
        await request(`/api/user/languages/${language.user_language_id}`, "DELETE");
        await loadDashboard();
        notify("Język został usunięty.");
      } catch (error) { report("dashboard-status", error); }
      finally { remove.disabled = false; if (remove.isConnected) remove.focus(); else $("btn-add-language").focus(); }
    });
    const header = node("div", "tile-heading"); header.append(open, remove);
    const actions = node("div", "tile-actions");
    actions.append(link("Otwórz słowa", `/language?id=${language.id}`), link("Ćwicz", `/study?id=${language.id}`));
    tile.append(header, node("p", "muted", language.name_native), node("p", "tile-word-count", wordCount(language.total_words)), node("p", "muted", `Przećwiczone: ${language.practiced_words} · poprawność: ${percent(language.accuracy)}`), actions);
    $("my-languages").append(tile);
  }
}
async function loadDashboard() {
  const current = ++version;
  $("btn-refresh").disabled = true;
  status("dashboard-status", "Wczytywanie postępu…");
  try {
    const data = await request("/api/dashboard");
    if (current !== version) return;
    timezone = data.timezone;
    $("user-login").textContent = data.user.login;
    $("stat-words").textContent = `${data.summary.practiced_words}/${data.summary.total_words}`;
    $("stat-quizzes").textContent = data.summary.quizzes;
    $("stat-accuracy").textContent = percent(data.summary.accuracy);
    $("stat-answers").textContent = `${data.summary.correct}/${data.summary.answers} odpowiedzi`;
    $("stat-streak").textContent = data.summary.streak;
    $("learning-day").textContent = "Twój plan na " + new Intl.DateTimeFormat("pl-PL", {day: "numeric", month: "long", timeZone: "UTC"}).format(new Date(data.today + "T12:00:00Z"));
    renderDue(data.due, data.summary); renderDifficult(data.difficult); renderLanguages(data.languages);
    const next = continueTarget(data);
    $("continue-heading").textContent = next.title;
    $("continue-description").textContent = next.detail;
    $("continue-learning").hidden = !next.href;
    $("continue-onboarding").hidden = !!next.href;
    if (next.href) { $("continue-learning").href = next.href; $("continue-learning").textContent = next.label + " →"; }
    historyIds.clear(); $("history-list").replaceChildren();
    appendHistory(data.history.items);
    if (!data.history.items.length) $("history-list").append(node("p", "empty", "Nie masz jeszcze ukończonych quizów."));
    nextOffset = data.history.next_offset; historyButton();
    status("history-status", "");
    status("dashboard-status", "");
    $("dashboard-login").hidden = true;
  } catch (error) { if (current === version) report("dashboard-status", error); }
  finally { if (current === version) $("btn-refresh").disabled = false; }
}

$("btn-refresh").addEventListener("click", loadDashboard);
$("continue-onboarding").addEventListener("click", () => $("btn-add-language").click());
$("btn-history-more").addEventListener("click", async () => {
  if (historyBusy || nextOffset === null) return;
  const current = version, offset = nextOffset;
  historyBusy = true; historyButton(); status("history-status", "Wczytywanie starszych wyników…");
  try {
    const data = await request(`/api/dashboard/history?limit=10&offset=${offset}`);
    if (current !== version) return;
    appendHistory(data.items); nextOffset = data.next_offset; status("history-status", "");
  } catch (error) { if (current === version) report("history-status", error); }
  finally { historyBusy = false; historyButton(); }
});
$("logout").addEventListener("click", async () => {
  $("logout").disabled = true;
  try { await request("/api/auth/logout", "POST"); window.location.href = "/"; }
  catch (error) { report("dashboard-status", error); $("logout").disabled = false; }
});

function closeModal() {
  if (languageBusy) return;
  $("modal-lang").classList.add("hidden"); $("btn-add-language").focus();
}
async function loadLanguageChoices() {
  $("btn-retry-languages").hidden = true; status("modal-lang-msg", "Wczytywanie języków…");
  try {
    allLanguages = await request("/api/languages");
    renderLanguageChoices(); status("modal-lang-msg", "");
  } catch (error) { report("modal-lang-msg", error); $("btn-retry-languages").hidden = false; }
}
function renderLanguageChoices() {
  const search = $("lang-search").value.toLocaleLowerCase("pl");
  $("lang-list").replaceChildren();
  const matches = allLanguages.filter(language => `${language.name_pl} ${language.name_native}`.toLocaleLowerCase("pl").includes(search));
  if (!matches.length) $("lang-list").append(node("li", "muted", "Brak wyników."));
  for (const language of matches) {
    const li = node("li");
    const button = node("button", "language-choice", `${language.flag} ${language.name_pl} · ${language.name_native}`);
    button.type = "button"; button.disabled = languageBusy || ownedLanguages.has(language.id);
    if (ownedLanguages.has(language.id)) button.textContent += " · dodano";
    button.addEventListener("click", async () => {
      if (languageBusy) return;
      languageBusy = true; renderLanguageChoices();
      try {
        try { await request("/api/user/languages", "POST", {language_id: language.id}); }
        catch (error) { if (error.status !== 409) throw error; }
        languageBusy = false; closeModal(); await loadDashboard(); notify(`Dodano język: ${language.name_pl}.`);
      } catch (error) { report("modal-lang-msg", error); }
      finally { languageBusy = false; renderLanguageChoices(); }
    });
    li.append(button); $("lang-list").append(li);
  }
}
$("btn-add-language").addEventListener("click", async () => {
  $("modal-lang").classList.remove("hidden"); $("lang-search").focus();
  if (!allLanguages.length) await loadLanguageChoices(); else renderLanguageChoices();
});
$("btn-retry-languages").addEventListener("click", loadLanguageChoices);
$("modal-close").addEventListener("click", closeModal);
$("lang-search").addEventListener("input", renderLanguageChoices);
$("modal-lang").addEventListener("click", event => { if (event.target === $("modal-lang")) closeModal(); });
$("modal-lang").addEventListener("keydown", event => {
  if (event.key === "Escape") { event.preventDefault(); closeModal(); }
  if (event.key !== "Tab") return;
  const controls = [...$("modal-lang").querySelectorAll('button:not(:disabled):not([hidden]), input:not(:disabled)')];
  const first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
void loadDashboard();
