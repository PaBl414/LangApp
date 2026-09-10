import { getFingerprint, getCookieId } from "./fingerprint.js";

// Ustawianie cookie identyfikatora od razu przy wejściu na stronę
getCookieId();
function formatError(data) {
  if (!data) return "";
  const x = data.detail;
  if (typeof x === "string") return x;
  if (Array.isArray(x)) {
    return x.map(e => {
      const f = Array.isArray(e.loc) ? e.loc.filter(v => v !== "body").join(".") : "";
      return f ? `${f}: ${e.msg}` : e.msg;
    }).join("\n");
  }
  return JSON.stringify(x);
}

// Przełączanie zakładek
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".form").forEach(f => f.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`${btn.dataset.tab}-form`).classList.add("active");
  });
});

// Kryteria hasła — animowany wskaźnik
const passwordInput = document.getElementById("reg-password");
const criteriaEls = document.querySelectorAll("#criteria li");

const checks = {
  len:     v => v.length >= 6,
  upper:   v => /[A-Z]/.test(v),
  digit:   v => /\d/.test(v),
  special: v => /[^A-Za-z0-9]/.test(v),
};

function updateCriteria() {
  const v = passwordInput.value;
  criteriaEls.forEach(el => {
    const k = el.dataset.crit;
    const ok = checks[k](v);
    el.classList.toggle("ok", ok && v.length > 0);
    el.classList.toggle("bad", !ok && v.length > 0);
  });
}
passwordInput.addEventListener("input", updateCriteria);

// Wysyłka formularza rejestracji
document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("register-msg");
  msg.className = "msg";
  msg.textContent = "Przetwarzanie…";

  const fd = new FormData(e.target);
  const login = fd.get("login")?.trim();
  const password = fd.get("password");
  const password_confirm = fd.get("password_confirm");

  let fingerprint, cookie_id;
  try {
    fingerprint = await getFingerprint();
    cookie_id = getCookieId();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Błąd inicjalizacji: " + err.message;
    return;
  }

  const payload = { login, password, password_confirm, fingerprint, cookie_id };

  let res, data;
  try {
    res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    data = await res.json().catch(() => ({}));
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Błąd sieci: " + err.message;
    return;
  }

  if (!res.ok) {
    msg.className = "msg error";
    msg.textContent = formatError(data) || `Błąd rejestracji (HTTP ${res.status}).`;
    return;
  }

  msg.className = "msg ok";
  msg.textContent = "Konto utworzone! Przekierowanie…";
  setTimeout(() => (window.location.href = "/dashboard"), 800);
});