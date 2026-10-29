import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/util";
import { Auth } from "./pages/Auth";
import { Credits } from "./pages/Credits";
import { DocumentPage } from "./pages/DocumentPage";
import { Documents } from "./pages/Documents";
import { Landing } from "./pages/Landing";
import { NewCheck } from "./pages/NewCheck";
import { RulebookNew } from "./pages/RulebookNew";
import { RulebookPage } from "./pages/RulebookPage";
import { Rulebooks } from "./pages/Rulebooks";

function Private({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <main><Loading /></main>;
  if (!user) return <Navigate to="/signin" replace state={{ from: loc.pathname + loc.search }} />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="signin" element={<Auth mode="signin" />} />
        <Route path="signup" element={<Auth mode="signup" />} />
        <Route path="documents" element={<Private><Documents /></Private>} />
        <Route path="documents/:id" element={<Private><DocumentPage /></Private>} />
        <Route path="check" element={<Private><NewCheck /></Private>} />
        <Route path="rulebooks" element={<Private><Rulebooks /></Private>} />
        <Route path="rulebooks/new" element={<Private><RulebookNew /></Private>} />
        <Route path="rulebooks/:ref" element={<Private><RulebookPage /></Private>} />
        <Route path="credits" element={<Private><Credits /></Private>} />
        <Route path="*" element={<main><h1>Page not found</h1></main>} />
      </Route>
    </Routes>
  );
}
