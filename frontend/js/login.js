import { getFingerprint, getCookieId } from "./fingerprint.js";

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

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("login-msg");
  msg.className = "msg";
  msg.textContent = "Logowanie…";

  const fd = new FormData(e.target);
  const login = fd.get("login")?.trim();
  const password = fd.get("password");

  let fingerprint, cookie_id;
  try {
    fingerprint = await getFingerprint();
    cookie_id = getCookieId();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Błąd inicjalizacji: " + err.message;
    return;
  }

  const payload = { login, password, fingerprint, cookie_id };

  let res, data;
  try {
    res = await fetch("/api/auth/login", {
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
    msg.textContent = formatError(data) || `Błąd logowania (HTTP ${res.status}).`;
    return;
  }

  window.location.href = "/dashboard";
});