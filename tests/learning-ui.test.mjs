import test from "node:test";
import assert from "node:assert/strict";
import { continueTarget, filterVocabulary, matchingRound, shuffled, wordCount, vocabularyTags } from "../frontend/js/learning-ui.js";

const words = [{id:1,word:"hello",translation_pl:"cześć",translation_alternatives:["witaj"]},
  {id:2,word:"house",translation_pl:"dom"}, {id:3,word:"cat",translation_pl:"kot"}, {id:4,word:"dog",translation_pl:"pies"}];

test("word counts use Polish plural forms", () => {
  assert.equal(wordCount(1),"1 słowo"); assert.equal(wordCount(4),"4 słowa");
  assert.equal(wordCount(12),"12 słów"); assert.equal(wordCount(44),"44 słowa");
});

test("matching rounds have the same unique pairs on both sides without mutating vocabulary", () => {
  const before = JSON.stringify(words);
  for (let i = 0; i < 20; i++) {
    const result = matchingRound(words);
    assert.equal(result.left.length,4);
    assert.deepEqual(result.left.map(w=>w.id).sort(),result.right.map(w=>w.id).sort());
  }
  assert.equal(JSON.stringify(words),before);
  assert.deepEqual(matchingRound([]),{left:[],right:[]});
});

test("ambiguous repeated translations and normalized repeated prompts are excluded", () => {
  const result = matchingRound([...words,{id:5,word:"hi",translation_pl:"CZEŚĆ"},{id:6,word:" HELLO ",translation_pl:"powitanie"}]);
  const normalize = value=>value.toLowerCase().trim();
  assert.equal(new Set(result.left.map(w=>normalize(w.word))).size,result.left.length);
  assert.equal(new Set(result.left.map(w=>normalize(w.translation_pl))).size,result.left.length);
  assert.ok(result.left.length<=4);
});

test("matching finds two valid pairs even if the first edge would block both alternatives", () => {
  const tricky=[{id:1,word:"a",translation_pl:"x"},{id:2,word:"b",translation_pl:"x"},{id:3,word:"a",translation_pl:"y"}];
  for (const value of [0,0.2,0.5,0.9]) {
    const round=matchingRound(tricky,4,()=>value);
    assert.equal(round.left.length,2);
    assert.equal(new Set(round.left.map(w=>w.word)).size,2);
    assert.equal(new Set(round.left.map(w=>w.translation_pl)).size,2);
  }
});

test("shuffling preserves every item and supports a one-word flashcard deck", () => {
  assert.deepEqual(shuffled([words[0]]),[words[0]]);
  assert.deepEqual(shuffled(words,()=>0).map(w=>w.id).sort(),[1,2,3,4]);
});

test("continue priority is owned draft, due reviews, quiz, vocabulary, then onboarding", () => {
  const language={id:1,total_words:4,name_pl:"Angielski"};
  const due={language_id:1,direction:"lang_to_pl",count:2,name_pl:"Angielski"};
  const data={languages:[language],due:[due],active_session:{session_id:7,language_id:1,current_index:2,total:4}};
  assert.equal(continueTarget(data).href,"/study?id=1&session=7");
  assert.equal(continueTarget({...data,active_session:null}).href,"/study?id=1&review=lang_to_pl&quick=1");
  assert.equal(continueTarget({languages:[language],due:[]}).href,"/study?id=1&quick=1");
  assert.equal(continueTarget({languages:[{...language,total_words:1}]}).href,"/language?id=1");
  assert.equal(continueTarget({languages:[]}).href,null);
  assert.notEqual(continueTarget({...data,active_session:{...data.active_session,language_id:99}}).href,"/study?id=99&session=7");
});

test("vocabulary search includes aliases and NFC while preserving source order", () => {
  assert.deepEqual(filterVocabulary(words,"WITAJ").map(w=>w.id),[1]);
  assert.deepEqual(filterVocabulary(words,"dom").map(w=>w.id),[2]);
  assert.deepEqual(filterVocabulary(words,"missing"),[]);
  assert.equal(filterVocabulary(words," "),words);
  assert.equal(filterVocabulary([{word:"cafe\u0301",translation_pl:"kawiarnia"}],"café").length,1);
});

test("tag and context search intersect, normalize and keep source order", () => {
  const tagged=[{...words[0],tags:["Ważne","Do pracy"],example_sentence:"Hello, my friend.",example_translation:"Cześć, przyjacielu."},{...words[1],tags:["ważne"]},words[2]];
  assert.deepEqual(vocabularyTags(tagged),["Do pracy","Ważne"]);
  assert.deepEqual(filterVocabulary(tagged,"przyjacielu","WAŻNE").map(w=>w.id),[1]);
  assert.deepEqual(filterVocabulary(tagged,"","ważne").map(w=>w.id),[1,2]);
  assert.deepEqual(filterVocabulary(tagged,"house","Do pracy"),[]);
  assert.deepEqual(filterVocabulary(tagged,"Do pracy").map(w=>w.id),[1]);
});
