// Talks to the Formatly server. Types mirror server/formatly_server.

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const TOKEN_KEY = "formatly.token";

export type Severity = "error" | "warning" | "suggestion";

export interface User { id: string; email: string; name: string; credits: number; is_admin: boolean }

export interface Issue {
  rule: string;
  category: string;
  severity: Severity;
  message: string;
  hint: string;
  block: number | null;
  fixable: boolean;
  excerpt: string;
  data: Record<string, unknown>;
}

export interface Category {
  id: string; name: string; status: "pass" | "warn" | "fail";
  errors: number; warnings: number; suggestions: number;
}

export interface Report {
  rulebook: { name: string; version: number };
  score: number;
  counts: { errors: number; warnings: number; suggestions: number; fixable: number };
  categories: Category[];
  document: { paragraphs: number; words: number; chapters: { number: number; title: string }[] };
  issues: Issue[];
}

export interface Version {
  id: string; number: number; filename: string; source: "upload" | "autofix";
  status: "pending" | "done" | "failed"; error: string; score: number | null;
  counts: Partial<Report["counts"]>; rulebook_ref: string; rulebook_name: string;
  fix_summary: { fixed_count?: number; before_score?: number; from_version?: number };
  created_at: string;
}

export interface DocumentInfo {
  id: string; title: string; rulebook_ref: string; created_at: string; updated_at: string;
  latest: Version | null; versions: Version[];
}

export interface RulebookSummary {
  ref: string; name: string; description: string; institution: string; department: string;
  builtin: boolean; verified: boolean; visibility: string; mine: boolean; uses: number;
}

export interface RulebookFull extends RulebookSummary {
  data: Record<string, unknown>;   // as written (may extend another)
  rules: Record<string, unknown>;  // fully resolved
}

export interface Question { field: string; question: string; options: string[]; suggested: string | null }
export interface Note { type: "learned" | "unsure" | "not_checkable" | "quote" | "dropped"; text: string; rule?: string }

export interface Guideline {
  id: string; kind: "guideline" | "sample"; filename: string;
  status: "pending" | "done" | "failed"; error: string;
  draft: Record<string, unknown>; questions: Question[]; notes: Note[];
}

export interface Balance { credits: number; fix_cost: number; history: { delta: number; reason: string; created_at: string }[] }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const token = {
  get: (): string | null => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string | null) => {
    try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
  },
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = token.get();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, headers });
  } catch {
    throw new ApiError(0, "No connection. Check your internet and try again.");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join(" ")
      : `Something went wrong (${res.status}).`;
    throw new ApiError(res.status, msg);
  }
  return body as T;
}

const json = (data: unknown) => JSON.stringify(data);

export const api = {
  register: (email: string, password: string, name: string) =>
    request<{ token: string; user: User }>("/auth/register", { method: "POST", body: json({ email, password, name }) }),
  login: (email: string, password: string) =>
    request<{ token: string; user: User }>("/auth/login", { method: "POST", body: json({ email, password }) }),
  me: () => request<User>("/auth/me"),

  rulebooks: () => request<RulebookSummary[]>("/rulebooks"),
  library: (q: string) => request<RulebookSummary[]>(`/rulebooks/library?q=${encodeURIComponent(q)}`),
  rulebook: (ref: string) => request<RulebookFull>(`/rulebooks/${encodeURIComponent(ref)}`),
  saveRulebook: (body: { name: string; description?: string; institution?: string; department?: string;
                         visibility: string; data: Record<string, unknown> }, ref?: string) =>
    request<RulebookSummary>(ref ? `/rulebooks/${ref}` : "/rulebooks", { method: ref ? "PUT" : "POST", body: json(body) }),
  deleteRulebook: (ref: string) => request<void>(`/rulebooks/${ref}`, { method: "DELETE" }),

  documents: () => request<DocumentInfo[]>("/documents"),
  document: (id: string) => request<DocumentInfo>(`/documents/${id}`),
  upload: (file: File, rulebookRef: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("rulebook_ref", rulebookRef);
    return request<DocumentInfo>("/documents", { method: "POST", body: fd });
  },
  uploadVersion: (docId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<DocumentInfo>(`/documents/${docId}/versions`, { method: "POST", body: fd });
  },
  updateDocument: (id: string, body: { title?: string; rulebook_ref?: string }) =>
    request<DocumentInfo>(`/documents/${id}`, { method: "PATCH", body: json(body) }),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  report: (versionId: string) => request<{ version: Version; report: Report }>(`/versions/${versionId}/report`),
  fix: (versionId: string) => request<DocumentInfo>(`/versions/${versionId}/fix`, { method: "POST" }),

  readGuideline: (files: File[], text: string, baseRef: string) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("text", text);
    fd.append("base_ref", baseRef);
    return request<Guideline>("/guidelines", { method: "POST", body: fd });
  },
  learnFromSample: (file: File, baseRef: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("base_ref", baseRef);
    return request<Guideline>("/guidelines/sample", { method: "POST", body: fd });
  },
  guideline: (id: string) => request<Guideline>(`/guidelines/${id}`),
  answer: (id: string, answers: Record<string, string>) =>
    request<Guideline>(`/guidelines/${id}/answers`, { method: "POST", body: json({ answers }) }),

  balance: () => request<Balance>("/billing"),
};

/** Download a file that needs the sign-in token (a plain link cannot send it). */
export async function download(versionId: string, kind: "commented" | "original", fallbackName: string) {
  const t = token.get();
  const res = await fetch(`${BASE}/versions/${versionId}/download?kind=${kind}`, {
    headers: t ? { Authorization: `Bearer ${t}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "The file could not be downloaded.");
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
