import { getFingerprint, getCookieId } from "./fingerprint.js";
import { request } from "./api-client.js";

document.getElementById("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget, button = form.querySelector('button[type="submit"]');
  if (button.disabled) return;
  const msg = document.getElementById("login-msg"), data = new FormData(form);
  button.disabled = true; msg.className = "msg"; msg.textContent = "Logowanie…";
  try {
    await request("/api/auth/login", "POST", {
      login: data.get("login")?.trim(), password: data.get("password"),
      fingerprint: await getFingerprint(), cookie_id: getCookieId(),
    });
    window.location.href = "/dashboard";
  } catch (error) { msg.className = "msg error"; msg.textContent = error.message; }
  finally { button.disabled = false; }
});
