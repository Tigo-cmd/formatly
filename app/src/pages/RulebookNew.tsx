import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Guideline } from "../api";
import { FilePicker } from "../components/FilePicker";
import { RulebookEditor } from "../components/RulebookEditor";
import { ErrorNote, errorText } from "../components/util";

type Source = "guideline" | "text" | "sample";

const BASES: [string, string][] = [
  ["builtin:default", "Formatly Standard: project"],
  ["builtin:seminar", "Formatly Standard: seminar"],
  ["builtin:postgraduate", "Formatly Standard: postgraduate"],
  ["builtin:generic", "Common layout (A4, 1.5 in left margin)"],
];

export function RulebookNew() {
  const [source, setSource] = useState<Source>("guideline");
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [base, setBase] = useState("builtin:default");
  const [guideline, setGuideline] = useState<Guideline | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  // While the guideline is being read, ask the server every two seconds.
  useEffect(() => {
    if (guideline?.status !== "pending") return;
    const started = Date.now();
    timer.current = window.setInterval(async () => {
      try {
        const g = await api.guideline(guideline.id);
        if (g.status !== "pending" || Date.now() - started > 240_000) {
          window.clearInterval(timer.current);
          if (g.status === "pending") setError("Reading is taking longer than expected. Refresh this page in a minute.");
          setGuideline(g);
        }
      } catch { /* keep trying on a flaky connection */ }
    }, 2000);
    return () => window.clearInterval(timer.current);
  }, [guideline?.id, guideline?.status]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      if (source === "sample") {
        if (!files[0]) throw new Error("Choose the model document first.");
        setGuideline(await api.learnFromSample(files[0], base));
      } else {
        if (source === "guideline" && !files.length) throw new Error("Choose the guideline file or photos first.");
        if (source === "text" && !text.trim()) throw new Error("Paste the guideline text first.");
        setGuideline(await api.readGuideline(source === "guideline" ? files : [], source === "text" ? text : "", base));
      }
    } catch (e) {
      setError(e instanceof Error && !("status" in e) ? e.message : errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (guideline?.status === "done") {
    return (
      <main className="stack">
        <div className="page stack">
          <h1>Check your new rulebook</h1>
          <p className="muted">
            {guideline.kind === "sample"
              ? "Formatly measured your model document. Review the rules below, then save."
              : "Formatly read your guideline. Answer any questions, review the rules, then save."}
          </p>
        </div>
        <RulebookEditor initial={guideline.draft} guidelineId={guideline.id}
                        questions={guideline.questions} notes={guideline.notes} />
      </main>
    );
  }

  const tab = (id: Source, label: string) => (
    <button role="tab" aria-selected={source === id} onClick={() => { setSource(id); setFiles([]); setError(null); }}>{label}</button>
  );

  return (
    <main>
      <div className="page stack-lg" style={{ maxWidth: 760, margin: "0 auto" }}>
        <div className="stack">
          <Link to="/rulebooks" className="small">Rulebooks</Link>
          <h1>Add your guideline</h1>
          <p className="muted">Give Formatly the rules you were given, and it turns them into a rulebook you can check against.</p>
        </div>

        {guideline?.status === "pending" ? (
          <div className="stack" role="status">
            <p className="row"><span className="spinner" aria-hidden /> Reading your guideline. This usually takes under a minute.</p>
            <p className="muted small">You can stay on this page; it updates by itself.</p>
          </div>
        ) : (
          <>
            {guideline?.status === "failed" && <ErrorNote error={guideline.error} />}
            <div className="tabs" role="tablist">
              {tab("guideline", "Upload the guideline")}
              {tab("text", "Paste the text")}
              {tab("sample", "Use a model document")}
            </div>
            {source === "guideline" && (
              <FilePicker accept=".pdf,.docx,image/*" multiple files={files} onChange={setFiles}
                          title="Choose the guideline"
                          hint="A PDF or Word file, or photos of each page of the printed handout." />
            )}
            {source === "text" && (
              <label className="field"><span>Guideline text</span>
                <textarea value={text} onChange={(e) => setText(e.target.value)}
                          placeholder="Paste the formatting part of your guideline here." />
              </label>
            )}
            {source === "sample" && (
              <div className="stack">
                <FilePicker accept=".docx" files={files} onChange={setFiles}
                            title="Choose a correctly formatted document"
                            hint="A project your department accepted, as a Word file. Formatly measures its formatting." />
              </div>
            )}
            <label className="field"><span>Start from</span>
              <select value={base} onChange={(e) => setBase(e.target.value)}>
                {BASES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <small>Anything your guideline does not mention follows this.</small>
            </label>
            <ErrorNote error={error} />
            <button className="btn" onClick={start} disabled={busy}>
              {busy ? "Starting…" : source === "sample" ? "Measure this document" : "Read my guideline"}
            </button>
          </>
        )}
      </div>
    </main>
  );
}
