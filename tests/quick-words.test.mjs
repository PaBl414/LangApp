import test from "node:test";
import assert from "node:assert/strict";
import { previewWords } from "../frontend/js/quick-words.js";

test("spreadsheet tabs and typed pairs preserve literal commas, slashes and equals in tab fields", () => {
  const result = previewWords("\uFEFFhello\tcześć, witaj\r\n\r\nhouse = dom / domostwo\nformula\tx = y");
  assert.equal(result.canSave, true);
  assert.deepEqual(result.rows.map(({line, word, translation_pl}) => ({line, word, translation_pl})), [
    {line: 1, word: "hello", translation_pl: "cześć, witaj"},
    {line: 3, word: "house", translation_pl: "dom / domostwo"},
    {line: 4, word: "formula", translation_pl: "x = y"},
  ]);
});

test("identical normalized pairs are skipped and different translations block saving", () => {
  const same = previewWords("cafe\u0301 = kawiarnia\nCAFÉ = KAWIARNIA\nhouse = dom", [{word: "café", translation_pl: "kawiarnia"}]);
  assert.deepEqual(same.rows.map(row => row.status), ["duplicate", "duplicate", "new"]);
  assert.equal(same.canSave, true);
  const conflict = previewWords("cat = kot\nCAT = pies");
  assert.equal(conflict.canSave, false);
  assert.equal(conflict.rows[1].status, "error");
});

test("invalid separators, missing fields and oversized content never enable saving", () => {
  for (const text of ["cat", "cat=", "=kot", "cat=kot=zwierzę", "cat\tkot\textra", "x".repeat(129) + "=kot", "cat=" + "😀".repeat(129)]) {
    assert.equal(previewWords(text).canSave, false, text);
  }
  assert.equal(previewWords("😀".repeat(128) + "=kot").canSave, true);
  assert.equal(previewWords(" \n\t ").canSave, false);
});

test("100 pairs are allowed and larger or excessively long pastes are rejected", () => {
  const hundred = Array.from({length: 100}, (_, i) => `word${i}=słowo${i}`).join("\n");
  assert.equal(previewWords(hundred).canSave, true);
  const excessive = previewWords(hundred + "\nanother=inne");
  assert.equal(excessive.canSave, false);
  assert.match(excessive.error, /100/);
  assert.equal(excessive.rows.length, 100);
  assert.equal(previewWords("x".repeat(60001)).canSave, false);
});

test("legacy ambiguous word variants are conflicts even when one translation matches", () => {
  assert.equal(previewWords("CAT=kot", [{word: "cat", translation_pl: "kot"}, {word: "Cat", translation_pl: "pies"}]).canSave, false);
});
