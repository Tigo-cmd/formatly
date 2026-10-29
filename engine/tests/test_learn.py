from formatly_engine import check, rulebook_from_dict
from formatly_engine.learn import learn_rulebook
from samples import build_project, build_standard_project


def test_learning_from_a_correct_document_reproduces_its_rules():
    data = build_standard_project()
    learned = learn_rulebook(data, "default")
    rb = rulebook_from_dict(learned.data)
    assert rb.page.size == "Letter"
    assert rb.body.font == "Times New Roman" and rb.body.line_spacing.value == 2.0
    assert check(data, rb).issues == []
    assert any("Preliminary pages, in order" in n for n in learned.notes)


def test_learning_picks_up_a_different_layout():
    learned = learn_rulebook(build_project(), "default")
    rb = rulebook_from_dict(learned.data)
    assert rb.page.size == "A4"
    assert rb.page.margins.left == 2160  # 1.5 in
    assert rb.body.first_line_indent == 720


def test_learning_does_not_copy_a_missing_hanging_indent():
    learned = learn_rulebook(build_project(no_hanging_indent=True), "default")
    assert "hanging_indent" not in learned.data.get("references", {})
    assert any("hanging indent" in u for u in learned.unsure)


def test_inconsistent_documents_keep_the_base_rule():
    import io

    import docx

    d = docx.Document(io.BytesIO(build_standard_project()))
    body = [p for p in d.paragraphs if p.text.startswith(("This report", "Prior systems"))]
    for p in body[::2]:  # half the paragraphs: no clear rule
        p.paragraph_format.line_spacing = 1.5
    buf = io.BytesIO()
    d.save(buf)
    learned = learn_rulebook(buf.getvalue(), "default")
    assert "line_spacing" not in learned.data["body"]
    assert any("line spacing varies" in u for u in learned.unsure)
