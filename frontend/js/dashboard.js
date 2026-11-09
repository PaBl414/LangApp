import { formatError } from "./api-errors.js";

// Wylogowanie
document.getElementById("logout").addEventListener("click", async () => {
  try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) {}
  window.location.href = "/";
});

// Pobierz dane użytkownika
(async () => {
  const res = await fetch("/api/me", { credentials: "same-origin" });
  if (!res.ok) { window.location.href = "/"; return; }
  const me = await res.json();
  document.getElementById("user-login").textContent = me.login;
})();

// === Moje języki ===
const myLangsEl = document.getElementById("my-languages");

async function loadMyLanguages() {
  const res = await fetch("/api/user/languages", { credentials: "same-origin" });
  const langs = await res.json();
  if (!langs.length) {
    myLangsEl.innerHTML = `<p class="empty">Nie masz jeszcze żadnego języka. Kliknij „+ Dodaj język".</p>`;
    return;
  }
  myLangsEl.innerHTML = "";
  langs.forEach(l => {
    const tile = document.createElement("article");
    tile.className = "tile";
    tile.innerHTML = `
      <div class="tile-flag">${l.flag}</div>
      <h3>${l.name_pl}</h3>
      <p class="muted">${l.name_native}</p>
      <button class="ghost small danger" data-ulid="${l.user_language_id}">Usuń</button>
    `;
    tile.addEventListener("click", (e) => {
      if (e.target.tagName === "BUTTON") return;
      window.location.href = `/language?id=${l.id}`;
    });
    myLangsEl.appendChild(tile);
  });
  myLangsEl.querySelectorAll("button[data-ulid]").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Usunąć język wraz ze słowami, historią quizów i postępem? Tej operacji nie można cofnąć.")) return;
      try {
        const res = await fetch(`/api/user/languages/${btn.dataset.ulid}`, { method: "DELETE" });
        if (!res.ok) {
          alert(formatError(await res.json().catch(() => ({}))));
          return;
        }
        await loadMyLanguages();
      } catch {
        alert("Błąd sieci. Nie udało się potwierdzić usunięcia języka.");
      }
    });
  });
}
loadMyLanguages();

// === Modal: dodawanie języka ===
const modal = document.getElementById("modal-lang");
const langList = document.getElementById("lang-list");
const langSearch = document.getElementById("lang-search");
let allLanguages = [];

document.getElementById("btn-add-language").addEventListener("click", async () => {
  if (!allLanguages.length) {
    const res = await fetch("/api/languages");
    allLanguages = await res.json();
  }
  renderLangList(allLanguages);
  modal.classList.remove("hidden");
  langSearch.focus();
});

document.getElementById("modal-close").addEventListener("click", () => modal.classList.add("hidden"));
modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.add("hidden"); });

langSearch.addEventListener("input", () => {
  const q = langSearch.value.toLowerCase();
  renderLangList(allLanguages.filter(l =>
    l.name_pl.toLowerCase().includes(q) || l.name_native.toLowerCase().includes(q)
  ));
});

function renderLangList(list) {
  langList.innerHTML = "";
  if (!list.length) {
    langList.innerHTML = `<li class="muted" style="padding:8px;">Brak wyników</li>`;
    return;
  }
  list.forEach(l => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="flag">${l.flag}</span> <b>${l.name_pl}</b> <span class="muted">${l.name_native}</span>`;
    li.addEventListener("click", async () => {
      const res = await fetch("/api/user/languages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language_id: l.id }),
      });
      if (res.ok || res.status === 409) {
        modal.classList.add("hidden");
        loadMyLanguages();
      } else {
        alert("Nie udało się dodać języka.");
      }
    });
    langList.appendChild(li);
  });
}
