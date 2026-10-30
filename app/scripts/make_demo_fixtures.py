"""Sample data for the website's preview build (npm run build:preview).

Every report here comes from the real engine run on a sample project, so the
preview shows exactly what Formatly says. Run from the repository root:
    python app/scripts/make_demo_fixtures.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "tests"))
sys.path.insert(0, str(ROOT / "server" / "tests"))

from formatly_engine import check, fix, load_rulebook  # noqa: E402
from formatly_engine.learn import learn_rulebook  # noqa: E402
from formatly_engine.rulebook import _load_raw  # noqa: E402
from formatly_server.ai import to_rulebook  # noqa: E402
from formatly_server.rulebooks import builtin_list  # noqa: E402
from formatly_server.routers.guidelines import usable  # noqa: E402
from samples import build_standard_project  # noqa: E402
from test_guidelines import extraction  # noqa: E402

project = build_standard_project(missing_scope=True, abstract_double=True, toc_wrong_title=True,
                                 split_reference=True, old_reference=True, blank_lines_before_chapter=True,
                                 certification_supervisor=True)
before = check(project).report
fixed = fix(project)
after = fixed.after.report
clean = check(build_standard_project()).report

builtins = builtin_list()
full = {b["ref"]: {**b, "mine": False, "uses": 0, "institution": "", "department": "", "visibility": "public",
                   "data": _load_raw(b["ref"].split(":", 1)[1]),
                   "rules": load_rulebook(b["ref"].split(":", 1)[1]).model_dump(mode="json")}
        for b in builtins}

x = extraction()
draft, dropped = usable(to_rulebook(x, _load_raw("default"), "default"), "default")
guideline = {
    "draft": draft,
    "questions": [q.model_dump() for q in x.questions],
    "notes": [{"type": "not_checkable", "text": t} for t in x.not_checkable]
    + [{"type": "quote", "rule": q.rule, "text": q.quote} for q in x.quotes] + dropped,
}
learned = learn_rulebook(build_standard_project(), "default", "Learned from a model project")
sample = {
    "draft": usable(learned.data, "default")[0],
    "notes": [{"type": "learned", "text": t} for t in learned.notes] + [{"type": "unsure", "text": t} for t in learned.unsure],
}

out = {
    "reports": {"before": before, "after": after, "clean": clean},
    "fix_summary": {"fixed_count": sum(fixed.applied.values()), "before_score": before["score"], "from_version": 1},
    "builtins": builtins,
    "rulebooks": full,
    "guideline": guideline,
    "sample": sample,
}
path = ROOT / "app" / "src" / "demo" / "fixtures.json"
path.write_text(json.dumps(out, separators=(",", ":")))
print(f"{path}: {path.stat().st_size // 1024} KB; scores {before['score']} -> {after['score']}, clean {clean['score']}")
