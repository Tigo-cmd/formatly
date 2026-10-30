import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { isPreview } from "./api";
import { App } from "./App";
import { AuthProvider } from "./auth";
import "./styles.css";

// The preview lives inside another page, so it keeps its place in memory instead of the address bar.
const Router = isPreview ? MemoryRouter : BrowserRouter;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Router>
      <AuthProvider>
        <App />
      </AuthProvider>
    </Router>
  </StrictMode>,
);
