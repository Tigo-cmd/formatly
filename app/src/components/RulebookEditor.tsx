import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Note, type Question } from "../api";
import { ErrorNote, errorText } from "./util";

type Data = Record<string, unknown>;

function getPath(d: Data, path: string): unknown {
  return path.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Data)[k] : undefined), d);
}

function setPath(d: Data, path: string, value: unknown): Data {
  const out: Data = structuredClone(d);
  const keys = path.split(".");
  let cur = out;
  for (const k of keys.slice(0, -1)) {
    if (typeof cur[k] !== "object" || cur[k] === null) cur[k] = {};
    cur = cur[k] as Data;
  }
  const last = keys[keys.length - 1];
  if (value === "" || value === undefined) delete cur[last];
  else cur[last] = value;
  return out;
}

const SPACING: [string, string][] = [["1", "Single"], ["1.15", "1.15"], ["1.5", "1.5 lines"], ["2", "Double"]];

interface FieldDef { path: string; label: string; kind: "text" | "number" | "select"; options?: [string, string][]; hint?: string }

const FIELDS: { title: string; fields: FieldDef[] }[] = [
  { title: "Page", fields: [
    { path: "page.size", label: "Paper", kind: "select", options: [["A4", "A4"], ["Letter", "US Letter"], ["Legal", "Legal"], ["A5", "A5"]] },
    { path: "page.margins.top", label: "Top margin", kind: "text", hint: "e.g. 1in or 2.54cm" },
    { path: "page.margins.bottom", label: "Bottom margin", kind: "text" },
    { path: "page.margins.left", label: "Left margin", kind: "text" },
    { path: "page.margins.right", label: "Right margin", kind: "text" },
  ] },
  { title: "Body text", fields: [
    { path: "body.font", label: "Font", kind: "text" },
    { path: "body.size", label: "Font size (pt)", kind: "number" },
    { path: "body.line_spacing", label: "Line spacing", kind: "select", options: SPACING },
    { path: "body.alignment", label: "Alignment", kind: "select",
      options: [["justify", "Justified"], ["left", "Left"], ["center", "Centred"], ["right", "Right"]] },
    { path: "body.first_line_indent", label: "First-line indent", kind: "text", hint: "0in for none" },
  ] },
  { title: "Numbering and references", fields: [
    { path: "page_numbering.preliminaries", label: "Pages before Chapter One", kind: "select",
      options: [["lower_roman", "i, ii, iii"], ["upper_roman", "I, II, III"], ["decimal", "1, 2, 3"], ["none", "No numbers"]] },
    { path: "page_numbering.main", label: "From Chapter One", kind: "select",
      options: [["decimal", "1, 2, 3"], ["lower_roman", "i, ii, iii"]] },
    { path: "references.style", label: "Referencing style", kind: "select",
      options: [["apa7", "APA 7"], ["apa6", "APA 6"], ["harvard", "Harvard"], ["mla", "MLA"], ["chicago", "Chicago"], ["ieee", "IEEE"]] },
    { path: "references.max_age_years", label: "Sources no older than (years)", kind: "number" },
    { path: "limits.abstract_max_words", label: "Abstract word limit", kind: "number" },
  ] },
];

interface Props {
  initial: Data;
  meta?: { name?: string; institution?: string; department?: string; visibility?: string; description?: string };
  editRef?: string;          // updating an existing rulebook
  guidelineId?: string;      // a draft with questions from a guideline
  questions?: Question[];
  notes?: Note[];
}

export function RulebookEditor({ initial, meta = {}, editRef, guidelineId, questions = [], notes = [] }: Props) {
  const nav = useNavigate();
  const [data, setData] = useState<Data>(initial);
  const [base, setBase] = useState<Data | null>(null);
  const [name, setName] = useState(meta.name ?? String(initial.name ?? ""));
  const [institution, setInstitution] = useState(meta.institution ?? "");
  const [department, setDepartment] = useState(meta.department ?? "");
  const [visibility, setVisibility] = useState(meta.visibility ?? "private");
  const [open, setOpen] = useState(questions);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [json, setJson] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const extendsName = String(data.extends ?? "default");
  useEffect(() => {
    api.rulebook(`builtin:${extendsName}`).then((r) => setBase(r.rules)).catch(() => setBase(null));
  }, [extendsName]);

  const shown = (path: string): string => {
    const own = getPath(data, path);
    return own === undefined || own === null ? "" : String(own);
  };
  const placeholder = (path: string): string => {
    const v = base ? getPath(base, path) : undefined;
    if (v === undefined || v === null) return "Not checked";
    if (typeof v === "object" && v && "value" in (v as Data)) return String((v as Data).value);
    if (typeof v === "number" && path.startsWith("page.margins")) return `${v / 1440}in`;
    if (typeof v === "number" && path.endsWith("indent")) return `${v / 1440}in`;
    return String(v);
  };
  const update = (path: string, raw: string, kind: FieldDef["kind"]) => {
    let value: unknown = raw;
    if (raw !== "" && (kind === "number" || path.endsWith("line_spacing"))) value = Number(raw);
    if (path.startsWith("page.margins.") && raw !== "") {
      // Margins are set together: fill the others from the base so the rulebook stays complete.
      let next = data;
      for (const side of ["top", "bottom", "left", "right"]) {
        const p = `page.margins.${side}`;
        if (getPath(next, p) === undefined) next = setPath(next, p, placeholder(p));
      }
      setData(setPath(next, path, value));
      return;
    }
    setData(setPath(data, path, value));
  };

  async function applyAnswers() {
    if (!guidelineId) return;
    // Unanswered questions take the suggested answer.
    const all = Object.fromEntries(open.map((q) => [q.field, answers[q.field] ?? q.suggested ?? q.options[0]]));
    setBusy(true);
    setError(null);
    try {
      const g = await api.answer(guidelineId, all);
      setData(g.draft);
      setOpen(g.questions);
      setAnswers({});
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }

  async function save() {
    let body = data;
    if (json !== null) {
      try { body = JSON.parse(json); } catch { setError("The advanced settings are not valid JSON."); return; }
    }
    if (!name.trim()) { setError("Give your rulebook a name."); return; }
    setBusy(true);
    setError(null);
    try {
      const saved = await api.saveRulebook(
        { name: name.trim(), institution, department, visibility, description: meta.description ?? "",
          data: { ...body, name: name.trim() } }, editRef);
      nav(`/rulebooks/${saved.ref}?saved=1`);
    } catch (e) { setError(errorText(e)); setBusy(false); }
  }

  const byType = (t: Note["type"]) => notes.filter((n) => n.type === t);

  return (
    <div className="stack">
      {open.length > 0 && (
        <section className="page stack" aria-labelledby="q">
          <h2 id="q">A few questions</h2>
          <p className="muted">Your guideline was not clear about these. Your answers become rules.</p>
          {open.map((q) => (
            <fieldset key={q.field} style={{ border: 0, padding: 0, margin: 0 }}>
              <legend style={{ fontWeight: 600, marginBottom: 8 }}>{q.question}</legend>
              {q.options.map((opt) => (
                <label className="choice" key={opt}>
                  <input type="radio" name={q.field} checked={(answers[q.field] ?? q.suggested) === opt}
                         onChange={() => setAnswers({ ...answers, [q.field]: opt })} />
                  <span>{opt}{opt === q.suggested && <span className="muted small"> (suggested)</span>}</span>
                </label>
              ))}
            </fieldset>
          ))}
          <button className="btn" disabled={busy} onClick={applyAnswers}>Use these answers</button>
        </section>
      )}

      {(byType("learned").length > 0 || byType("unsure").length > 0) && (
        <section className="page stack">
          <h2>What Formatly measured</h2>
          <ul className="small">{byType("learned").map((n, i) => <li key={i}>{n.text}</li>)}</ul>
          {byType("unsure").length > 0 && (
            <div className="notice notice-info small">
              <p><b>Not consistent in the model document, so the standard rule is kept:</b></p>
              <ul>{byType("unsure").map((n, i) => <li key={i}>{n.text}</li>)}</ul>
            </div>
          )}
        </section>
      )}

      <section className="page stack" aria-labelledby="settings">
        <h2 id="settings">The main rules</h2>
        <p className="muted small">
          Anything left empty follows the Formatly rulebook this starts from ({extendsName}); its value is shown in grey.
        </p>
        {FIELDS.map((group) => (
          <fieldset key={group.title} style={{ border: 0, padding: 0, margin: "8px 0 0" }}>
            <legend style={{ fontFamily: "var(--serif)", fontWeight: 650, fontSize: "1.1rem", marginBottom: 12 }}>{group.title}</legend>
            <div className="grid-2">
              {group.fields.map((f) => (
                <label className="field" key={f.path}>
                  <span>{f.label}</span>
                  {f.kind === "select" ? (
                    <select value={shown(f.path)} onChange={(e) => update(f.path, e.target.value, f.kind)}>
                      <option value="">Standard ({placeholder(f.path)})</option>
                      {f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  ) : (
                    <input type={f.kind === "number" ? "number" : "text"} value={shown(f.path)}
                           placeholder={placeholder(f.path)} onChange={(e) => update(f.path, e.target.value, f.kind)} />
                  )}
                  {f.hint && <small>{f.hint}</small>}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <details>
          <summary className="small" style={{ cursor: "pointer" }}>Advanced: every rule as JSON</summary>
          <textarea style={{ fontFamily: "ui-monospace, monospace", fontSize: 13, minHeight: 260, marginTop: 8 }}
                    value={json ?? JSON.stringify(data, null, 2)} onChange={(e) => setJson(e.target.value)}
                    aria-label="Rulebook as JSON" />
        </details>
      </section>

      {(byType("not_checkable").length > 0 || byType("quote").length > 0 || byType("dropped").length > 0) && (
        <section className="page stack">
          {byType("dropped").length > 0 && (
            <div className="notice notice-error small"><ul>{byType("dropped").map((n, i) => <li key={i}>{n.text}</li>)}</ul></div>
          )}
          {byType("not_checkable").length > 0 && (
            <div>
              <h3>Rules you need to follow yourself</h3>
              <p className="muted small">Your guideline also says these, which a check of the Word file cannot see.</p>
              <ul>{byType("not_checkable").map((n, i) => <li key={i}>{n.text}</li>)}</ul>
            </div>
          )}
          {byType("quote").length > 0 && (
            <details>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>Where each rule came from</summary>
              <ul className="small">
                {byType("quote").map((n, i) => <li key={i}><b>{n.rule}</b>: <q>{n.text}</q></li>)}
              </ul>
            </details>
          )}
        </section>
      )}

      <section className="page stack" aria-labelledby="save">
        <h2 id="save">Name and sharing</h2>
        <div className="grid-2">
          <label className="field"><span>Name</span>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Accounting project 2026" />
          </label>
          <label className="field"><span>Institution</span>
            <input type="text" value={institution} onChange={(e) => setInstitution(e.target.value)} />
          </label>
          <label className="field"><span>Department or course</span>
            <input type="text" value={department} onChange={(e) => setDepartment(e.target.value)} />
          </label>
          <label className="field"><span>Who can use it</span>
            <select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
              <option value="private">Only me</option>
              <option value="shared">Anyone I send the link to</option>
              <option value="public">Everyone: list it in the library</option>
            </select>
            <small>Share it so classmates can check against the same rules.</small>
          </label>
        </div>
        <ErrorNote error={error} />
        <div className="row">
          <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : editRef ? "Save changes" : "Save rulebook"}</button>
        </div>
      </section>
    </div>
  );
}
