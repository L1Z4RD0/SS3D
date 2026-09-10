// Shared numeric-input guards. HTML `min`/`max` attributes only help when a
// field sits inside a real <form> that gets submitted — plain "Agregar" row
// buttons and live-preview panels bypass native constraint validation
// entirely, so every place that consumes a user-typed number must also run
// these checks explicitly before using the value.

export const GRAMS_MAX = 5000; // generous ceiling above any standard spool, to catch typos like "500000"

/**
 * True only for a finite, real number within [min, max] (inclusive on both
 * ends unless allowZero is false, which excludes exactly `min`).
 */
export function isValidNumber(value, { min = 0, max = Infinity, allowZero = true } = {}) {
  if (value === null || value === undefined || value === "") return false;
  const n = Number(value);
  if (!Number.isFinite(n)) return false; // rejects letters/symbols coerced to NaN, and Infinity
  if (allowZero ? n < min : n <= min) return false;
  if (n > max) return false;
  return true;
}

export function isValidGrams(value) {
  return isValidNumber(value, { min: 0, max: GRAMS_MAX, allowZero: false });
}

export function gramsErrorMessage(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) {
    return "Ingresa un número válido de gramos.";
  }
  if (Number(value) <= 0) return "Los gramos deben ser mayores a 0.";
  if (Number(value) > GRAMS_MAX) return `Los gramos no pueden superar ${GRAMS_MAX}g.`;
  return "Valor de gramos inválido.";
}

/**
 * FastAPI returns `detail` as a plain string for our own HTTPException calls,
 * but as an array of {msg, loc, ...} objects for Pydantic 422 validation
 * errors. Rendering that array directly in the UI shows "[object Object]" —
 * this always resolves to a readable string instead.
 */
export function extractApiError(err, fallback = "Ocurrió un error inesperado.") {
  const detail = err?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => e.msg || JSON.stringify(e)).join(" · ") || fallback;
  }
  return fallback;
}
