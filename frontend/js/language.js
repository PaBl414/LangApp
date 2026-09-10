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

// === 2. Wylogowanie ===
document.getElementById("logout").addEventListener("click", async () => {
  try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) {}
  window.location.href = "/";
});

// === 3. Ładowanie języka i słów ===
async function loadAll() {
  const res = await fetch(`/api/user/languages/${LANGUAGE_ID}/words`, {
    credentials: "same-origin",
  });
  if (!res.ok) {
    if (res.status === 401) { window.location.href = "/"; return; }
    alert("Nie udało się załadować danych języka.");
    window.location.href = "/dashboard";
    return;
  }
  const data = await res.json();
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
      </div>
      <div class="word-actions">
        ${w.is_valid ? "" : `<span class="badge-warn" title="Słowo spoza bazy API">⚠</span>`}
        <button class="ghost small danger" type="button" data-id="${w.id}">Usuń</button>
      </div>
    `;
    el.appendChild(div);
  });

  el.querySelectorAll("button[data-id]").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Usunąć to słowo?")) return;
      await fetch(`/api/words/${btn.dataset.id}`, { method: "DELETE" });
      loadAll();
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

document.getElementById("btn-add-word").addEventListener("click", () => {
  inputForeign.value = "";
  inputPolish.value = "";
  msg.textContent = "";
  msg.className = "msg";
  suggestionsEl.classList.add("hidden");
  suggestionsEl.innerHTML = "";
  modal.classList.remove("hidden");
  inputForeign.focus();
});

function closeModal() { modal.classList.add("hidden"); }
document.getElementById("modal-word-close").addEventListener("click", closeModal);
document.getElementById("w-cancel").addEventListener("click", closeModal);
modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

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
    const res = await fetch(
      `/api/dictionary/check?lang=${encodeURIComponent(LANG.code)}&word=${encodeURIComponent(word)}`
    );
    if (!res.ok) return;
    const data = await res.json();
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
  const word = inputForeign.value.trim();
  const translation = inputPolish.value.trim();
  msg.className = "msg";

  if (!word || !translation) {
    msg.classList.add("error");
    msg.textContent = "Uzupełnij oba pola.";
    return;
  }

  let is_valid = true;
  try {
    const chk = await fetch(
      `/api/dictionary/check?lang=${encodeURIComponent(LANG.code)}&word=${encodeURIComponent(word)}`
    );
    if (chk.ok) {
      const info = await chk.json();
      is_valid = !!info.exists;
      if (!info.exists && !confirm(
        `Słowo „${word}" nie zostało znalezione w bazie API.\n` +
        `Dodać mimo to (zostanie oznaczone jako niezweryfikowane)?`
      )) {
        return;
      }
    }
  } catch (e) {
    is_valid = false;
    if (!confirm("Nie udało się zweryfikować słowa (brak internetu?). Dodać mimo to?")) return;
  }

  const res = await fetch(`/api/user/languages/${LANGUAGE_ID}/words`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word, translation_pl: translation, is_valid }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    msg.classList.add("error");
    msg.textContent = data.detail || `Błąd (HTTP ${res.status}).`;
    return;
  }
  closeModal();
  loadAll();
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
loadAll();