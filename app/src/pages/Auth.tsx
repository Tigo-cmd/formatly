import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorNote, errorText } from "../components/util";

export function Auth({ mode }: { mode: "signin" | "signup" }) {
  const { user, signIn, signUp } = useAuth();
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/documents";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") await signUp(email, password, name);
      else await signIn(email, password);
      nav(from, { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const signup = mode === "signup";
  return (
    <main>
      <form className="page stack" style={{ maxWidth: 440, margin: "24px auto" }} onSubmit={submit}>
        <h1>{signup ? "Create your account" : "Sign in"}</h1>
        {signup && <p className="muted">Checking is free. You get two auto-fixes to start.</p>}
        <ErrorNote error={error} />
        {signup && (
          <label className="field"><span>Your name</span>
            <input type="text" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        <label className="field"><span>Email</span>
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field"><span>Password</span>
          <input type="password" required minLength={signup ? 8 : undefined}
                 autoComplete={signup ? "new-password" : "current-password"}
                 value={password} onChange={(e) => setPassword(e.target.value)} />
          {signup && <small>At least 8 characters.</small>}
        </label>
        <button className="btn btn-block" disabled={busy}>
          {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
        </button>
        <p className="small muted">
          {signup ? <>Already have an account? <Link to="/signin">Sign in</Link></>
                  : <>New to Formatly? <Link to="/signup">Create an account</Link></>}
        </p>
      </form>
    </main>
  );
}
