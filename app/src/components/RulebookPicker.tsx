import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RulebookSummary } from "../api";

interface Props { value: string; onChange: (ref: string) => void }

/** Choose the rules to check against: Formatly's, your own, or one from the library. */
export function RulebookPicker({ value, onChange }: Props) {
  const [mine, setMine] = useState<RulebookSummary[]>([]);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<RulebookSummary[] | null>(null);

  useEffect(() => { api.rulebooks().then(setMine).catch(() => setMine([])); }, []);

  useEffect(() => {
    if (query.trim().length < 2) { setFound(null); return; }
    const t = setTimeout(() => api.library(query).then(setFound).catch(() => setFound([])), 350);
    return () => clearTimeout(t);
  }, [query]);

  const option = (rb: RulebookSummary) => (
    <label className="choice" key={rb.ref}>
      <input type="radio" name="rulebook" checked={value === rb.ref} onChange={() => onChange(rb.ref)} />
      <span>
        <strong>{rb.name}</strong>
        {rb.verified && !rb.builtin && <span className="badge"> Verified</span>}
        {(rb.institution || rb.department) && (
          <span className="muted small" style={{ display: "block" }}>
            {[rb.institution, rb.department].filter(Boolean).join(", ")}
          </span>
        )}
        {rb.description && <span className="muted small" style={{ display: "block" }}>{rb.description}</span>}
      </span>
    </label>
  );

  return (
    <div className="stack">
      <div>{mine.map(option)}</div>
      <label className="field">
        <span>Find your department’s rules</span>
        <input type="search" placeholder="University, department or course" value={query}
               onChange={(e) => setQuery(e.target.value)} />
      </label>
      {found && (found.length ? <div>{found.map(option)}</div>
        : <p className="muted small">Nobody has shared rules matching “{query}” yet.</p>)}
      <p className="small">
        Your guideline is different? <Link to="/rulebooks/new">Add your guideline</Link> and Formatly will
        turn it into rules.
      </p>
    </div>
  );
}
