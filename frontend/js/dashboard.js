document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/";
});

(async () => {
  const res = await fetch("/api/me");
  if (!res.ok) {
    window.location.href = "/";
    return;
  }
  const me = await res.json();
  document.getElementById("user-login").textContent = me.login;
})();