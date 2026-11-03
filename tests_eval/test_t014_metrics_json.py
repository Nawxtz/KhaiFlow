"""T-014: one metrics dict and `evaluate.py --json PATH` for the manuscript tables."""
import hashlib
import json
import subprocess
import sys

import evaluate
from parser import SmartAddressParser, build_mock_geo_db

TOP = {"method", "dataset", "intent", "field_accuracy", "field_prf", "macro_f1", "micro_f1", "tags", "latency_ms",
       "noise_robustness"}


def summary():
    parser = SmartAddressParser(build_mock_geo_db())
    return evaluate.metrics_summary(evaluate.DATASET, parser)


def test_summary_shape_and_values():
    s = summary()
    assert set(s) == TOP
    assert s["method"] == "rule-based regex and fuzzy matching, offline (mock geo database)"
    d = [(c.input, c.expect_address) for c in evaluate.DATASET]
    assert s["dataset"] == {"cases": 120, "address_cases": 100, "non_address_cases": 20,
                            "sha256_16": hashlib.sha256(json.dumps(d, ensure_ascii=False).encode()).hexdigest()[:16]}
    assert s["intent"] == {"tp": 100, "tn": 20, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "accuracy": 1.0}
    assert s["field_accuracy"]["province"] == {"correct": 100, "total": 100, "accuracy": 1.0}
    assert s["field_prf"]["district"]["precision"] == 1.0
    assert s["macro_f1"] == 1.0 and s["micro_f1"] == 1.0
    assert set(s["tags"]) == {"correct", "total", "accuracy"}
    assert set(s["latency_ms"]) == {"p50", "p95", "mean", "max", "throughput_per_s"}
    assert set(s["noise_robustness"]) == {"clean_micro_f1", "per_transform", "retention"}


def test_summary_is_json_and_deterministic_except_latency():
    a, b = summary(), summary()
    json.dumps(a, ensure_ascii=False)
    a.pop("latency_ms"), b.pop("latency_ms")
    assert a == b


def test_cli_writes_json_and_keeps_text_report(tmp_path):
    out = tmp_path / "m.json"
    p = subprocess.run([sys.executable, "evaluate.py", "--json", str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-500:]
    assert set(json.loads(out.read_text(encoding="utf-8"))) == TOP
    assert "Field-Level Accuracy" in p.stdout and "F1 retention" in p.stdout
