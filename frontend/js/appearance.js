// Runs before the stylesheet to apply saved appearance without a theme flash.
(() => {
  const themeKey = "langapp.appearance.theme.v1", sizeKey = "langapp.appearance.text.v1";
  const root = document.documentElement;
  const themes = ["system", "light", "dark"], sizes = ["standard", "large"];
  function read(key, allowed, fallback) {
    try { const value = localStorage.getItem(key); return allowed.includes(value) ? value : fallback; }
    catch { return fallback; }
  }
  function apply() {
    root.dataset.theme = read(themeKey, themes, "system");
    root.dataset.textSize = read(sizeKey, sizes, "standard");
  }
  apply();
  function build() {
    const details = document.createElement("details"); details.className = "appearance-settings";
    const summary = document.createElement("summary"); summary.textContent = "Wygląd";
    summary.setAttribute("aria-label", "Ustawienia wyglądu");
    const panel = document.createElement("div"); panel.className = "appearance-panel";
    const status = document.createElement("p"); status.className = "msg"; status.setAttribute("role", "status");
    function control(title, values, selected, key, attribute, id) {
      const label = document.createElement("label"); label.textContent = title;
      const select = document.createElement("select"); select.id = id;
      for (const [value, text] of values) { const option = document.createElement("option"); option.value = value; option.textContent = text; select.append(option); }
      select.value = selected;
      select.addEventListener("change", () => {
        root.dataset[attribute] = select.value;
        try { localStorage.setItem(key, select.value); status.textContent = "Ustawienie zapisane."; }
        catch { status.textContent = "Ustawienie działa na tej stronie. Przeglądarka blokuje jego zapamiętanie."; }
      });
      label.append(select); panel.append(label); return select;
    }
    const theme = control("Motyw", [["system", "Zgodny z systemem"], ["light", "Jasny"], ["dark", "Ciemny"]], root.dataset.theme, themeKey, "theme", "appearance-theme");
    const size = control("Wielkość tekstu", [["standard", "Standardowa"], ["large", "Większa"]], root.dataset.textSize, sizeKey, "textSize", "appearance-text");
    panel.append(status); details.append(summary, panel);
    const topbar = document.querySelector(".topbar");
    if (topbar) {
      const actions = document.createElement("div"); actions.className = "topbar-actions";
      actions.append(details);
      const logout = document.getElementById("logout"); if (logout) actions.append(logout);
      topbar.append(actions);
    } else { details.classList.add("auth-appearance"); document.body.prepend(details); }
    window.addEventListener("storage", event => {
      if ([null, themeKey, sizeKey].includes(event.key)) { apply(); theme.value = root.dataset.theme; size.value = root.dataset.textSize; status.textContent = ""; }
    });
    document.addEventListener("click", event => { if (!details.contains(event.target)) details.open = false; });
    details.addEventListener("keydown", event => { if (event.key === "Escape") { details.open = false; summary.focus(); event.preventDefault(); } });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build, {once: true}); else build();
})();
