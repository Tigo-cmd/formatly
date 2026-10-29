import { api } from "../api";
import { ErrorNote, Loading, plural, useLoad, when } from "../components/util";

export function Credits() {
  const { data, error } = useLoad(() => api.balance());
  return (
    <main>
      <div className="page stack" style={{ maxWidth: 640, margin: "0 auto" }}>
        <h1>Auto-fix credits</h1>
        <ErrorNote error={error} />
        {!data && !error && <Loading />}
        {data && (
          <>
            <p style={{ fontSize: "var(--step-1)" }}>You have {plural(data.credits, "credit")}.</p>
            <p className="muted">
              Checking is always free. Auto-fix uses {plural(data.fix_cost, "credit")} per document version and corrects
              the formatting for you; your words are never changed.
            </p>
            <p className="notice notice-info">Buying credits with card, bank transfer or USSD is coming soon.</p>
            {data.history.length > 0 && (
              <>
                <h2 style={{ fontSize: "var(--step-1)" }}>History</h2>
                <ul className="doc-list">
                  {data.history.map((h, i) => (
                    <li key={i}><div className="item">
                      <span className={`mini-score ${h.delta > 0 ? "mark-pass" : ""}`}>{h.delta > 0 ? `+${h.delta}` : h.delta}</span>
                      <span>{h.reason}<span className="muted small" style={{ display: "block" }}>{when(h.created_at)}</span></span>
                    </div></li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </div>
    </main>
  );
}
