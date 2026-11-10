import test from "node:test";
import assert from "node:assert/strict";
import { setTimeout as pause } from "node:timers/promises";
import { createWordChecker, dictionaryMessage, readDictionaryPreference, saveDictionaryPreference } from "../frontend/js/dictionary.js";

function harness(lookup, supported = true) {
  const input = new EventTarget();
  input.value = "hello";
  const feedback = {textContent: "", className: ""};
  const checker = createWordChecker({input, feedback, getLanguage: () => "en", isSupported: () => supported, delay: 5, lookup});
  return {input, feedback, checker};
}

test("missing entries, unsupported languages and outages have different neutral messages", () => {
  assert.match(dictionaryMessage({status:"not_found"}), /Możesz zapisać/);
  assert.match(dictionaryMessage({status:"unavailable"}), /chwilowo niedostępny/);
  assert.match(dictionaryMessage({status:"unsupported"}), /nie jest obsługiwane/);
  assert.equal(dictionaryMessage({status:"disabled"}), "");
  assert.match(dictionaryMessage({status:"found",source:"wiktionary"}), /Wiktionary/);
});

test("turning off clears timers and ignores responses already in flight", async () => {
  let resolveLookup, calls = 0;
  const {checker, feedback} = harness(() => {calls++; return new Promise(resolve => {resolveLookup = resolve;});});
  checker.setEnabled(true);
  await pause(20);
  checker.setEnabled(false);
  resolveLookup({status:"not_found"});
  await pause(10);
  assert.equal(calls, 1);
  assert.equal(feedback.textContent, "");
  checker.setEnabled(true);
  checker.setEnabled(false);
  await pause(20);
  assert.equal(calls, 1);
});

test("old input results cannot overwrite a newer input or a cleared form", async () => {
  const pending = [];
  const {checker, input, feedback} = harness(() => new Promise(resolve => pending.push(resolve)));
  checker.setEnabled(true);
  await pause(20);
  input.value = "house";
  input.dispatchEvent(new Event("input"));
  await pause(20);
  pending[1]({status:"found"});
  await pause(5);
  pending[0]({status:"not_found"});
  await pause(5);
  assert.match(feedback.textContent, /Znaleziono/);
  input.value = "";
  checker.invalidate();
  assert.equal(feedback.textContent, "");
});

test("unsupported languages never send a lookup and network errors stay advisory", async () => {
  let calls = 0;
  const unsupported = harness(async () => {calls++;}, false);
  unsupported.checker.setEnabled(true);
  await pause(20);
  assert.equal(calls, 0);
  assert.match(unsupported.feedback.textContent, /nie jest obsługiwane/);
  const failing = harness(async () => {throw new Error("offline");});
  failing.checker.setEnabled(true);
  await pause(20);
  assert.match(failing.feedback.textContent, /chwilowo niedostępny/);
  assert.ok(!failing.feedback.className.includes("error"));
});

test("blocked browser storage still permits disabling checks for the current page", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis,"localStorage");
  Object.defineProperty(globalThis,"localStorage",{configurable:true,get(){throw new Error("blocked");}});
  try {
    saveDictionaryPreference(false);
    assert.equal(readDictionaryPreference(),false);
    saveDictionaryPreference(true);
    assert.equal(readDictionaryPreference(),true);
  } finally {
    if(original)Object.defineProperty(globalThis,"localStorage",original);
    else delete globalThis.localStorage;
  }
});

test("the browser preference persists and clearing it restores the default", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis,"localStorage");
  const values = new Map();
  Object.defineProperty(globalThis,"localStorage",{configurable:true,value:{
    getItem:key=>values.get(key)??null, setItem:(key,value)=>values.set(key,value),
  }});
  try {
    saveDictionaryPreference(false);
    assert.equal(readDictionaryPreference(),false);
    values.clear();
    assert.equal(readDictionaryPreference(),true);
  } finally {
    if(original)Object.defineProperty(globalThis,"localStorage",original);
    else delete globalThis.localStorage;
  }
});
