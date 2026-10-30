import { NavLink, Outlet, Link } from "react-router-dom";
import { isPreview } from "../api";
import icon from "../assets/icon.svg";
import { useAuth } from "../auth";

export function Layout() {
  const { user, signOut } = useAuth();
  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <Link to={user ? "/documents" : "/"} className="wordmark" aria-label="Formatly home">
            <img src={icon} alt="" width={28} height={28} />
            <span>Formatly</span>
          </Link>
          {user ? (
            <nav aria-label="Main">
              <NavLink to="/documents">Documents</NavLink>
              <NavLink to="/rulebooks">Rulebooks</NavLink>
              <NavLink to="/credits" className="credits-pill" title="Auto-fix credits">
                {user.credits} {user.credits === 1 ? "credit" : "credits"}
              </NavLink>
              <button className="link-btn wide-only signout" onClick={signOut}>
                Sign out
              </button>
            </nav>
          ) : (
            <nav aria-label="Account">
              <NavLink to="/signin">Sign in</NavLink>
            </nav>
          )}
        </div>
      </header>
      {isPreview && (
        <p className="preview-note">
          Preview with sample results. Any file you choose stays in your browser and shows a sample project’s report.
        </p>
      )}
      <Outlet />
    </>
  );
}
