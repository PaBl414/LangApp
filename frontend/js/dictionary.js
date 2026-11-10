import { request } from "./api-client.js";

export const DICTIONARY_PREFERENCE = "langapp.dictionary.enabled.v1";
let memoryPreference = true;

export function readDictionaryPreference() {
  try {
    const value = localStorage.getItem(DICTIONARY_PREFERENCE);
    memoryPreference = value !== "0";
  } catch { /* Storage may be blocked; the toggle still works for this page. */ }
  return memoryPreference;
}

export function saveDictionaryPreference(enabled) {
  memoryPreference = enabled;
  try { localStorage.setItem(DICTIONARY_PREFERENCE, enabled ? "1" : "0"); } catch { /* Keep the in-memory choice. */ }
}

export function dictionaryMessage(result) {
  switch (result?.status) {
    case "found": return result.source === "wiktionary" ? "Znaleziono wpis w Wiktionary." : "Znaleziono wpis w słowniku.";
    case "not_found": return "Brak wpisu w dostępnych słownikach. Możesz zapisać słowo.";
    case "unsupported": return "Sprawdzanie tego języka nie jest obsługiwane. Możesz zapisać słowo.";
    case "disabled": return "";
    default: return "Słownik chwilowo niedostępny. Możesz zapisać słowo.";
  }
}

// Each input owns a generation counter. Toggling off, editing or closing the
// editor invalidates both delayed work and responses already in flight.
export function createWordChecker({ input, feedback, suggestions = null, getLanguage, isSupported, delay = 700, lookup = request }) {
  let enabled = false, timer = null, generation = 0;
  let choices = [], active = -1, chosenWord = null;
  function closeSuggestions() {
    choices = [];
    active = -1;
    if (!suggestions) return;
    suggestions.replaceChildren();
    suggestions.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }
  function choose(word) {
    if (!enabled || !choices.includes(word)) return;
    chosenWord = word;
    input.value = word;
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.focus();
  }
  function renderSuggestions(result, word) {
    closeSuggestions();
    if (!suggestions || !Array.isArray(result?.suggestions)) return;
    const key = value => value.normalize("NFC").toLowerCase();
    choices = [...new Set(result.suggestions.filter(value => typeof value === "string" &&
      [...value].length <= 128 && value.trim() && value !== word && key(value).startsWith(key(word))))].slice(0, 5);
    for (const [index, value] of choices.entries()) {
      const button = suggestions.ownerDocument.createElement("button");
      button.type = "button";
      button.id = `${suggestions.id}-${index}`;
      button.tabIndex = -1;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.textContent = value;
      button.addEventListener("mousedown", event => event.preventDefault());
      button.addEventListener("click", () => choose(value));
      suggestions.appendChild(button);
    }
    suggestions.hidden = choices.length === 0;
    input.setAttribute("aria-expanded", choices.length ? "true" : "false");
    if (choices.length && result?.status === "not_found") feedback.textContent = "Wybierz podpowiedź lub dokończ słowo.";
  }
  if (suggestions) {
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", suggestions.id);
    input.setAttribute("aria-expanded", "false");
    input.addEventListener("keydown", event => {
      if (event.isComposing || !choices.length) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        event.stopImmediatePropagation();
        active = event.key === "ArrowDown" ? (active + 1) % choices.length : (active < 0 ? choices.length - 1 : (active + choices.length - 1) % choices.length);
        [...suggestions.children].forEach((button, index) => button.setAttribute("aria-selected", String(index === active)));
        input.setAttribute("aria-activedescendant", `${suggestions.id}-${active}`);
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        event.stopImmediatePropagation();
        choose(choices[active]);
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeSuggestions();
      } else if (event.key === "Tab") closeSuggestions();
    }, true);
    input.addEventListener("blur", event => {
      if (!suggestions.contains(event.relatedTarget)) {
        generation += 1;
        clearTimeout(timer);
        closeSuggestions();
        if (feedback.textContent === "Sprawdzanie słowa…") feedback.textContent = "";
      }
    });
  }
  function invalidate() {
    generation += 1;
    clearTimeout(timer);
    feedback.textContent = "";
    feedback.className = "msg dictionary-feedback";
    closeSuggestions();
  }
  function schedule() {
    invalidate();
    const word = input.value.trim(), lang = getLanguage();
    if (word !== chosenWord) chosenWord = null;
    if (!enabled || !word || !lang) return;
    if (!isSupported(lang)) {
      feedback.textContent = dictionaryMessage({status: "unsupported"});
      return;
    }
    if ([...word].length > 128) return;
    const version = generation;
    timer = setTimeout(async () => {
      feedback.textContent = "Sprawdzanie słowa…";
      let result;
      try {
        result = await lookup(`/api/dictionary/check?lang=${encodeURIComponent(lang)}&word=${encodeURIComponent(word)}` +
          (suggestions && [...word].length >= 2 && !chosenWord ? "&suggest=true" : ""));
      } catch { result = {status: "unavailable"}; }
      if (!enabled || version !== generation || input.value.trim() !== word) return;
      feedback.textContent = dictionaryMessage(result);
      feedback.className = "msg dictionary-feedback" + (result?.status === "found" ? " ok" : "");
      renderSuggestions(result, word);
    }, delay);
  }
  input.addEventListener("input", schedule);
  return { invalidate, schedule, setEnabled(value) { enabled = value; schedule(); } };
}
