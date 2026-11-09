import { formatError } from "./api-errors.js";

export class APIError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}

// Retrying writes is a caller decision: quiz writes carry their own id/revision.
export async function request(url, method = "GET", body, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method, credentials: "same-origin", signal: controller.signal,
      ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    });
    let data;
    if (response.status === 204) return null;
    try { data = await response.json(); }
    catch {
      if (!response.ok) throw new APIError(`Serwer zwrócił błąd HTTP ${response.status}. Spróbuj ponownie.`, response.status);
      throw new APIError("Serwer zwrócił nieprawidłową odpowiedź. Spróbuj ponownie.");
    }
    if (!response.ok) throw new APIError(formatError(data, `Błąd HTTP ${response.status}.`), response.status);
    return data;
  } catch (error) {
    if (error instanceof APIError) throw error;
    if (controller.signal.aborted) throw new APIError("Upłynął czas oczekiwania na serwer. Ponów próbę.");
    throw new APIError("Brak odpowiedzi serwera. Sprawdź połączenie i ponów próbę.");
  } finally { clearTimeout(timeout); }
}
