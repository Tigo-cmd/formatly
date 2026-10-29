from formatly_server.ai import (AIError, Body, Captions, Chapter, GuidelineExtraction, Margins, Page,
                                PageNumbering, Question, Quote, References, Section, Subsection, apply_answers,
                                content_blocks, to_rulebook)
from formatly_engine.rulebook import _load_raw

from conftest import signup
from samples import build_project, build_standard_project

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extraction(**over) -> GuidelineExtraction:
    """What Claude might return for a typical departmental guideline."""
    base = dict(
        suggested_name="University X, Accounting, Project Work 2026", institution="University X",
        department="Accounting", document_type="project",
        page=Page(size="A4", orientation="portrait", margins=Margins(top="1in", bottom="1in", left="1.5in", right="1in")),
        body=Body(font="Times New Roman", size_pt=12, line_spacing="1.5", alignment="justify", first_line_indent=None),
        headings=[], chapter_label="words",
        preliminaries=[Section(title="Declaration", required=True, line_spacing=None, max_paragraphs=None,
                               max_words=None, must_include=[]),
                       Section(title="Certification", required=True, line_spacing=None, max_paragraphs=None,
                               max_words=None, must_include=["External Examiner"]),
                       Section(title="Abstract", required=True, line_spacing="single", max_paragraphs=1,
                               max_words=250, must_include=[])],
        chapters=[Chapter(number=1, title="Introduction", sections=[Subsection(number="1.1", title="Background of the Study")]),
                  Chapter(number=2, title="Literature Review", sections=[])],
        back_matter=[Section(title="References", required=True, line_spacing=None, max_paragraphs=None,
                             max_words=None, must_include=[])],
        page_numbering=PageNumbering(preliminaries="lower_roman", main="decimal", position="bottom_center"),
        captions=Captions(table_position="above", figure_position="below", numbering="by_chapter"),
        references=References(style="apa7", order="alphabetical", hanging_indent="0.5in", line_spacing=None,
                              max_age_years=5),
        main_text_max_words=None,
        questions=[Question(field="body.first_line_indent", question="Should paragraphs be indented?",
                            options=["0in", "0.5in"], suggested="0.5in")],
        not_checkable=["Submit three spiral-bound copies."],
        quotes=[Quote(rule="body.line_spacing", quote="Use 1.5 line spacing throughout.")],
    )
    base.update(over)
    return GuidelineExtraction(**base)


class FakeReader:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result or extraction(), error, []

    def read(self, blocks):
        self.calls.append(blocks)
        if self.error:
            raise self.error
        return self.result


def test_to_rulebook_maps_the_guideline():
    data = to_rulebook(extraction(), _load_raw("default"), "default")
    assert data["extends"] == "default" and data["page"]["size"] == "A4"
    assert data["body"]["line_spacing"] == 1.5
    pre = {s["id"]: s for s in data["structure"]["preliminaries"]}
    assert pre["certification"]["must_include"] == ["External Examiner"]
    assert pre["abstract"]["text"]["line_spacing"] == 1.0 and pre["abstract"]["max_paragraphs"] == 1
    assert data["limits"]["abstract_max_words"] == 250
    assert data["structure"]["chapters"][0]["sections"][0]["title"] == "Background of the Study"


def test_apply_answers_sets_paths_and_ignores_others():
    data = apply_answers({"body": {}}, {"body.first_line_indent": "0.5in", "body.line_spacing": "double",
                                        "extends": "/etc/passwd", "../x": "y"})
    assert data == {"body": {"first_line_indent": "0.5in", "line_spacing": 2.0}}


def test_content_blocks_by_file_type():
    pdf = content_blocks([("g.pdf", b"%PDF-1.7 rest")], "")
    assert pdf[0]["type"] == "document"
    photo = content_blocks([("p.jpg", b"\xff\xd8\xff\xe0 rest")], "and this")
    assert [b["type"] for b in photo] == ["image", "text"]
    word = content_blocks([("g.docx", build_project())], "")
    assert word[0]["type"] == "text" and "CERTIFICATION" in word[0]["text"]
    try:
        content_blocks([("x.zip", b"not a guideline")], "")
        raise AssertionError("expected an error")
    except AIError:
        pass


def test_guideline_without_ai_configured(client, auth):
    r = client.post("/api/guidelines", headers=auth, data={"text": "Use Times New Roman"})
    assert r.status_code == 503


def test_guideline_to_rulebook_flow(client, auth):
    reader = FakeReader()
    client.app.state.reader = reader
    r = client.post("/api/guidelines", headers=auth, data={"text": "Use 1.5 line spacing throughout..."})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    g = client.get(f"/api/guidelines/{r.json()['id']}", headers=auth).json()  # background task has run
    assert g["status"] == "done"
    assert g["questions"][0]["field"] == "body.first_line_indent"
    assert {"type": "not_checkable", "text": "Submit three spiral-bound copies."} in g["notes"]
    assert reader.calls[0][-1]["text"].startswith("Guideline text:")

    g = client.post(f"/api/guidelines/{g['id']}/answers", headers=auth,
                    json={"answers": {"body.first_line_indent": "0.5in"}}).json()
    assert g["questions"] == [] and g["draft"]["body"]["first_line_indent"] == "0.5in"

    saved = client.post("/api/rulebooks", headers=auth, json={
        "name": g["draft"]["name"], "institution": "University X", "data": g["draft"]})
    assert saved.status_code == 201, saved.text
    rules = client.get(f"/api/rulebooks/{saved.json()['ref']}", headers=auth).json()["rules"]
    assert rules["page"]["size"] == "A4" and rules["references"]["max_age_years"] == 5


def test_guideline_failure_is_reported(client, auth):
    client.app.state.reader = FakeReader(error=AIError("This guideline could not be read. Try a clearer photo."))
    r = client.post("/api/guidelines", headers=auth, data={"text": "blurry"})
    g = client.get(f"/api/guidelines/{r.json()['id']}", headers=auth).json()
    assert g["status"] == "failed" and "clearer photo" in g["error"]


def test_invalid_parts_of_a_draft_are_dropped_with_a_note(client, auth):
    bad = extraction(body=Body(font="Times New Roman", size_pt=12, line_spacing="whatever spacing",
                               alignment="justify", first_line_indent=None))
    client.app.state.reader = FakeReader(bad)
    r = client.post("/api/guidelines", headers=auth, data={"text": "x"})
    g = client.get(f"/api/guidelines/{r.json()['id']}", headers=auth).json()
    assert g["status"] == "done" and "body" not in g["draft"]
    assert any(n["type"] == "dropped" and "body" in n["text"] for n in g["notes"])
    assert g["draft"]["page"]["size"] == "A4"  # the rest is kept


def test_learn_from_a_model_document(client, auth):
    r = client.post("/api/guidelines/sample", headers=auth, data={"base_ref": "builtin:default"},
                    files={"file": ("model.docx", build_project(), DOCX)})
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["kind"] == "sample" and g["draft"]["page"]["size"] == "A4"
    assert any(n["type"] == "learned" and "Margins" in n["text"] for n in g["notes"])


def test_guidelines_are_private(client, auth):
    r = client.post("/api/guidelines/sample", headers=auth, files={"file": ("m.docx", build_standard_project(), DOCX)})
    eve = signup(client, email="eve@example.com")
    assert client.get(f"/api/guidelines/{r.json()['id']}", headers=eve).status_code == 404


def test_base_must_be_builtin(client, auth):
    r = client.post("/api/guidelines/sample", headers=auth, data={"base_ref": "../../etc"},
                    files={"file": ("m.docx", build_standard_project(), DOCX)})
    assert r.status_code == 422
