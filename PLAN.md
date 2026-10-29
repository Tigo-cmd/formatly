# Formatly: product plan

> Format, cite and correct your work against any guideline.

This is the agreed plan. It records what we are building and why, so later
decisions can be checked against it.

## 1. The problem

Anyone who writes a formal document has to follow a set of rules: font, size,
line spacing, margins, page numbering, the order of preliminary pages and
chapters, citation style (APA and others), table and figure captions, word
limits. Whoever sets those rules (a lecturer, a supervisor, a department, a
journal, an employer, a funding body) then spends hours correcting the same
formatting mistakes again and again, and the writer reprints and resubmits
each time.

## 2. What Formatly does

Anyone creates an account and gives Formatly two things:

1. **The rules.** The guideline document they were given, in any form.
2. **Their work.** The document to be checked (`.docx`).

Formatly reads the rules, checks the work against them, and returns:

- the **same Word file with comments** in the margin at every problem, each
  comment saying which rule it breaks and how to fix it;
- a **report** with a score and a checklist;
- optionally (paid) an **auto-fixed** copy of the document.

The user fixes their work or uses auto-fix, re-checks as often as they want,
and keeps every version.

Formatly is not limited to schools or to any single role. Students, researchers,
professionals and organisations all use it the same way. People who set rules
(lecturers, supervisors, editors, departments, companies) can optionally publish
their rulebook so everyone they work with is checked against it.

## 3. Where the rules come from

In priority order (higher overrides lower):

1. **The user's guideline**, uploaded as PDF or Word, a **photo of a printed
   handout**, or pasted text. AI turns it into a structured rulebook and asks the
   user about anything vague (e.g. "'standard margins': is that 1 inch?").
2. **A shared rulebook** someone else already created for the same institution
   or publication (see section 6).
3. **A citation style preset** (APA 7, MLA, Harvard, Chicago, IEEE).
4. **The Formatly default rulebook**, written by the Formatly team. Anything not
   covered above falls back to it. It is edited from an admin panel without
   code changes.

The user always sees the final rulebook and can edit it before checking.

## 4. Checks

Three kinds of check, each done with the right tool:

| Kind | How | Shown as |
| --- | --- | --- |
| Exact formatting (fonts, sizes, spacing, margins, page numbers) | Read directly from the document. No AI. Exact and free. | Errors |
| Structure (sections present and in order) | Rules, plus AI to recognise headings named differently | Errors |
| Citations, writing, content | AI plus rules | Suggestions with confidence |

The full catalogue (✅ = auto-fixable):

- **Page setup:** paper size, orientation, margins, binding margin. ✅
- **Body text:** font, size, line spacing, paragraph spacing, alignment,
  first-line indent, mixed fonts, highlighted or coloured text, double spaces. ✅
- **Headings:** chapter heading format (e.g. "CHAPTER ONE", centred, bold,
  capitals), heading levels, numbering (1.1, 1.1.1), each chapter on a new
  page. ✅
- **Structure:** preliminary pages present and in order, chapters in order,
  references, appendices. ✅ reorder; missing sections are added as headings
  for the user to fill in.
- **Page numbering:** roman numerals for preliminary pages, arabic from the
  first chapter, position. ✅
- **Table of contents and lists of tables and figures:** present and up to
  date. ✅ regenerate.
- **Tables and figures:** numbering, caption position (tables above, figures
  below), each one referred to in the text. ✅ numbering and captions.
- **References:** every in-text citation is in the reference list and vice
  versa, alphabetical order, hanging indent, author and year format, "et al.",
  italics, DOI format. ✅ format and order. Missing references are flagged only;
  Formatly never invents a source.
- **Writing:** spelling, grammar, punctuation, consistent spelling variant,
  abstract and overall word limits, repeated words, first-person use if
  forbidden. ✅ shown as changes the user accepts or rejects one by one.
- **Content (suggestions only):** abstract contains aim, method, findings and
  conclusion; objectives are answered in the conclusion; research questions
  match the analysis. Never auto-fixed.

### Principles

- **Auto-fix never rewrites the user's ideas.** Formatting, layout and
  references are fixed directly. Spelling and grammar are proposed as tracked
  changes for the user to accept. Content is only ever commented on. This keeps
  the work the user's own and keeps Formatly acceptable to institutions.
- **The original is never modified.** Every check and fix produces a new
  version.
- **Every comment cites its rule** and can be explained ("Why?").
- **Users can dispute a comment.** Disputes feed back into accuracy work.
- **Privacy.** Documents are not used to train AI models, are deleted on
  request, and are retained only as long as the user wants.

## 5. Accounts and roles

- **User** (everyone): signs up with email, Google, or phone number + SMS code.
  Uploads guidelines and work, checks, fixes, keeps versions.
- **Rule owner** (optional): anyone who sets rules for others, such as a lecturer,
  supervisor, department, editor or company. Publishes a rulebook with a share
  link or code, can mark it verified, and can optionally receive submissions
  and see the status of everyone using it.
- **Team** (optional): several people working on one document, e.g. a group
  project.
- **Admin** (Formatly team): maintains the default rulebook, presets, verified
  library, pricing.

## 6. Shared rulebook library

When a user uploads a guideline, they can save it as a shared rulebook (e.g.
"University X, Department of Accounting, Project Work 2026"). Others search
and reuse it instead of uploading again. Rule owners can mark a rulebook as
verified. Over time this becomes a library of guidelines across institutions
and publications. That is Formatly's main growth loop and hardest-to-copy
asset.

## 7. More features (later phases)

- Chat with your document ("what is still failing?", "is my reference list
  right?").
- Generate the table of contents and lists of tables and figures.
- Reference helper: paste a link, DOI or title and get a correctly formatted
  reference.
- Before/after comparison between versions.
- Deadlines and reminders.
- Dashboard for rule owners: everyone using their rulebook and their status.
- Similarity (plagiarism) check through a partner service.
- Word add-in: see problems live while typing.

## 8. Market and payments

- **Launch market: Nigeria.** Prices in naira.
- **Payments:** Paystack (cards, bank transfer, USSD), Flutterwave as backup.
  Stripe later for other countries.
- **Pricing model:**
  - Free: limited checks per month, basic report.
  - Pay per document: full check plus auto-fix.
  - Credits / monthly plan: for heavy users.
  - Organisation plan: an institution or company pays so its people use it
    free.
- Exact prices are set later with real usage data.
- Low data use and reliable uploads on weak networks are requirements, not
  extras.

## 9. Platforms and architecture

One codebase for the user interface, one server.

- **Web app** (React / Next.js): first.
- **Android app:** the web app wrapped with Capacitor (file picker, camera for
  guideline photos, notifications, resumable uploads).
- **Desktop app** (Windows, macOS, Linux): the web app wrapped with Tauri.
- **Server** (Python / FastAPI): API, job queue for processing, PostgreSQL,
  object storage for documents.
- **Engine** (Python, `engine/`): reads `.docx`, resolves effective formatting,
  runs checks, writes comments, applies fixes. Independent of the server so it
  is tested on its own.
- **AI** (Claude API): guideline-to-rulebook extraction, heading recognition,
  citation and writing checks, explanations. Only the parts of a document a check
  needs are sent, not the whole file.
- **LibreOffice** (headless, server side): page layout for page-based checks
  and PDF previews.

```
formatly/
  engine/      the checking and fixing engine (Python)   <- Phase 1
  server/      API, jobs, accounts, payments (Python)
  app/         web app, wrapped for Android and desktop
  docs/        rulebook format and other docs
```

## 10. Build phases

1. **Engine.** `.docx` in, commented `.docx` and report out. Exact formatting,
   structure, page numbering, captions, basic reference checks. Basic
   auto-fix of formatting. Command-line tool. Temporary default rulebook.
2. **Web app and server.** Accounts, upload, rulebook editor, report page,
   version history. AI guideline-to-rulebook extraction.
3. **AI checks, full auto-fix, payments.** Citations, writing, content
   suggestions; tracked-change fixes; Paystack.
4. **Shared rulebook library and rule-owner features.**
5. **Android app, then desktop app.**

## 11. Known hard parts

1. Word's formatting inheritance (document defaults, theme fonts, style
   chains, character styles, direct formatting) must be resolved correctly, or
   Formatly reports false errors.
2. Page-based rules (what is on which page) need layout. LibreOffice does that
   on the server.
3. Citation styles have many edge cases. AI handles these with confidence
   levels.
4. Auto-fix must never corrupt a file. The engine re-checks its own output.
5. PDF input loses formatting information, so work is submitted as `.docx`
   (Google Docs exports it). Guidelines can be any format.

## 12. Open items

- Default rulebook: to be provided by the Formatly team; a temporary one is in
  `engine/formatly_engine/rulebooks/default.yaml` until then.
- Check that the name, domain and Play Store listing for "Formatly" are
  available.
- Real guideline documents and sample works (anonymised) for testing.
