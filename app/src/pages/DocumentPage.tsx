import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, download, type DocumentInfo, type Issue, type Report, type Version } from "../api";
import { useAuth } from "../auth";
import { RulebookPicker } from "../components/RulebookPicker";
import { ErrorNote, Loading, errorText, plural, scoreClass, useLoad, when } from "../components/util";

const LABEL: Record<Issue["severity"], string> = { error: "Must fix", warning: "Check", suggestion: "Suggestion" };
const PAGE_SIZE = 40;

export function DocumentPage() {
  const { id = "" } = useParams();
  const { data: doc, error, setData: setDoc } = useLoad(() => api.document(id), [id]);
  const [versionId, setVersionId] = useState<string | null>(null);

  useEffect(() => { if (doc && !versionId) setVersionId(doc.latest?.id ?? null); }, [doc, versionId]);

  if (error) return <main><ErrorNote error={error} /></main>;
  if (!doc) return <main><Loading /></main>;
  const version = doc.versions.find((v) => v.id === versionId) ?? doc.latest;
  return (
    <main className="stack">
      <div>
        <Link to="/documents" className="small">Your documents</Link>
        <h1 style={{ marginTop: 4 }}>{doc.title}</h1>
      </div>
      {doc.versions.length > 1 && (
        <div className="version-strip" role="group" aria-label="Versions">
          {doc.versions.map((v) => (
            <button key={v.id} aria-pressed={v.id === version?.id} onClick={() => setVersionId(v.id)}>
              Version {v.number}{v.source === "autofix" ? " (auto-fixed)" : ""}: {v.score ?? "–"}
            </button>
          ))}
        </div>
      )}
      {version && <VersionReport doc={doc} version={version}
                                 onDoc={(d) => { setDoc(d); setVersionId(d.latest?.id ?? null); }} />}
    </main>
  );
}

function VersionReport({ doc, version, onDoc }: { doc: DocumentInfo; version: Version; onDoc: (d: DocumentInfo) => void }) {
  const { user, refresh } = useAuth();
  const { data, error } = useLoad(() => api.report(version.id), [version.id]);
  const [busy, setBusy] = useState<"fix" | "upload" | "download" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const report: Report | null = data?.report ?? null;
  const issues = useMemo(() => {
    const all = report?.issues ?? [];
    return category ? all.filter((i) => i.category === category) : all;
  }, [report, category]);

  if (version.status === "failed") return <p className="notice notice-error">{version.error}</p>;
  if (error) return <ErrorNote error={error} />;
  if (!report) return <Loading label="Opening the report" />;

  const c = report.counts;
  const isLatest = doc.latest?.id === version.id;

  async function act(kind: "fix" | "upload" | "download", fn: () => Promise<void>) {
    setBusy(kind);
    setActionError(null);
    try { await fn(); } catch (e) { setActionError(errorText(e)); } finally { setBusy(null); }
  }

  const fix = () => act("fix", async () => { onDoc(await api.fix(version.id)); await refresh(); });
  const uploadNew = (file: File) => act("upload", async () => { onDoc(await api.uploadVersion(doc.id, file)); });
  const save = (kind: "commented" | "original") =>
    act("download", () => download(version.id, kind, version.filename));

  return (
    <div className="stack">
      <section className="page">
        <div className="row" style={{ gap: 24, alignItems: "flex-start" }}>
          <div className={`score ${scoreClass(report.score)}`} aria-label={`Score ${report.score} out of 100`}>
            <b>{report.score}</b><span>out of 100</span>
          </div>
          <div className="stack" style={{ flex: "1 1 260px" }}>
            <p style={{ fontSize: "var(--step-1)" }}>
              {c.errors === 0 && c.warnings === 0
                ? "Nothing to fix. This version follows the rules."
                : <>
                    <span className="mark mark-error" style={{ fontSize: "inherit" }}>{plural(c.errors, "problem")} to fix</span>
                    {c.warnings > 0 && <>, <span className="mark mark-warning" style={{ fontSize: "inherit" }}>{c.warnings} to check</span></>}
                    {c.suggestions > 0 && <span className="muted">, {plural(c.suggestions, "suggestion")}</span>}
                  </>}
            </p>
            <p className="muted small">
              Checked against {version.rulebook_name}, {when(version.created_at)}.{" "}
              {version.source === "autofix" && version.fix_summary.fixed_count != null &&
                `Auto-fix corrected ${plural(version.fix_summary.fixed_count, "problem")} in version ${version.fix_summary.from_version}. What is left needs you.`}
            </p>
            <ErrorNote error={actionError} />
            <div className="row">
              <button className="btn" onClick={() => save("commented")} disabled={busy !== null}>
                {busy === "download" ? "Preparing…" : "Download with comments"}
              </button>
              {version.source === "autofix" && (
                <button className="btn btn-quiet" onClick={() => save("original")} disabled={busy !== null}>
                  Download the fixed file
                </button>
              )}
              {isLatest && c.fixable > 0 && (
                <button className="btn btn-quiet" onClick={fix} disabled={busy !== null || (user?.credits ?? 0) < 1}
                        title={(user?.credits ?? 0) < 1 ? "You have no auto-fix credits left" : undefined}>
                  {busy === "fix" ? "Fixing…" : `Auto-fix ${plural(c.fixable, "problem")} (1 credit)`}
                </button>
              )}
              {isLatest && (
                <label className="btn btn-quiet" style={{ position: "relative" }}>
                  {busy === "upload" ? "Checking…" : "Upload corrected version"}
                  <input type="file" accept=".docx" className="sr-only" disabled={busy !== null}
                         onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadNew(f); e.target.value = ""; }} />
                </label>
              )}
            </div>
            {isLatest && c.fixable > 0 && (user?.credits ?? 0) < 1 && (
              <p className="small">You have no auto-fix credits left. <Link to="/credits">Get credits</Link> or fix it yourself with the comments.</p>
            )}
          </div>
        </div>
      </section>

      <div className="grid-report">
        <section className="page" aria-labelledby="cats">
          <h2 id="cats" style={{ fontSize: "var(--step-1)" }}>What was checked</h2>
          <ul className="checklist" style={{ marginTop: 8 }}>
            <li>
              <button aria-pressed={category === null} onClick={() => { setCategory(null); setShowAll(false); }}>
                <span className="name">Everything</span><span className="muted small status">{report.issues.length}</span>
              </button>
            </li>
            {report.categories.map((cat) => (
              <li key={cat.id}>
                <button aria-pressed={category === cat.id} onClick={() => { setCategory(cat.id); setShowAll(false); }}>
                  <span className="name">
                    <span className={`tick mark-${cat.status === "pass" ? "pass" : cat.status === "fail" ? "error" : "warning"}`} aria-hidden>
                      {cat.status === "pass" ? "✓" : cat.status === "fail" ? "✗" : "!"}
                    </span>
                    {cat.name}
                  </span>
                  <span className="muted small status">
                    {cat.status === "pass" ? "Passed" : [cat.errors && `${cat.errors} to fix`, cat.warnings && `${cat.warnings} to check`].filter(Boolean).join(", ")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="page" aria-labelledby="notes">
          <div className="spread">
            <h2 id="notes" style={{ fontSize: "var(--step-1)" }}>
              {category ? report.categories.find((x) => x.id === category)?.name : "All notes"}
            </h2>
            {issues.length > 0 && <span className="muted small">{plural(issues.length, "note")}</span>}
          </div>
          {issues.length === 0 && <p className="muted" style={{ marginTop: 12 }}>No notes here.</p>}
          <div style={{ marginTop: 8 }}>
            {(showAll ? issues : issues.slice(0, PAGE_SIZE)).map((issue, k) => <IssueRow key={k} issue={issue} />)}
          </div>
          {!showAll && issues.length > PAGE_SIZE && (
            <button className="btn btn-quiet" style={{ marginTop: 12 }} onClick={() => setShowAll(true)}>
              Show all {issues.length} notes
            </button>
          )}
        </section>
      </div>

      {isLatest && <ChangeRules doc={doc} onDoc={onDoc} />}
    </div>
  );
}

function ChangeRules({ doc, onDoc }: { doc: DocumentInfo; onDoc: (d: DocumentInfo) => void }) {
  const [ref, setRef] = useState(doc.rulebook_ref);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function apply() {
    setBusy(true);
    setError(null);
    try { onDoc(await api.updateDocument(doc.id, { rulebook_ref: ref })); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  return (
    <details className="page">
      <summary style={{ cursor: "pointer", fontWeight: 600 }}>Checked against the wrong rules?</summary>
      <div className="stack" style={{ marginTop: 16 }}>
        <RulebookPicker value={ref} onChange={setRef} />
        <ErrorNote error={error} />
        <button className="btn" disabled={busy || ref === doc.rulebook_ref} onClick={apply}>
          {busy ? "Checking…" : "Check again with these rules"}
        </button>
      </div>
    </details>
  );
}

function IssueRow({ issue }: { issue: Issue }) {
  return (
    <article className={`issue issue-${issue.severity}`}>
      <blockquote className={`slip${issue.excerpt ? "" : " empty"}`} style={{ margin: 0 }}>
        {issue.excerpt || (issue.block == null ? "Whole document" : "A table or picture")}
      </blockquote>
      <div className="note">
        <p><span className={`mark mark-${issue.severity}`}>{LABEL[issue.severity]}</span>{" "}{issue.message}</p>
        {issue.hint && <p className="hint small">{issue.hint}</p>}
        {issue.fixable && <p className="can-fix">Auto-fix can do this</p>}
      </div>
    </article>
  );
}
