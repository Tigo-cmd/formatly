"""Write sample documents to try Formatly on.

    python scripts/make_samples.py out/
    formatly check out/standard-with-mistakes.docx -o out/commented.docx
    formatly fix out/standard-with-mistakes.docx -o out/fixed.docx
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from samples import build_messy_project, build_project, build_standard_project  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
out.mkdir(parents=True, exist_ok=True)
files = {
    "standard-correct.docx": build_standard_project(),
    "standard-with-mistakes.docx": build_standard_project(
        certification_supervisor=True, missing_scope=True, old_reference=True, abstract_double=True,
        toc_wrong_title=True, no_list_of_tables=True, blank_lines_before_chapter=True,
        split_reference=True),
    "generic-correct.docx": build_project(),   # check with: -r generic
    "generic-messy.docx": build_messy_project(),
}
for name, data in files.items():
    (out / name).write_bytes(data)
    print(out / name)
