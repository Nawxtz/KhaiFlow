"""T-009: evaluate.py exposes per-field PRF and macro/micro F1."""
import evaluate
from models import ParseResult
from parser import SmartAddressParser, build_mock_geo_db


SCORED_FIELDS = ["province", "zipcode", "district", "sub_district", "phone"]


def test_field_prf_keys_and_ranges():
    parser = SmartAddressParser(build_mock_geo_db())
    results = evaluate.run_evaluation(evaluate.DATASET, parser)

    assert "field_prf" in results
    assert "macro_f1" in results
    assert "micro_f1" in results

    prf = results["field_prf"]
    for field in SCORED_FIELDS:
        assert field in prf
        metrics = prf[field]
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "support" in metrics

        assert isinstance(metrics["support"], int)
        assert metrics["support"] == results["field_total"][field]

        p = metrics["precision"]
        r = metrics["recall"]
        f1 = metrics["f1"]
        assert 0.0 <= p <= 1.0
        assert 0.0 <= r <= 1.0
        assert 0.0 <= f1 <= 1.0

        if p + r > 0:
            assert abs(f1 - (2 * p * r / (p + r))) < 1e-4
        else:
            assert f1 == 0.0


def test_field_prf_dataset_metrics():
    parser = SmartAddressParser(build_mock_geo_db())
    results = evaluate.run_evaluation(evaluate.DATASET, parser)
    prf = results["field_prf"]

    # Province in DATASET parses 100/100 without false positives or false negatives
    assert prf["province"]["support"] == 100
    assert prf["province"]["precision"] == 1.0
    assert prf["province"]["recall"] == 1.0
    assert prf["province"]["f1"] == 1.0

    # Zipcode in DATASET has 98 expected cases correctly parsed
    assert prf["zipcode"]["support"] == 98
    assert prf["zipcode"]["recall"] == 1.0

    # A field that is right whenever it is expected has precision 1.0; values the case does not check never count
    for f in SCORED_FIELDS:
        if results["field_correct"][f] == results["field_total"][f]:
            assert prf[f]["precision"] == 1.0, f

    # Macro-F1 is the average F1 across the scored address fields
    expected_macro = sum(prf[f]["f1"] for f in SCORED_FIELDS) / len(SCORED_FIELDS)
    assert abs(results["macro_f1"] - expected_macro) < 1e-4
    assert 0.0 <= results["micro_f1"] <= 1.0


def test_field_prf_tp_fp_fn_edge_cases():
    class DummyParser:
        def __init__(self, mapping):
            self.mapping = mapping

        def parse(self, text):
            return self.mapping.get(text, ParseResult())

    mapping = {
        "c1": ParseResult(status="Success", province="เชียงใหม่", zipcode="50000"),
        "c2": ParseResult(status="Success", province="ลำพูน", zipcode=None),
        "c3": ParseResult(status="Success", province=None, zipcode="10100"),
    }
    cases = [
        # c1: province TP, zipcode TP
        evaluate.EvalCase(
            input="c1",
            category="clean",
            description="c1",
            expect_address=True,
            expected={"province": "เชียงใหม่", "zipcode": "50000"},
        ),
        # c2: province wrong (FP+FN), zipcode missing (FN)
        evaluate.EvalCase(
            input="c2",
            category="clean",
            description="c2",
            expect_address=True,
            expected={"province": "เชียงใหม่", "zipcode": "50000"},
        ),
        # c3: province missing (FN); zipcode is not in expected, so it is not scored
        # (DATASET lists only the fields a case checks, not fields that must be empty)
        evaluate.EvalCase(
            input="c3",
            category="clean",
            description="c3",
            expect_address=True,
            expected={"province": "กรุงเทพมหานคร"},
        ),
    ]

    results = evaluate.run_evaluation(cases, DummyParser(mapping))
    prf = results["field_prf"]

    # province: 1 TP, 1 FP (wrong value 'ลำพูน'), 2 FN (wrong 'ลำพูน', missing in c3) -> support=3
    assert prf["province"]["support"] == 3
    assert abs(prf["province"]["precision"] - (1.0 / 2.0)) < 1e-4
    assert abs(prf["province"]["recall"] - (1.0 / 3.0)) < 1e-4
    assert abs(prf["province"]["f1"] - 0.4) < 1e-4

    # zipcode: 1 TP, 0 FP (c3 not scored), 1 FN (missing in c2) -> support=2
    assert prf["zipcode"]["support"] == 2
    assert abs(prf["zipcode"]["precision"] - 1.0) < 1e-4
    assert abs(prf["zipcode"]["recall"] - 0.5) < 1e-4
    assert abs(prf["zipcode"]["f1"] - 2.0 / 3.0) < 1e-4

    # Micro-F1 pooled: total TP=2, total FP=1, total FN=3
    # micro precision = 2/3, micro recall = 2/5, micro F1 = 0.5
    assert abs(results["micro_f1"] - 0.5) < 1e-4


def test_existing_accuracy_metrics_preserved():
    parser = SmartAddressParser(build_mock_geo_db())
    results = evaluate.run_evaluation(evaluate.DATASET, parser)

    assert results["field_correct"]["province"] == 100
    assert results["field_total"]["province"] == 100
    assert results["field_correct"]["zipcode"] == 98
    assert results["field_total"]["zipcode"] == 98
    assert results["tp"] == 100
    assert results["tn"] == 20
    assert results["fp"] == 0
    assert results["fn"] == 0

    report = evaluate.format_report(results, len(evaluate.DATASET))
    assert "Field-Level Accuracy" in report
    assert "province" in report
    assert "zipcode" in report
