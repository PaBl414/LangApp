export function formatError(data, fallback = "Nie udało się wykonać operacji.") {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(error => {
      const field = (error.loc || []).filter(value => value !== "body").join(".");
      return field ? `${field}: ${error.msg}` : error.msg;
    }).join("\n");
  }
  return fallback;
}
