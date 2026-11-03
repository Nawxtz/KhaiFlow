"""T-010: evaluate.py reports latency percentiles and throughput (manuscript metric: inference latency, throughput)."""
import evaluate
from parser import SmartAddressParser, build_mock_geo_db


def test_latency_summary_nearest_rank():
    s = evaluate.latency_summary([5.0, 1.0, 3.0, 2.0, 4.0, 10.0, 6.0, 7.0, 8.0, 9.0])
    assert s["p50"] == 5.0
    assert s["p95"] == 10.0
    assert s["max"] == 10.0
    assert abs(s["mean"] - 5.5) < 1e-9
    assert abs(s["throughput_per_s"] - 1000 / 5.5) < 1e-6


def test_latency_summary_single_and_empty():
    assert evaluate.latency_summary([2.0])["p95"] == 2.0
    assert evaluate.latency_summary([]) == {}


def test_report_prints_percentiles_and_old_lines():
    parser = SmartAddressParser(build_mock_geo_db())
    results = evaluate.run_evaluation(evaluate.DATASET, parser)
    report = evaluate.format_report(results, len(evaluate.DATASET))
    for text in ("p50", "p95", "Throughput", "Avg processing time", "Max processing time"):
        assert text in report
