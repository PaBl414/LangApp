import { request } from "./api-client.js";
import { previewWords, cleanWordText } from "./quick-words.js";

/**
 * language.js — widok pojedynczego języka.
 * Lista słów, dodawanie z walidacją API (Datamuse + Free Dictionary), usuwanie.
 * Przycisk „Ucz się" → /study?id=N
 */

// === 1. Odczyt ID języka z URL ===
const params = new URLSearchParams(window.location.search);
const LANGUAGE_ID = parseInt(params.get("id"), 10);
if (!LANGUAGE_ID) {
  window.location.href = "/dashboard";
}

let LANG = null;
let editingWord = null;
let savingWord = false;
let savingQuick = false;
let savingInline = false;
let WORDS = [];
let loadVersion = 0;

// === 2. Wylogowanie ===
document.getElementById("logout").addEventListener("click", async () => {
  if (savingQuick || savingWord || savingInline) return;
  if (hasUnsavedWords() && !confirm("Masz niezapisane słowa. Wylogować i odrzucić wpisane dane?")) return;
  try {
    await request("/api/auth/logout", "POST");
    quickInput.value = "";
    inlineForeign.value = "";
    inlinePolish.value = "";
    window.location.href = "/";
  }
  catch (error) { alert(error.message); }
});

// === 3. Ładowanie języka i słów ===
async function loadAll() {
  const version = ++loadVersion;
  const data = await request(`/api/user/languages/${LANGUAGE_ID}/words`);
  if (version !== loadVersion) return;
  LANG = data.language;
  document.getElementById("language-msg").textContent = "";
  document.getElementById("language-retry").hidden = true;

  document.getElementById("lang-flag").textContent = LANG.flag;
  document.getElementById("lang-name").textContent = LANG.name_pl;
  document.getElementById("lang-native").textContent = LANG.name_native;

  renderWords(data.words.sort((a, b) => a.id - b.id));
  quickInput.disabled = false;
  document.getElementById("btn-advanced-word").disabled = false;
  refreshQuickPreview();
}

function renderWords(words) {
  WORDS = words;
  document.getElementById("word-count").textContent = words.length;
  const el = document.getElementById("word-list");

  if (!words.length) {
    el.innerHTML = `<p class="empty">Brak słów. Dodaj pierwszą parę w polach poniżej.</p>`;
    refreshQuickPreview();
    return;
  }

  el.innerHTML = "";
  words.forEach(w => {
    const div = document.createElement("div");
    div.className = "word-row" + (w.is_valid ? "" : " warning");
    div.innerHTML = `
      <div class="word-cell">
        <b>${escapeHtml(w.word)}</b>
        <span class="muted"> → </span>
        <span>${escapeHtml(w.translation_pl)}</span>
        ${(w.translation_alternatives || []).length ? `<small class="muted"> (również: ${w.translation_alternatives.map(escapeHtml).join("; ")})</small>` : ""}
        ${(w.word_alternatives || []).length ? `<small class="muted"> (inne formy: ${w.word_alternatives.map(escapeHtml).join("; ")})</small>` : ""}
      </div>
      <div class="word-actions">
        ${w.is_valid ? "" : `<span class="badge-warn" title="Słowo niezweryfikowane w zewnętrznym słowniku" aria-label="Niezweryfikowane w słowniku">⚠</span>`}
        <button class="ghost small" type="button" data-edit="${w.id}">Edytuj</button>
        <button class="ghost small danger" type="button" data-id="${w.id}">Usuń</button>
      </div>
    `;
    el.appendChild(div);
  });

  el.querySelectorAll("button[data-edit]").forEach(button => {
    button.addEventListener("click", () => openEditor(words.find(word => word.id === Number(button.dataset.edit))));
  });

  el.querySelectorAll("button[data-id]").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (savingQuick || savingWord || savingInline) return;
      if (!confirm("Usunąć to słowo?")) return;
      try {
        await request(`/api/words/${btn.dataset.id}`, "DELETE");
        await loadAll();
      } catch (error) {
        alert(error.message);
      }
    });
  });
  refreshQuickPreview();
}

function mergeWords(words) {
  // A successful write takes precedence over an earlier list refresh.
  loadVersion += 1;
  const byId = new Map(WORDS.map(word => [word.id, word]));
  words.forEach(word => byId.set(word.id, { ...byId.get(word.id), ...word }));
  renderWords([...byId.values()]);
}

// The always-visible row remains below the vocabulary as new entries arrive.
const inlineForm = document.getElementById("inline-word-form");
const inlineForeign = document.getElementById("inline-foreign");
const inlinePolish = document.getElementById("inline-polish");
const inlineSave = document.getElementById("inline-save");
const inlineMsg = document.getElementById("inline-msg");

function hasUnsavedWords() {
  return !!(quickInput.value.trim() || inlineForeign.value.trim() || inlinePolish.value.trim());
}

function refreshInlineControls() {
  const disabled = !LANG || savingInline || savingQuick || savingWord;
  [inlineForeign, inlinePolish, inlineSave].forEach(control => { control.disabled = disabled; });
  inlineSave.textContent = savingInline ? "Dodawanie…" : "Dodaj słowo";
}

for (const input of [inlineForeign, inlinePolish]) {
  input.addEventListener("input", () => { inlineMsg.textContent = ""; inlineMsg.className = "msg"; });
  input.addEventListener("keydown", event => {
    if (event.key !== "Enter" || event.isComposing) return;
    if (event.repeat) { event.preventDefault(); return; }
    if (input === inlineForeign) { event.preventDefault(); inlinePolish.focus(); }
  });
}
inlineForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!LANG || savingInline || savingQuick || savingWord) return;
  const word = cleanWordText(inlineForeign.value), translation = cleanWordText(inlinePolish.value);
  if (!word || !translation) {
    inlineMsg.className = "msg error";
    inlineMsg.textContent = "Wpisz słowo i jego polskie tłumaczenie.";
    (!word ? inlineForeign : inlinePolish).focus();
    return;
  }
  savingInline = true;
  document.getElementById("logout").disabled = true;
  document.getElementById("btn-advanced-word").disabled = true;
  inlineMsg.className = "msg";
  inlineMsg.textContent = "Dodawanie słowa…";
  refreshQuickPreview();
  try {
    const result = await request(`/api/user/languages/${LANGUAGE_ID}/words/import`, "POST", {
      words: [{ word, translation_pl: translation }],
    });
    mergeWords(result.words);
    inlineForeign.value = "";
    inlinePolish.value = "";
    inlineMsg.className = "msg ok";
    inlineMsg.textContent = result.added ? `Dodano „${word}”. Możesz wpisać kolejne słowo.` : "Ta para jest już na liście. Możesz dodać kolejne słowo.";
  } catch (error) {
    inlineMsg.className = "msg error";
    inlineMsg.textContent = error.message + " Wpisane dane zachowano. Możesz ponowić zapis.";
  } finally {
    savingInline = false;
    document.getElementById("logout").disabled = false;
    document.getElementById("btn-advanced-word").disabled = false;
    refreshQuickPreview();
    inlineForeign.focus();
  }
});

// One field accepts a single pair or a whole pasted list; no modal is needed.
const quickInput = document.getElementById("quick-input");
const quickSave = document.getElementById("quick-save");
const quickMsg = document.getElementById("quick-msg");

function refreshQuickPreview() {
  refreshInlineControls();
  const preview = previewWords(quickInput.value, WORDS);
  document.getElementById("quick-preview").hidden = !preview.rows.length && !preview.error;
  const rows = document.getElementById("quick-rows");
  rows.replaceChildren();
  for (const row of preview.rows) {
    const tr = document.createElement("tr");
    tr.dataset.status = row.status;
    for (const value of [row.line, row.word, row.translation_pl, row.message]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    }
    rows.appendChild(tr);
  }
  const count = status => preview.rows.filter(row => row.status === status).length;
  document.getElementById("quick-summary").textContent = preview.error ||
    `Nowe: ${count("new")} · Duplikaty do pominięcia: ${count("duplicate")} · Błędne wiersze: ${count("error")}`;
  quickSave.disabled = !LANG || !preview.canSave || savingQuick || savingWord || savingInline;
  quickSave.textContent = savingQuick ? "Zapisywanie…" : "Dodaj słowa";
  return preview;
}

quickInput.addEventListener("input", () => {
  quickMsg.textContent = "";
  quickMsg.className = "msg";
  refreshQuickPreview();
});
quickInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing && !event.repeat) {
    event.preventDefault();
    if (!quickSave.disabled) quickSave.click();
  }
});
quickSave.addEventListener("click", async () => {
  if (savingQuick || savingWord || savingInline || !LANG) return;
  const preview = refreshQuickPreview();
  if (!preview.canSave) return;
  savingQuick = true;
  quickInput.readOnly = true;
  document.getElementById("btn-advanced-word").disabled = true;
  document.getElementById("logout").disabled = true;
  document.querySelectorAll("#word-list button").forEach(button => { button.disabled = true; });
  quickMsg.className = "msg";
  quickMsg.textContent = "Zapisywanie całej listy…";
  refreshQuickPreview();
  try {
    const result = await request(`/api/user/languages/${LANGUAGE_ID}/words/import`, "POST", {
      words: preview.rows.map(({ word, translation_pl }) => ({ word, translation_pl })),
    });
    quickInput.value = "";
    mergeWords(result.words);
    quickMsg.className = "msg ok";
    quickMsg.textContent = `Dodano: ${result.added}. Pominięto identyczne pary: ${result.skipped}. Możesz wpisać kolejne słowa.`;
  } catch (error) {
    quickMsg.className = "msg error";
    quickMsg.textContent = error.message + " Wpisana lista pozostaje w polu. Ponowienie identycznej listy nie utworzy duplikatów.";
  } finally {
    savingQuick = false;
    quickInput.readOnly = false;
    document.getElementById("btn-advanced-word").disabled = false;
    document.getElementById("logout").disabled = false;
    document.querySelectorAll("#word-list button").forEach(button => { button.disabled = false; });
    refreshQuickPreview();
    quickInput.focus();
  }
});
window.addEventListener("beforeunload", event => {
  if (savingQuick || savingInline || hasUnsavedWords()) {
    event.preventDefault();
    event.returnValue = "";
  }
});

// === 4. Helper HTML ===
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// === 5. Modal: dodawanie słowa ===
const modal = document.getElementById("modal-word");
const msg = document.getElementById("w-msg");
const suggestionsEl = document.getElementById("w-suggest");
const inputForeign = document.getElementById("w-foreign");
const inputPolish = document.getElementById("w-polish");
const translationAlternatives = document.getElementById("w-translation-alternatives");
const wordAlternatives = document.getElementById("w-word-alternatives");
let editorVersion = 0;
let editorOpener = null;

function openEditor(word = null) {
  if (savingWord || savingQuick || savingInline || !LANG) return;
  clearTimeout(checkTimer);
  editorVersion += 1;
  if (modal.classList.contains("hidden")) editorOpener = document.activeElement;
  editingWord = word;
  document.getElementById("word-modal-title").textContent = word ? "Edytuj słowo" : "Dodaj słowo";
  inputForeign.value = word?.word || "";
  inputPolish.value = word?.translation_pl || "";
  translationAlternatives.value = (word?.translation_alternatives || []).join("\n");
  wordAlternatives.value = (word?.word_alternatives || []).join("\n");
  document.getElementById("word-options").open = !!(word?.translation_alternatives?.length || word?.word_alternatives?.length);
  document.getElementById("w-save-next").hidden = !!word;
  msg.textContent = "";
  msg.className = "msg";
  suggestionsEl.classList.add("hidden");
  suggestionsEl.innerHTML = "";
  modal.classList.remove("hidden");
  inputForeign.focus();
}
document.getElementById("btn-add-word").addEventListener("click", () => {
  inlineForm.scrollIntoView({ block: "center" });
  inlineForeign.focus();
});
document.getElementById("btn-advanced-word").addEventListener("click", () => openEditor());

function closeModal() {
  if (savingWord) return;
  editorVersion += 1;
  clearTimeout(checkTimer);
  modal.classList.add("hidden");
  if (editorOpener?.isConnected) editorOpener.focus();
  else quickInput.focus();
}
document.getElementById("modal-word-close").addEventListener("click", closeModal);
document.getElementById("w-cancel").addEventListener("click", closeModal);
modal.addEventListener("click", (e) => { if (e.target === modal && !savingWord) closeModal(); });
modal.addEventListener("keydown", event => {
  if (event.key === "Escape") { event.preventDefault(); closeModal(); }
  if (event.key !== "Tab") return;
  const focusable = [...modal.querySelectorAll("button, input, textarea, summary")]
    .filter(element => !element.disabled && element.getClientRects().length > 0);
  const first = focusable[0], last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
inputForeign.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); inputPolish.focus(); }
});
inputPolish.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.isComposing && !event.repeat) {
    event.preventDefault();
    saveWord(!editingWord);
  }
});

// Debounce walidacji przy wpisywaniu
let checkTimer = null;
inputForeign.addEventListener("input", () => {
  const v = inputForeign.value.trim();
  suggestionsEl.classList.add("hidden");
  suggestionsEl.innerHTML = "";
  if (checkTimer) clearTimeout(checkTimer);
  if (v.length < 2) return;
  checkTimer = setTimeout(() => checkWord(v), 600);
});

async function checkWord(word) {
  const version = editorVersion;
  try {
    const data = await request(
      `/api/dictionary/check?lang=${encodeURIComponent(LANG.code)}&word=${encodeURIComponent(word)}`
    );
    if (version !== editorVersion || modal.classList.contains("hidden") || inputForeign.value.trim() !== word) return;
    if (!data.exists && data.suggestions?.length) {
      suggestionsEl.innerHTML = `<span class="muted">Czy chodziło Ci o:</span> ` +
        data.suggestions.map(s =>
          `<button class="suggestion" type="button" data-word="${escapeHtml(s)}">${escapeHtml(s)}</button>`
        ).join(" ");
      suggestionsEl.classList.remove("hidden");
      suggestionsEl.querySelectorAll("button.suggestion").forEach(btn => {
        btn.addEventListener("click", () => {
          inputForeign.value = btn.dataset.word;
          suggestionsEl.classList.add("hidden");
        });
      });
    }
  } catch (e) {
    console.warn("checkWord error:", e);
  }
}

// === 6. Zapis słowa ===
document.getElementById("w-save").addEventListener("click", () => saveWord(false));
document.getElementById("w-save-next").addEventListener("click", () => saveWord(true));
async function saveWord(keepOpen = false) {
  if (savingWord || savingQuick || savingInline || !LANG) return;
  const word = inputForeign.value.trim();
  const translation = inputPolish.value.trim();
  msg.className = "msg";

  if (!word || !translation) {
    msg.classList.add("error");
    msg.textContent = "Uzupełnij oba pola.";
    return;
  }

  const variants = input => input.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  const edited = editingWord;
  const payload = {
    word, translation_pl: translation, is_valid: edited?.word === word ? edited.is_valid : false,
    translation_alternatives: variants(translationAlternatives), word_alternatives: variants(wordAlternatives),
  };
  const controls = ["w-save", "w-save-next", "w-cancel", "modal-word-close", "w-foreign", "w-polish", "w-translation-alternatives", "w-word-alternatives"].map(id => document.getElementById(id));
  savingWord = true;
  controls.forEach(control => { control.disabled = true; });
  document.getElementById("logout").disabled = true;
  refreshQuickPreview();
  msg.textContent = "Zapisywanie…";
  try {
    if (edited?.word !== word) {
      try {
        const check = await request(`/api/dictionary/check?lang=${encodeURIComponent(LANG.code)}&word=${encodeURIComponent(word)}`);
        payload.is_valid = !!check.exists;
        if (!payload.is_valid && !confirm(`Słowo „${word}" nie zostało znalezione. Zapisać jako niezweryfikowane?`)) {
          msg.textContent = "Zapis anulowany. Wpisane dane zachowano.";
          return;
        }
      } catch {
        payload.is_valid = false;
        if (!confirm("Nie udało się zweryfikować słowa. Zapisać jako niezweryfikowane?")) {
          msg.textContent = "Zapis anulowany. Wpisane dane zachowano.";
          return;
        }
      }
    }
    const result = await request(edited ? `/api/words/${edited.id}` : `/api/user/languages/${LANGUAGE_ID}/words`, edited ? "PUT" : "POST", payload);
    mergeWords([result.word]);
    savingWord = false;
    if (keepOpen && !edited) {
      openEditor();
      msg.className = "msg ok";
      msg.textContent = `Dodano „${word}”. Wpisz kolejne słowo.`;
    } else closeModal();
  } catch (error) {
    msg.classList.add("error");
    msg.textContent = error.message + " Wpisane dane zachowano w formularzu.";
  } finally {
    savingWord = false;
    document.getElementById("logout").disabled = false;
    controls.forEach(control => { control.disabled = false; });
    refreshQuickPreview();
    if (!modal.classList.contains("hidden")) inputForeign.focus();
  }
}

// === 7. Przycisk „Ucz się" → /study?id=N ===
const btnStudy = document.getElementById("btn-study");
if (btnStudy) {
  btnStudy.addEventListener("click", () => {
    window.location.href = `/study?id=${LANGUAGE_ID}`;
  });
} else {
  console.warn("[language.js] Brak elementu #btn-study w HTML.");
}

// === 8. Start ===
async function refreshLanguage() {
  const retry = document.getElementById("language-retry");
  retry.disabled = true;
  try { await loadAll(); }
  catch (error) {
    document.getElementById("language-msg").textContent = error.message;
    document.getElementById("language-msg").className = "msg error";
    retry.hidden = false;
    if (error.status === 401) window.location.href = "/";
  } finally { retry.disabled = false; }
}
document.getElementById("language-retry").addEventListener("click", refreshLanguage);
refreshLanguage();
