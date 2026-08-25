import "server-only";

/**
 * `process.env.X ?? fallback` only falls back when the var is entirely
 * absent -- a present-but-blank .env line (e.g. `SUPABASE_STORAGE_BUCKET=`)
 * has a value of `""`, which `??` treats as set and keeps, silently losing
 * the intended default. Mirrors pipeline/config.py's `_optional()` for the
 * same reason: this exact case (a blank SUPABASE_STORAGE_BUCKET) was found
 * and fixed on the Python side and would otherwise be reintroduced here.
 */
export function envOr(name: string, fallback: string): string {
  const value = process.env[name];
  return value && value.trim() !== "" ? value : fallback;
}

/** Same blank-handling as envOr, plus a clear error on a genuinely
 * non-numeric value instead of silently producing NaN (or, worse,
 * Number("") === 0) and letting a downstream API call fail confusingly. */
export function envIntOr(name: string, fallback: number): number {
  const raw = envOr(name, String(fallback));
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${name}=${JSON.stringify(raw)} is not a valid number.`);
  }
  return parsed;
}
