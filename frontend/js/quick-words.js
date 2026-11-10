// Paste format: one pair per line, separated by '=' or a spreadsheet tab.
// Commas, slashes and punctuation remain literal translation content.
export const MAX_QUICK_WORDS = 100;
export const cleanWordText = value => value.normalize("NFC").replace(/\s+/gu, " ").trim();
const keyFor = value => cleanWordText(value).toLowerCase();

export function previewWords(text, existing = []) {
  if (text.length > 60000) return { rows: [], error: "Lista jest za długa. Wklej maksymalnie 100 par słów.", canSave: false };
  const known = new Map();
  for (const word of existing) {
    const key = keyFor(word.word);
    known.set(key, [...(known.get(key) || []), keyFor(word.translation_pl)]);
  }
  const rows = [];
  for (const [index, raw] of text.replace(/^\uFEFF/u, "").split(/\r\n|\n|\r/u).entries()) {
    if (!raw.trim()) continue;
    if (rows.length === MAX_QUICK_WORDS) {
      return { rows, error: "Jednorazowo można dodać maksymalnie 100 par. Podziel listę na mniejsze części.", canSave: false };
    }
    const parts = raw.split(raw.includes("\t") ? "\t" : "=");
    const row = { line: index + 1, word: cleanWordText(parts[0] || ""), translation_pl: cleanWordText(parts[1] || ""), status: "new", message: "Nowe · bez weryfikacji słownikowej" };
    if (parts.length !== 2) {
      row.status = "error";
      row.message = "Użyj jednego znaku = albo dwóch kolumn oddzielonych tabulatorem.";
    } else if (!row.word || !row.translation_pl) {
      row.status = "error";
      row.message = "Uzupełnij słowo i tłumaczenie.";
    } else if ([row.word, row.translation_pl].some(value => [...value].length > 128)) {
      row.status = "error";
      row.message = "Słowo i tłumaczenie mogą mieć najwyżej 128 znaków każde.";
    } else {
      const key = keyFor(row.word);
      const translations = known.get(key);
      if (translations?.some(value => value !== keyFor(row.translation_pl))) {
        row.status = "error";
        row.message = "To słowo ma inne tłumaczenie. Popraw listę lub użyj Edytuj.";
      } else if (translations) {
        row.status = "duplicate";
        row.message = "Ta sama para już jest na liście — zostanie pominięta.";
      } else {
        known.set(key, [keyFor(row.translation_pl)]);
      }
    }
    rows.push(row);
  }
  return { rows, error: "", canSave: rows.length > 0 && rows.every(row => row.status !== "error") };
}
