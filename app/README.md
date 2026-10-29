# Formatly web app

React single-page app (Vite, TypeScript). The same code will be wrapped as the
Android app (Capacitor) and the desktop app (Tauri) in Phase 5.

```sh
npm install
npm run dev        # http://localhost:5173, calls the API on :8000 through /api
npm run build      # type-check and build into dist/
```

Set `VITE_API_URL` at build time when the API is on another address
(e.g. `https://api.formatly.ng/api`), and add the app's address to the
server's `FORMATLY_CORS_ORIGINS`.

| Screen | Path |
| --- | --- |
| Landing, sign in, sign up | `/`, `/signin`, `/signup` |
| Documents | `/documents` |
| Check a document (file, rules, check) | `/check` |
| Report: score, checklist, notes, download, auto-fix, versions, change rules | `/documents/:id` |
| Rulebooks and the library | `/rulebooks` |
| Add your guideline (upload, photos, paste, model document) | `/rulebooks/new` |
| One rulebook: summary, or the editor for your own | `/rulebooks/:ref` |
| Credits | `/credits` |

Design: the bound project and the marker's pen. Binding blue and gold are the
brand; red, amber and green mean only "must fix", "check" and "passed". Literata
is used for headings and for quoting the writer's document; everything else
uses the system font so slow connections download one typeface.
