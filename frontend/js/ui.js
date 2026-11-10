export function notify(message, tone = "ok", action = null) {
  let region = document.getElementById("toast-region");
  if (!region) {
    region = document.createElement("div"); region.id = "toast-region";
    region.setAttribute("role", "status"); region.setAttribute("aria-live", "polite");
    document.body.append(region);
  }
  region.replaceChildren();
  const toast = document.createElement("div"); toast.className = `toast ${tone}`;
  const text = document.createElement("span"); text.textContent = message;
  const close = document.createElement("button"); close.type = "button"; close.textContent = "×";
  close.className = "ghost"; close.setAttribute("aria-label", "Zamknij komunikat");
  close.addEventListener("click", () => toast.remove());
  toast.append(text);
  let timer = null;
  if (action) {
    const button = document.createElement("button"); button.type = "button"; button.className = "ghost"; button.textContent = action.label;
    button.addEventListener("click", async () => {
      clearTimeout(timer); button.disabled = true;
      try { await action.onClick(); toast.remove(); }
      catch (error) { text.textContent = error.message; toast.className = "toast error"; button.disabled = false; }
    });
    toast.append(button);
  }
  toast.append(close); region.append(toast);
  timer = setTimeout(() => toast.remove(), 5000);
}

export function confirmAction({title = "Potwierdź działanie", message, label = "Potwierdź"}) {
  return new Promise(resolve => {
    const opener = document.activeElement;
    const dialog = document.createElement("dialog"); dialog.className = "action-dialog";
    const heading = document.createElement("h2"); heading.id = "action-dialog-title"; heading.textContent = title;
    dialog.setAttribute("aria-labelledby", heading.id);
    const description = document.createElement("p"); description.textContent = message;
    const actions = document.createElement("div"); actions.className = "dialog-actions";
    const cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "ghost"; cancel.textContent = "Anuluj";
    const accept = document.createElement("button"); accept.type = "button"; accept.className = "primary"; accept.textContent = label;
    let settled = false;
    function finish(confirmed) {
      if (settled) return;
      settled = true;
      if (dialog.open) dialog.close(confirmed ? "confirm" : "cancel");
      dialog.remove();
      if (opener?.isConnected) opener.focus();
      resolve(confirmed);
    }
    cancel.addEventListener("click", () => finish(false));
    accept.addEventListener("click", () => finish(true));
    dialog.addEventListener("cancel", event => { event.preventDefault(); finish(false); });
    dialog.addEventListener("close", () => finish(dialog.returnValue === "confirm"), {once: true});
    actions.append(cancel, accept); dialog.append(heading, description, actions); document.body.append(dialog);
    dialog.showModal(); cancel.focus();
  });
}
