// The preview's stand-in for the server: same functions as `api`, kept in memory.
// Results come from the real engine run on a sample project (see scripts/make_demo_fixtures.py).
import {
  ApiError, type Balance, type DocumentInfo, type Guideline, type Report, type RulebookFull, type RulebookSummary,
  type User, type Version,
} from "../api";
import fixtures from "./fixtures.json";

const F = fixtures as unknown as {
  reports: { before: Report; after: Report; clean: Report };
  fix_summary: Version["fix_summary"];
  builtins: RulebookSummary[];
  rulebooks: Record<string, RulebookFull>;
  guideline: { draft: Record<string, unknown>; questions: Guideline["questions"]; notes: Guideline["notes"] };
  sample: { draft: Record<string, unknown>; notes: Guideline["notes"] };
};

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const id = () => Math.random().toString(16).slice(2, 14);
const now = () => new Date().toISOString();

let user: User | null = null;
const docs: DocumentInfo[] = [];
const reports = new Map<string, Report>();
const mine: RulebookFull[] = [];
const guidelines = new Map<string, Guideline & { readyAt: number }>();
const history: Balance["history"] = [];

const LIBRARY: RulebookSummary[] = [
  { ref: "sample-lib-1", name: "Computer Engineering project 2026 (sample)", description: "", institution: "Michael Okpara University of Agriculture, Umudike",
    department: "Computer Engineering", builtin: false, verified: true, visibility: "public", mine: false, uses: 214 },
  { ref: "sample-lib-2", name: "Accounting project work (sample)", description: "", institution: "University of Nigeria, Nsukka",
    department: "Accounting", builtin: false, verified: false, visibility: "public", mine: false, uses: 57 },
];

function rulebookName(ref: string): string {
  return F.rulebooks[ref]?.name ?? mine.find((r) => r.ref === ref)?.name ?? LIBRARY.find((r) => r.ref === ref)?.name ?? "Your rules";
}

function addVersion(doc: DocumentInfo, report: Report, filename: string, source: Version["source"], ref: string): Version {
  const v: Version = {
    id: id(), number: doc.versions.length + 1, filename, source, status: "done", error: "",
    score: report.score, counts: report.counts, rulebook_ref: ref, rulebook_name: rulebookName(ref),
    fix_summary: source === "autofix" ? F.fix_summary : {}, created_at: now(),
  };
  reports.set(v.id, { ...report, rulebook: { name: v.rulebook_name, version: 2 } });
  doc.versions.push(v);
  doc.latest = v;
  doc.updated_at = v.created_at;
  return v;
}

function setPath(d: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split(".");
  let cur = d;
  for (const k of keys.slice(0, -1)) cur = (cur[k] ??= {}) as Record<string, unknown>;
  cur[keys[keys.length - 1]] = value;
}

function needUser(): User {
  if (!user) throw new ApiError(401, "Please sign in.");
  return user;
}

const signIn = async (email: string, name = "") => {
  await wait(300);
  user = user ?? { id: "demo", email, name: name || "Preview user", credits: 2, is_admin: false };
  if (!history.length) history.push({ delta: 2, reason: "Welcome credits", created_at: now() });
  return { token: "preview", user };
};

const backend = {
  register: (email: string, _password: string, name: string) => signIn(email, name),
  login: (email: string, _password: string) => signIn(email),
  me: async () => needUser(),

  rulebooks: async () => [...F.builtins, ...mine],
  library: async (q: string) => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return [...LIBRARY, ...mine.filter((r) => r.visibility === "public")]
      .filter((r) => words.every((w) => `${r.name} ${r.institution} ${r.department}`.toLowerCase().includes(w)));
  },
  rulebook: async (ref: string): Promise<RulebookFull> => {
    const found = F.rulebooks[ref] ?? mine.find((r) => r.ref === ref);
    if (found) return found;
    const lib = LIBRARY.find((r) => r.ref === ref);
    if (lib) return { ...F.rulebooks["builtin:default"], ...lib };
    throw new ApiError(404, "Rulebook not found.");
  },
  saveRulebook: async (body: { name: string; description?: string; institution?: string; department?: string;
                               visibility: string; data: Record<string, unknown> }, ref?: string) => {
    await wait(300);
    const base = F.rulebooks["builtin:default"];
    const rb: RulebookFull = {
      ...base, ref: ref ?? `mine-${id()}`, name: body.name, description: body.description ?? "",
      institution: body.institution ?? "", department: body.department ?? "", builtin: false, verified: false,
      visibility: body.visibility, mine: true, uses: 0, data: body.data,
    };
    const i = mine.findIndex((r) => r.ref === rb.ref);
    if (i >= 0) mine[i] = rb; else mine.unshift(rb);
    return rb as RulebookSummary;
  },
  deleteRulebook: async (ref: string) => { const i = mine.findIndex((r) => r.ref === ref); if (i >= 0) mine.splice(i, 1); },

  documents: async () => { needUser(); return [...docs].sort((a, b) => b.updated_at.localeCompare(a.updated_at)); },
  document: async (docId: string) => {
    const d = docs.find((x) => x.id === docId);
    if (!d) throw new ApiError(404, "Document not found.");
    return d;
  },
  upload: async (file: File, rulebookRef: string) => {
    needUser();
    await wait(1200);
    const title = file.name.replace(/\.docx$/i, "");
    const doc: DocumentInfo = { id: id(), title, rulebook_ref: rulebookRef, created_at: now(), updated_at: now(), latest: null, versions: [] };
    addVersion(doc, F.reports.before, file.name, "upload", rulebookRef);
    docs.push(doc);
    return doc;
  },
  uploadVersion: async (docId: string, file: File) => {
    await wait(1200);
    const doc = await backend.document(docId);
    addVersion(doc, F.reports.clean, file.name, "upload", doc.rulebook_ref);
    return doc;
  },
  updateDocument: async (docId: string, body: { title?: string; rulebook_ref?: string }) => {
    const doc = await backend.document(docId);
    if (body.title) doc.title = body.title;
    if (body.rulebook_ref && body.rulebook_ref !== doc.rulebook_ref) {
      await wait(900);
      doc.rulebook_ref = body.rulebook_ref;
      addVersion(doc, reports.get(doc.latest!.id) ?? F.reports.before, doc.latest!.filename, "upload", body.rulebook_ref);
    }
    return doc;
  },
  deleteDocument: async (docId: string) => { const i = docs.findIndex((d) => d.id === docId); if (i >= 0) docs.splice(i, 1); },
  report: async (versionId: string) => {
    const doc = docs.find((d) => d.versions.some((v) => v.id === versionId));
    const version = doc?.versions.find((v) => v.id === versionId);
    const report = reports.get(versionId);
    if (!version || !report) throw new ApiError(404, "Version not found.");
    return { version, report };
  },
  fix: async (versionId: string) => {
    const u = needUser();
    if (u.credits < 1) throw new ApiError(402, "You have no auto-fix credits left. Buy credits to continue.");
    await wait(1800);
    const doc = docs.find((d) => d.versions.some((v) => v.id === versionId))!;
    const from = doc.versions.find((v) => v.id === versionId)!;
    addVersion(doc, F.reports.after, from.filename.replace(/\.docx$/i, " (auto-fixed).docx"), "autofix", doc.rulebook_ref)
      .fix_summary = { ...F.fix_summary, from_version: from.number };
    user = { ...u, credits: u.credits - 1 };
    history.unshift({ delta: -1, reason: "Auto-fix", created_at: now() });
    return doc;
  },

  readGuideline: async (_files: File[], _text: string, _baseRef: string) => {
    await wait(500);
    const g = { id: id(), kind: "guideline" as const, filename: _files.map((f) => f.name).join(", ") || "pasted text",
                status: "pending" as const, error: "", draft: {}, questions: [], notes: [], readyAt: Date.now() + 4000 };
    guidelines.set(g.id, g);
    return g;
  },
  learnFromSample: async (file: File, _baseRef: string) => {
    await wait(1200);
    const g = { id: id(), kind: "sample" as const, filename: file.name, status: "done" as const, error: "",
                draft: structuredClone(F.sample.draft), questions: [], notes: F.sample.notes, readyAt: 0 };
    guidelines.set(g.id, g);
    return g;
  },
  guideline: async (gid: string): Promise<Guideline> => {
    const g = guidelines.get(gid);
    if (!g) throw new ApiError(404, "Not found.");
    if (g.status === "pending" && Date.now() >= g.readyAt) {
      Object.assign(g, { status: "done", draft: structuredClone(F.guideline.draft),
                         questions: F.guideline.questions, notes: F.guideline.notes });
    }
    return g;
  },
  answer: async (gid: string, answers: Record<string, string>) => {
    const g = guidelines.get(gid);
    if (!g) throw new ApiError(404, "Not found.");
    for (const [path, value] of Object.entries(answers)) setPath(g.draft, path, value);
    g.questions = g.questions.filter((q) => !(q.field in answers));
    return g;
  },

  balance: async (): Promise<Balance> => ({ credits: needUser().credits, fix_cost: 1, history }),
};

// Like a real server, every answer is a fresh copy: the page never shares objects with the "server".
export const demoApi = Object.fromEntries(
  Object.entries(backend).map(([name, fn]) => [
    name, async (...args: unknown[]) => structuredClone(await (fn as (...a: unknown[]) => Promise<unknown>)(...args)),
  ]),
) as typeof backend;

export async function demoDownload(): Promise<void> {
  throw new ApiError(0, "Downloads are switched off in this preview. In the running app this saves your file with Formatly's comments in it.");
}

export const isPreview = true;
