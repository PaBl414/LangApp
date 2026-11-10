import { matchingRound, shuffled } from "./learning-ui.js";

export function createPractice({onOpen, onClose}) {
  const $ = id => document.getElementById(id);
  let words = [], deck = [], index = 0, revealed = false, mode = "cards";
  let round = null, left = null, right = null, mistakes = 0, wrong = null;
  const matched = new Set();
  const toPolish = () => $("practice-direction").value === "lang_to_pl";
  function setWords(values) {
    words = values.map((word, key) => ({...word, practice_key: key}));
  }
  function card() {
    const word = deck[index];
    if (!word) return;
    $("practice-count").textContent = `Fiszka ${index + 1} z ${deck.length}`;
    $("practice-card-side").textContent = revealed ? "Odpowiedź" : toPolish() ? "Przetłumacz na polski" : "Przetłumacz na język obcy";
    $("practice-card-text").textContent = revealed ? (toPolish() ? word.translation_pl : word.word) : (toPolish() ? word.word : word.translation_pl);
    const aliases = toPolish() ? word.translation_alternatives : word.word_alternatives;
    $("practice-card-hint").textContent = revealed ? "Kliknij, aby wrócić do pytania" : "Kliknij kartę lub naciśnij Spację, aby odsłonić";
    $("practice-card-extra").textContent = revealed && aliases?.length ? "Również: " + aliases.join(" · ") : "";
    $("practice-example").textContent = (toPolish() ? word.example_sentence : word.example_translation) || "";
    $("practice-example-translation").textContent = revealed ? (toPolish() ? word.example_translation : word.example_sentence) || "" : "";
    $("practice-card").classList.toggle("revealed", revealed);
    $("practice-card").setAttribute("aria-pressed", String(revealed));
    $("practice-previous").disabled = index === 0;
    $("practice-next").disabled = index === deck.length - 1;
    $("practice-feedback").textContent = "";
  }
  function step(delta) { index = Math.max(0, Math.min(deck.length - 1, index + delta)); revealed = false; card(); $("practice-card").focus(); }
  function updateMatching() {
    for (const button of $("practice-pairs").querySelectorAll("button")) {
      const key = Number(button.dataset.key), side = button.dataset.side;
      button.disabled = matched.has(key);
      button.classList.toggle("matched", matched.has(key));
      button.classList.toggle("miss", !!wrong && wrong[side] === key);
      button.setAttribute("aria-pressed", String(side === "left" ? left === key : right === key));
    }
    $("practice-count").textContent = `Połączono ${matched.size} z ${round.left.length} par · pomyłki: ${mistakes}`;
    $("practice-new-round").textContent = matched.size === round.left.length ? "Kolejna runda →" : "Wylosuj inne pary";
  }
  function pick(side, key) {
    if (matched.has(key)) return;
    wrong = null;
    if (side === "left") left = left === key ? null : key;
    else right = right === key ? null : key;
    if (left !== null && right !== null) {
      if (left === right) {
        matched.add(left); left = right = null;
        $("practice-feedback").textContent = matched.size === round.left.length ? "Wszystkie pary połączone. Dobra robota!" : "Dobra para! Wybierz następną.";
        $("practice-feedback").className = "msg ok";
      } else {
        mistakes += 1; wrong = {left, right}; left = right = null;
        $("practice-feedback").textContent = "Te słowa nie tworzą pary. Spróbuj ponownie.";
        $("practice-feedback").className = "msg error";
      }
    } else $("practice-feedback").textContent = "Wybierz pasujące słowo w drugiej kolumnie.";
    updateMatching();
    if (matched.size === round.left.length) $("practice-new-round").focus();
    else if ($("practice-pairs").contains(document.activeElement) && document.activeElement.disabled) {
      $("practice-pairs").querySelector('button:not(:disabled)')?.focus();
    }
  }
  function newRound() {
    round = matchingRound(words);
    left = right = wrong = null; mistakes = 0; matched.clear();
    $("practice-pairs").replaceChildren();
    if (round.left.length < 2) {
      $("practice-feedback").textContent = "Do łączenia par potrzebujesz co najmniej dwóch słów z różnymi tłumaczeniami. Możesz teraz wybrać fiszki.";
      $("practice-feedback").className = "msg";
      $("practice-count").textContent = "Za mało różnych par";
      $("practice-new-round").disabled = true;
      return;
    }
    $("practice-new-round").disabled = false;
    for (const side of ["left", "right"]) {
      const column = document.createElement("div"); column.className = "pair-column";
      const heading = document.createElement("h3"); heading.textContent = (side === "left") === toPolish() ? "Język obcy" : "Polski";
      column.append(heading);
      for (const word of round[side]) {
        const button = document.createElement("button"); button.type = "button"; button.className = "pair-choice";
        button.dataset.side = side; button.dataset.key = word.practice_key;
        button.textContent = (side === "left") === toPolish() ? word.word : word.translation_pl;
        button.addEventListener("click", () => pick(side, word.practice_key)); column.append(button);
      }
      $("practice-pairs").append(column);
    }
    $("practice-feedback").textContent = "Wybierz jedno słowo z każdej kolumny.";
    $("practice-feedback").className = "msg";
    updateMatching();
  }
  function start(value = "cards") {
    if (!words.length) return false;
    mode = value;
    $("practice-cards").hidden = mode !== "cards";
    $("practice-matching").hidden = mode !== "matching";
    $("practice-title").textContent = mode === "cards" ? "Fiszki" : "Połącz pary";
    $("practice-feedback").textContent = "";
    $("practice-feedback").className = "msg";
    onOpen();
    if (mode === "cards") { deck = shuffled(words); index = 0; revealed = false; card(); $("practice-card").focus(); }
    else { newRound(); $("practice-pairs").querySelector("button")?.focus(); }
    return true;
  }
  $("practice-card").addEventListener("click", () => { revealed = !revealed; card(); });
  $("practice-previous").addEventListener("click", () => step(-1));
  $("practice-next").addEventListener("click", () => step(1));
  $("practice-shuffle").addEventListener("click", () => start("cards"));
  $("practice-new-round").addEventListener("click", newRound);
  $("practice-direction").addEventListener("change", () => start(mode));
  $("practice-switch").addEventListener("click", () => start(mode === "cards" ? "matching" : "cards"));
  $("practice-close").addEventListener("click", onClose);
  $("screen-practice").addEventListener("keydown", event => {
    if (mode !== "cards" || event.isComposing || ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); step(event.key === "ArrowRight" ? 1 : -1); }
  });
  return {setWords, start};
}
