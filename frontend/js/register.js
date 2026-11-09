import { getFingerprint, getCookieId } from "./fingerprint.js";
import { request } from "./api-client.js";

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
  const form = e.currentTarget, button = form.querySelector('button[type="submit"]');
  if (button.disabled) return;
  button.disabled = true;
  const msg = document.getElementById("register-msg");
  msg.className = "msg";
  msg.textContent = "Przetwarzanie…";

  const fd = new FormData(e.target);
  const login = fd.get("login")?.trim();
  const password = fd.get("password");
  const password_confirm = fd.get("password_confirm");

  let completed = false;
  try {
    await request("/api/auth/register", "POST", {
      login, password, password_confirm, fingerprint: await getFingerprint(), cookie_id: getCookieId(),
    });
    completed = true;
    msg.className = "msg ok";
    msg.textContent = "Konto utworzone! Przekierowanie…";
    setTimeout(() => (window.location.href = "/dashboard"), 800);
  } catch (error) {
    msg.className = "msg error";
    msg.textContent = error.message;
  } finally { button.disabled = completed; }
});
