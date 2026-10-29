import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { FilePicker } from "../components/FilePicker";
import { RulebookPicker } from "../components/RulebookPicker";
import { ErrorNote, errorText } from "../components/util";

export function NewCheck() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [files, setFiles] = useState<File[]>([]);
  const [ref, setRef] = useState(params.get("rulebook") ?? "builtin:default");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!files[0]) { setError("Choose your Word file first."); return; }
    setBusy(true);
    setError(null);
    try {
      const doc = await api.upload(files[0], ref);
      nav(`/documents/${doc.id}`);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <main>
      <div className="page stack-lg" style={{ maxWidth: 760, margin: "0 auto" }}>
        <h1>Check a document</h1>
        <ol className="steps">
          <li className="stack">
            <h2>Your document</h2>
            <FilePicker accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        files={files} onChange={setFiles}
                        title="Choose your Word file"
                        hint="A .docx file. If you have a PDF or .doc, open it in Word and save as .docx." />
          </li>
          <li className="stack">
            <h2>The rules</h2>
            <RulebookPicker value={ref} onChange={setRef} />
          </li>
          <li className="stack">
            <h2>Check</h2>
            <ErrorNote error={error} />
            <button className="btn" onClick={run} disabled={busy}>
              {busy ? <><span className="spinner" aria-hidden /> Checking…</> : "Check my document"}
            </button>
            <p className="muted small">Checking is free. Most documents take a few seconds.</p>
          </li>
        </ol>
      </div>
    </main>
  );
}
