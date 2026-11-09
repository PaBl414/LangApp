import { request } from "./api-client.js";

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

// === 2. Wylogowanie ===
document.getElementById("logout").addEventListener("click", async () => {
  try { await request("/api/auth/logout", "POST"); window.location.href = "/"; }
  catch (error) { alert(error.message); }
});

// === 3. Ładowanie języka i słów ===
async function loadAll() {
  const data = await request(`/api/user/languages/${LANGUAGE_ID}/words`);
  LANG = data.language;

  document.getElementById("lang-flag").textContent = LANG.flag;
  document.getElementById("lang-name").textContent = LANG.name_pl;
  document.getElementById("lang-native").textContent = LANG.name_native;

  renderWords(data.words);
}

function renderWords(words) {
  document.getElementById("word-count").textContent = words.length;
  const el = document.getElementById("word-list");

  if (!words.length) {
    el.innerHTML = `<p class="empty">Brak słów. Kliknij „+ Dodaj słowo".</p>`;
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
        ${w.is_valid ? "" : `<span class="badge-warn" title="Słowo spoza bazy API">⚠</span>`}
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
      if (!confirm("Usunąć to słowo?")) return;
      try {
        await request(`/api/words/${btn.dataset.id}`, "DELETE");
        await loadAll();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

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

function openEditor(word = null) {
  if (savingWord) return;
  editingWord = word;
  document.getElementById("word-modal-title").textContent = word ? "Edytuj słowo" : "Dodaj słowo";
  inputForeign.value = word?.word || "";
  inputPolish.value = word?.translation_pl || "";
  translationAlternatives.value = (word?.translation_alternatives || []).join("\n");
  wordAlternatives.value = (word?.word_alternatives || []).join("\n");
  msg.textContent = "";
  msg.className = "msg";
  suggestionsEl.classList.add("hidden");
  suggestionsEl.innerHTML = "";
  modal.classList.remove("hidden");
  inputForeign.focus();
}
document.getElementById("btn-add-word").addEventListener("click", () => openEditor());

function closeModal() { modal.classList.add("hidden"); }
document.getElementById("modal-word-close").addEventListener("click", closeModal);
document.getElementById("w-cancel").addEventListener("click", closeModal);
modal.addEventListener("click", (e) => { if (e.target === modal && !savingWord) closeModal(); });

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
  try {
    const data = await request(
      `/api/dictionary/check?lang=${encodeURIComponent(LANG.code)}&word=${encodeURIComponent(word)}`
    );
    if (inputForeign.value.trim() !== word) return;
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
document.getElementById("w-save").addEventListener("click", async () => {
  if (savingWord) return;
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
  const controls = ["w-save", "w-cancel", "modal-word-close", "w-foreign", "w-polish", "w-translation-alternatives", "w-word-alternatives"].map(id => document.getElementById(id));
  savingWord = true;
  controls.forEach(control => { control.disabled = true; });
  msg.textContent = "Zapisywanie…";
  try {
    if (edited?.word !== word) {
      try {
        const check = await request(`/api/dictionary/check?lang=${encodeURIComponent(LANG.code)}&word=${encodeURIComponent(word)}`);
        payload.is_valid = !!check.exists;
        if (!payload.is_valid && !confirm(`Słowo „${word}" nie zostało znalezione. Zapisać jako niezweryfikowane?`)) return;
      } catch {
        payload.is_valid = false;
        if (!confirm("Nie udało się zweryfikować słowa. Zapisać jako niezweryfikowane?")) return;
      }
    }
    await request(edited ? `/api/words/${edited.id}` : `/api/user/languages/${LANGUAGE_ID}/words`, edited ? "PUT" : "POST", payload);
    closeModal();
    await loadAll();
  } catch (error) {
    msg.classList.add("error");
    msg.textContent = error.message + " Wpisane dane zachowano w formularzu.";
  } finally { savingWord = false; controls.forEach(control => { control.disabled = false; }); }
});

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
loadAll().catch(error => { alert(error.message); if (error.status === 401) window.location.href = "/"; });
