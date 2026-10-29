import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth";

export function Landing() {
  const { user } = useAuth();
  if (user) return <Navigate to="/documents" replace />;
  return (
    <>
      <main>
        <section className="hero">
          <div>
            <h1>Your project, checked against your guideline before anyone else marks it.</h1>
            <p className="lede">
              Upload your Word file. Formatly checks fonts, spacing, margins, chapters, page numbers,
              captions and references, and returns it with a note at every problem.
            </p>
            <div className="row" style={{ marginTop: 28 }}>
              <Link className="btn" to="/signup">Check my project</Link>
              <Link className="btn btn-quiet" to="/signin">Sign in</Link>
            </div>
            <p className="muted small" style={{ marginTop: 12 }}>Free to check. Two auto-fixes included.</p>
          </div>

          <figure className="demo" aria-label="Example: a project page with Formatly's notes in the margin">
            <div className="sheet">
              <p className="ch">CHAPTER ONE</p>
              <p className="ch">INTRODUCTION</p>
              <p><b>1.1 BACKGROUND OF THE STUDY</b></p>
              <p>
                Small businesses in Enugu now take most payments by transfer
                <span className="flag"> (Okafor and Bello 2021)</span>, yet few track how
                <span className="flag"> this  affects</span> their monthly revenue.
              </p>
              <p><b>1.2 STATEMENT OF THE PROBLEM</b></p>
              <p className="flag">Many owners still keep records by hand, and…</p>
            </div>
            <ul className="margin-notes">
              <li>Write the citation as (Okafor &amp; Bello, 2021)</li>
              <li>Two spaces between words</li>
              <li>Line spacing is 1.15. Required: double</li>
              <li className="ok">Chapter heading matches the guideline</li>
            </ul>
          </figure>
        </section>

        <section className="how page" aria-labelledby="how">
          <h2 id="how" className="sr-only">How it works</h2>
          <div>
            <h3>Bring your rules</h3>
            <p className="muted">
              Use the Formatly Standard, find your department’s rules, or upload the guideline you were
              given: a PDF, a Word file or photos of the printed handout.
            </p>
          </div>
          <div>
            <h3>Get it marked</h3>
            <p className="muted">
              In seconds you get a score and your own file back with comments in the margin, saying
              what is wrong and how to fix it.
            </p>
          </div>
          <div>
            <h3>Fix it your way</h3>
            <p className="muted">
              Correct it yourself, or let Auto-fix correct the formatting for you. Your words are never
              changed.
            </p>
          </div>
        </section>
      </main>
      <footer className="site">Formatly checks formatting and structure. Your documents are private to you.</footer>
    </>
  );
}
