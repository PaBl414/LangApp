// Small, dependency-free learning models shared by controllers and tests.
export const textKey = value => value.normalize("NFC").trim().replace(/\s+/gu, " ").toLowerCase();
export function wordCount(value) {
  const category = new Intl.PluralRules("pl").select(value);
  return `${value} ${category === "one" ? "słowo" : category === "few" ? "słowa" : "słów"}`;
}

export function shuffled(values, random = Math.random) {
  const result = [...values];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export function matchingRound(words, count = 4, random = Math.random) {
  const candidates = new Map(), assigned = new Map();
  for (const word of shuffled(words, random)) {
    const left = textKey(word.word), right = textKey(word.translation_pl);
    if (!left || !right) continue;
    if (!candidates.has(left)) candidates.set(left, []);
    candidates.get(left).push(word);
  }
  // Augmenting paths avoid a greedy choice leaving a one-pair round when two
  // unambiguous pairs are possible (A→X, B→X, A→Y can use B→X and A→Y).
  function assign(left, visited) {
    for (const word of candidates.get(left)) {
      const right = textKey(word.translation_pl);
      if (visited.has(right)) continue;
      visited.add(right);
      const previous = assigned.get(right);
      if (!previous || assign(textKey(previous.word), visited)) {
        assigned.set(right, word); return true;
      }
    }
    return false;
  }
  for (const left of candidates.keys()) { assign(left, new Set()); if (assigned.size >= count) break; }
  const selected = [...assigned.values()];
  return {left: shuffled(selected, random), right: shuffled(selected, random)};
}

export function continueTarget(data) {
  const languages = data.languages || [];
  const active = data.active_session;
  if (active && languages.some(language => language.id === active.language_id)) return {
    title: "Wróć do rozpoczętego quizu", label: "Kontynuuj naukę", detail: `Pytanie ${active.current_index + 1} z ${active.total}. Twoje odpowiedzi czekają.`,
    href: `/study?id=${active.language_id}&session=${active.session_id}`,
  };
  const due = data.due?.[0];
  if (due) return {title: "Czas na krótką powtórkę", label: "Rozpocznij powtórkę", detail: `${due.name_pl} · do powtórzenia: ${due.count}`,
    href: `/study?id=${due.language_id}&review=${due.direction}&quick=1`};
  const ready = languages.find(language => language.total_words >= 4);
  if (ready) return {title: "Kilka minut dla Twojego języka", label: "Rozpocznij naukę", detail: `${ready.name_pl} · krótki quiz z Twoich słów`, href: `/study?id=${ready.id}&quick=1`};
  const first = languages[0];
  if (first) return {title: "Zbuduj swój pierwszy zestaw", label: "Dodaj słowa", detail: "Dodaj cztery słowa, aby rozpocząć quiz. Fiszki są dostępne już od jednego słowa.", href: `/language?id=${first.id}`};
  return {title: "Twój pierwszy krok do nowego języka", label: "Wybierz język", detail: "Wybierz język, dodaj swoje słowa i ucz się we własnym tempie.", href: null};
}

export function vocabularyTags(words) {
  const unique = new Map();
  for (const word of words) for (const tag of word.tags || []) if (!unique.has(textKey(tag))) unique.set(textKey(tag), tag);
  return [...unique.values()].sort((a, b) => a.localeCompare(b, "pl"));
}

export function filterVocabulary(words, query, tag = "") {
  const key = textKey(query);
  const selected = tag ? words.filter(word => (word.tags || []).some(value => textKey(value) === textKey(tag))) : words;
  return !key ? selected : selected.filter(word => [word.word, word.translation_pl, word.example_sentence || "", word.example_translation || "",
    ...(word.tags || []), ...(word.translation_alternatives || []), ...(word.word_alternatives || [])].some(value => textKey(value).includes(key)));
}
