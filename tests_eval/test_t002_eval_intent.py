"""T-002: evaluate.py must count IntentShield rejections as non-addresses."""
import hashlib
import json

import evaluate
from parser import SmartAddressParser, build_mock_geo_db


def test_dataset_unchanged():
    d = [(c.input, c.expect_address) for c in evaluate.DATASET]
    digest = hashlib.sha256(json.dumps(d, ensure_ascii=False).encode()).hexdigest()[:16]
    assert digest == "5a1623abf82cfc64"


def test_intent_rejections_counted():
    r = evaluate.run_evaluation(evaluate.DATASET, SmartAddressParser(build_mock_geo_db()))
    assert (r["tp"], r["fn"]) == (100, 0)
    assert (r["tn"], r["fp"]) == (20, 0)
