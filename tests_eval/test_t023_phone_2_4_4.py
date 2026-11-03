"""T-023: mobile numbers written 2-4-4 ("08 1234 5678") are read as phones."""
import subprocess

import evaluate
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
ADDR = "คุณปลา 3/3 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 "


def test_two_four_four_mobile():
    for phone in ("08 1234 5678", "08-1234-5678", "08.1234.5678", "โทร. 08 1234 5678", "09 8765 4321"):
        r = P.parse(ADDR + phone)
        assert r.phone == ("0987654321" if "8765" in phone else "0812345678"), phone
        assert r.status == "Ready", phone


def test_not_a_phone():
    # too few digits for a mobile number: must not become a phone
    r = P.parse(ADDR + "08 1234")
    assert r.phone is None


def test_dataset_unchanged_and_synced():
    clean = evaluate.run_evaluation(evaluate.DATASET, P)
    assert clean["micro_f1"] == 1.0 and (clean["tp"], clean["tn"], clean["fp"], clean["fn"]) == (100, 20, 0, 0)
    assert subprocess.run(["bash", "scripts/check_parser_sync.sh"]).returncode == 0
