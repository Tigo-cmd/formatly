import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type RulebookFull } from "../api";
import { RulebookEditor } from "../components/RulebookEditor";
import { ErrorNote, Loading, useLoad } from "../components/util";

type R = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const inches = (twips: number) => `${+(twips / 1440).toFixed(2)} in`;
const spacing = (ls: R | null) =>
  !ls ? "Not checked" : ls.rule === "multiple" ? ({ 1: "Single", 1.5: "1.5 lines", 2: "Double" } as R)[ls.value] ?? `${ls.value} lines`
    : `${ls.rule === "exact" ? "Exactly" : "At least"} ${ls.value} pt`;
const WORDS: R = {
  lower_roman: "i, ii, iii", upper_roman: "I, II, III", decimal: "1, 2, 3", none: "no numbers",
  justify: "justified", left: "left-aligned", center: "centred", right: "right-aligned",
  apa7: "APA 7", apa6: "APA 6", harvard: "Harvard", mla: "MLA", chicago: "Chicago", ieee: "IEEE",
  alphabetical: "in alphabetical order", numeric: "numbered in order of citation",
};
const word = (v: unknown) => WORDS[String(v)] ?? String(v ?? "Not checked");
const list = (v: unknown) => (Array.isArray(v) ? v.map(word).join(" or ") : word(v));

/** The resolved rules in plain words. */
function Summary({ rules }: { rules: R }) {
  const rows: [string, string][] = [
    ["Paper", list(rules.page?.size)],
    ["Margins", rules.page?.margins
      ? `Top ${inches(rules.page.margins.top)}, bottom ${inches(rules.page.margins.bottom)}, left ${inches(rules.page.margins.left)}, right ${inches(rules.page.margins.right)}`
      : "Not checked"],
    ["Body text", [rules.body?.font, rules.body?.size && `${rules.body.size} pt`, spacing(rules.body?.line_spacing),
                   rules.body?.alignment && list(rules.body.alignment)].filter(Boolean).join(", ")],
    ["Page numbers", `${word(rules.page_numbering?.preliminaries)} before Chapter One, ${word(rules.page_numbering?.main)} from it`],
    ["References", [rules.references?.style && word(rules.references.style), rules.references?.order && word(rules.references.order),
                    rules.references?.max_age_years && `sources from the last ${rules.references.max_age_years} years`].filter(Boolean).join(", ")],
  ];
  const pre = (rules.structure?.preliminaries ?? []) as R[];
  const chapters = (rules.structure?.chapters ?? []) as R[];
  return (
    <div className="stack">
      <dl className="grid-2" style={{ margin: 0 }}>
        {rows.map(([k, v]) => (
          <div key={k}><dt className="small muted">{k}</dt><dd style={{ margin: 0 }}>{v}</dd></div>
        ))}
      </dl>
      {pre.length > 0 && (
        <div>
          <h3>Pages before Chapter One, in order</h3>
          <p>{pre.map((s) => s.title + (s.required === true ? "" : " (if needed)")).join(", ")}</p>
        </div>
      )}
      {chapters.length > 0 && (
        <div>
          <h3>Chapters</h3>
          <ul>
            {chapters.map((c) => (
              <li key={c.number}>
                Chapter {c.number}: {c.title}{c.required === false ? " (optional)" : ""}
                {c.sections?.length > 0 && <span className="muted small"> with {c.sections.map((s: R) => `${s.number} ${s.title}`).join(", ")}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function RulebookPage() {
  const { ref = "" } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { data: rb, error } = useLoad(() => api.rulebook(ref), [ref]);

  if (error) return <main><ErrorNote error={error} /></main>;
  if (!rb) return <main><Loading /></main>;
  const book = rb as RulebookFull;
  const shareLink = `${window.location.origin}/rulebooks/${encodeURIComponent(book.ref)}`;

  return (
    <main className="stack">
      <div className="page stack">
        <Link to="/rulebooks" className="small">Rulebooks</Link>
        <h1>{book.name}</h1>
        {params.get("saved") && <p className="notice notice-ok">Saved. You can check documents against it now.</p>}
        {book.description && <p className="muted">{book.description}</p>}
        <div className="row">
          <button className="btn" onClick={() => nav(`/check?rulebook=${encodeURIComponent(book.ref)}`)}>Check a document with these rules</button>
          {book.mine && book.visibility !== "private" && (
            <button className="btn btn-quiet" onClick={() => navigator.clipboard?.writeText(shareLink)}>Copy share link</button>
          )}
        </div>
      </div>
      {book.mine ? (
        <RulebookEditor initial={book.data} editRef={book.ref}
                        meta={{ name: book.name, institution: book.institution, department: book.department,
                                visibility: book.visibility, description: book.description }} />
      ) : (
        <>
          <section className="page"><Summary rules={book.rules as R} /></section>
          <section className="page stack">
            <h2 style={{ fontSize: "var(--step-1)" }}>Need something slightly different?</h2>
            <p className="muted">Start your own rulebook from this one and change only what your guideline says.</p>
            <CopyButton from={book} />
          </section>
        </>
      )}
    </main>
  );
}

function CopyButton({ from }: { from: RulebookFull }) {
  const nav = useNavigate();
  const parent = from.builtin ? from.ref.replace("builtin:", "") : from.ref;
  return (
    <button className="btn btn-quiet" onClick={async () => {
      const saved = await api.saveRulebook({ name: `My copy of ${from.name}`, visibility: "private", data: { extends: parent } });
      nav(`/rulebooks/${saved.ref}`);
    }}>Make my own from this</button>
  );
}
