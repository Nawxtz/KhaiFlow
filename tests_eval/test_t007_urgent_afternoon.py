"""T-007: delivery-time phrase 'ส่งก่อนบ่าย' tags as Urgent and strips from address_detail."""
import subprocess

import evaluate
from parser import SmartAddressParser, build_mock_geo_db


def test_delivery_time_tag_urgent():
    geo_db = build_mock_geo_db()
    parser = SmartAddressParser(geo_db)

    # Base phrase from B-001 eval case
    res = parser.parse("ส่งก่อนบ่าย คุณมานี 88/1 ต.คลองหลวง อ.คลองหลวง จ.ปทุมธานี 12120")
    assert "Urgent" in res.tags
    assert "Time_sensitive" not in res.tags

    # Prefix variation 'ขอส่งก่อนบ่าย' matching 'ขอส่งก่อนเที่ยง'
    res_var = parser.parse("ขอส่งก่อนบ่าย คุณมานี 88/1 ต.คลองหลวง อ.คลองหลวง จ.ปทุมธานี 12120")
    assert "Urgent" in res_var.tags


def test_delivery_time_stripped_from_address_detail():
    geo_db = build_mock_geo_db()
    parser = SmartAddressParser(geo_db)

    # Phrase placed in middle of address
    res = parser.parse("คุณมานี 88/1 ส่งก่อนบ่าย ต.คลองหลวง อ.คลองหลวง จ.ปทุมธานี 12120")
    assert res.address_detail is not None
    assert "ก่อนบ่าย" not in res.address_detail
    assert "ส่งก่อนบ่าย" not in res.address_detail
    assert res.address_detail == "88/1"

    # Phrase placed at end of address
    res_end = parser.parse("คุณมานี 88/1 ต.คลองหลวง อ.คลองหลวง จ.ปทุมธานี 12120 ส่งก่อนบ่าย")
    assert res_end.address_detail is not None
    assert "ก่อนบ่าย" not in res_end.address_detail
    assert res_end.address_detail == "88/1"


def test_evaluate_dataset_expects_urgent():
    cases = [c for c in evaluate.DATASET if "ส่งก่อนบ่าย" in c.input]
    assert len(cases) == 1, "Expected exactly one case with 'ส่งก่อนบ่าย' in evaluate.DATASET"
    case = cases[0]
    assert "Urgent" in case.expect_tags
    assert "Time_sensitive" not in case.expect_tags


def test_evaluate_runs_clean():
    geo_db = build_mock_geo_db()
    parser = SmartAddressParser(geo_db)
    results = evaluate.run_evaluation(evaluate.DATASET, parser)
    failures = [
        (c, r, msg)
        for c, r, msg in results["failed_cases"]
        if "ส่งก่อนบ่าย" in c.input
    ]
    assert failures == []


def test_parser_and_constants_copies_synced():
    proc = subprocess.run(["bash", "scripts/check_parser_sync.sh"])
    assert proc.returncode == 0
