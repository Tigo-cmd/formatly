import { useEffect, useState } from "react";
import { ApiError } from "../api";

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Something went wrong. Please try again.";
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="notice notice-error" role="alert">{error}</p>;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <p className="row muted" role="status"><span className="spinner" aria-hidden /> {label}…</p>;
}

/** Load something once (or when `deps` change), with loading and error state. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    load().then((d) => live && setData(d)).catch((e) => live && setError(errorText(e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, setData, reload: () => setTick((t) => t + 1) };
}

export function scoreClass(score: number | null | undefined): string {
  if (score == null) return "";
  return score >= 85 ? "score-good" : score >= 60 ? "score-mid" : "score-low";
}

export function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
