import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, Loading, scoreClass, useLoad, when } from "../components/util";

export function Documents() {
  const { data: docs, error } = useLoad(() => api.documents());
  return (
    <main className="stack-lg">
      <div className="spread">
        <h1>Your documents</h1>
        <Link className="btn" to="/check">Check a document</Link>
      </div>
      <ErrorNote error={error} />
      {!docs && !error && <Loading />}
      {docs && docs.length === 0 && (
        <div className="page stack">
          <h2>Nothing checked yet</h2>
          <p className="muted">Upload your project, thesis or report as a Word file (.docx) to see what needs fixing.</p>
          <p><Link className="btn" to="/check">Check a document</Link></p>
        </div>
      )}
      {docs && docs.length > 0 && (
        <div className="page">
          <ul className="doc-list">
            {docs.map((d) => (
              <li key={d.id}>
                <Link to={`/documents/${d.id}`}>
                  <span className={`mini-score ${scoreClass(d.latest?.score)}`}>{d.latest?.score ?? "–"}</span>
                  <span style={{ minWidth: 0 }}>
                    <h3>{d.title}</h3>
                    <span className="muted small">
                      {d.latest ? `Version ${d.latest.number}, ${when(d.latest.created_at)}` : ""}
                      {d.latest?.rulebook_name ? `, ${d.latest.rulebook_name}` : ""}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}
