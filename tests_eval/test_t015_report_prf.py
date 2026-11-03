"""T-015: the text report shows the per-field precision/recall/F1 table and macro/micro F1."""
import evaluate
from parser import SmartAddressParser, build_mock_geo_db


def report():
    parser = SmartAddressParser(build_mock_geo_db())
    r = evaluate.run_evaluation(evaluate.DATASET, parser)
    return evaluate.format_report(r, len(evaluate.DATASET))


def test_prf_section():
    text = report()
    assert "Field Precision / Recall / F1" in text
    for f in ("province", "zipcode", "district", "sub_district", "phone"):
        section = text.split("Field Precision / Recall / F1", 1)[1]
        row = [l for l in section.splitlines() if l.strip().startswith(f + " ") and l.count("%") >= 3]
        assert row, f"no PRF row for {f} (name, then precision, recall, F1 as percentages)"
    assert "Macro-F1" in text and "Micro-F1" in text


def test_existing_sections_stay():
    text = report()
    for s in ("Field-Level Accuracy", "Semantic Tag Detection", "Avg processing time", "p95 processing time"):
        assert s in text
