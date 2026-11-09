/**
 * Fingerprint + identyfikator cookie.
 * Ciche logi przez console.debug (niewidoczne w normalnym widoku konsoli).
 */

function d(msg, data) {
  console.debug('[FP]', msg, data ?? '');
}

export async function getFingerprint() {
  const cached = sessionStorage.getItem("langapp_fp");
  if (cached) return cached;

  let fp = "unknown";
  try {
    if (window.ThumbmarkJS && typeof window.ThumbmarkJS.getFingerprint === "function") {
      const result = await window.ThumbmarkJS.getFingerprint();
      fp = result?.thumbmark
        || result?.visitorId
        || (typeof result === "string" ? result : JSON.stringify(result));
    } else {
      // fallback: gdy ThumbmarkJS nie załadował się (np. brak internetu)
      fp = "fallback-" + (crypto.randomUUID?.() || Date.now());
    }
  } catch (e) {
    d('Błąd ThumbmarkJS:', e.message);
    fp = "error-" + (crypto.randomUUID?.() || Date.now());
  }

  fp = String(fp).slice(0, 128);
  sessionStorage.setItem("langapp_fp", fp);
  return fp;
}

export function getCookieId() {
  const stored = localStorage.getItem("langapp_cid");
  if (stored) return stored;
  const id = (crypto.randomUUID && crypto.randomUUID()) ||
             (Date.now().toString(36) + Math.random().toString(36).slice(2));
  localStorage.setItem("langapp_cid", id);
  return id;
}
