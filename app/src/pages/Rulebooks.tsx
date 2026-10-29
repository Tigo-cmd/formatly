import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RulebookSummary } from "../api";
import { ErrorNote, Loading, useLoad } from "../components/util";

export function Rulebooks() {
  const { data: books, error } = useLoad(() => api.rulebooks());
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<RulebookSummary[] | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) { setFound(null); return; }
    const t = setTimeout(() => api.library(query).then(setFound).catch(() => setFound([])), 350);
    return () => clearTimeout(t);
  }, [query]);

  const item = (rb: RulebookSummary) => (
    <li key={rb.ref}>
      <Link to={`/rulebooks/${encodeURIComponent(rb.ref)}`}>
        <span style={{ minWidth: 0 }}>
          <h3>{rb.name}{rb.verified && !rb.builtin && <span className="badge"> Verified</span>}</h3>
          <span className="muted small">
            {rb.builtin ? "By Formatly" : [rb.institution, rb.department].filter(Boolean).join(", ") || "Your rulebook"}
            {rb.uses > 0 && `, used ${rb.uses} ${rb.uses === 1 ? "time" : "times"}`}
          </span>
        </span>
      </Link>
    </li>
  );

  return (
    <main className="stack-lg">
      <div className="spread">
        <h1>Rulebooks</h1>
        <Link className="btn" to="/rulebooks/new">Add your guideline</Link>
      </div>
      <p className="muted" style={{ maxWidth: "62ch" }}>
        A rulebook is the set of rules your document is checked against: fonts, spacing, chapters, page
        numbers, references. Use Formatly’s, find your department’s, or make one from your guideline.
      </p>
      <ErrorNote error={error} />
      {!books && !error && <Loading />}
      {books && (
        <>
          <section className="page">
            <h2 style={{ fontSize: "var(--step-1)" }}>Formatly Standard</h2>
            <ul className="doc-list">{books.filter((b) => b.builtin).map(item)}</ul>
          </section>
          <section className="page">
            <h2 style={{ fontSize: "var(--step-1)" }}>Yours</h2>
            {books.some((b) => !b.builtin)
              ? <ul className="doc-list">{books.filter((b) => !b.builtin).map(item)}</ul>
              : <p className="muted" style={{ marginTop: 8 }}>
                  None yet. <Link to="/rulebooks/new">Add your guideline</Link> to make one.
                </p>}
          </section>
        </>
      )}
      <section className="page stack">
        <h2 style={{ fontSize: "var(--step-1)" }}>Library</h2>
        <label className="field"><span>Rules other students and staff have shared</span>
          <input type="search" placeholder="University, department or course" value={query}
                 onChange={(e) => setQuery(e.target.value)} />
        </label>
        {found && (found.length ? <ul className="doc-list">{found.map(item)}</ul>
                                : <p className="muted small">Nothing shared for “{query}” yet. Be the first: add your guideline and share it.</p>)}
      </section>
    </main>
  );
}
