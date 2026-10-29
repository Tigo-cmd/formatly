"""Write sample documents to try Formatly on.

    python scripts/make_samples.py out/
    formatly check out/sample-messy.docx -o out/sample-messy-commented.docx
    formatly fix out/sample-messy.docx -o out/sample-messy-fixed.docx
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from samples import build_messy_project, build_project  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
out.mkdir(parents=True, exist_ok=True)
(out / "sample-correct.docx").write_bytes(build_project())
(out / "sample-messy.docx").write_bytes(build_messy_project())
print(f"Wrote {out / 'sample-correct.docx'} and {out / 'sample-messy.docx'}")
