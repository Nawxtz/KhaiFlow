"""T-022: parcel tracking / delivery-status questions are rejected like other non-address chat."""
import subprocess

import evaluate
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())


def shielded(r):
    return any(w.startswith("[IntentShield]") for w in r.warnings) and r.confidence == 0.0


def test_tracking_questions_rejected():
    for text in ("เลขพัสดุ TH0123456789 ส่งถึงยังคะ", "ขอเลขพัสดุหน่อยค่ะ", "พัสดุส่งถึงยังคะ ติดตามยังไง",
                 "ขอเลข tracking หน่อยครับ"):
        assert shielded(P.parse(text)), text


def test_address_with_status_question_still_parses():
    r = P.parse("คุณเอ 1/1 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678 ส่งถึงยังคะ")
    assert r.status == "Ready" and (r.zipcode, r.phone) == ("20130", "0812345678")


def test_dataset_unchanged_and_synced():
    clean = evaluate.run_evaluation(evaluate.DATASET, P)
    assert clean["micro_f1"] == 1.0 and (clean["tp"], clean["tn"], clean["fp"], clean["fn"]) == (100, 20, 0, 0)
    assert subprocess.run(["bash", "scripts/check_parser_sync.sh"]).returncode == 0
