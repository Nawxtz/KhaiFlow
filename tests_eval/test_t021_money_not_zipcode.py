"""T-021: a money amount ("ยอด 30000 บาท") is never a zipcode, even after chat junk is stripped."""
import subprocess

import evaluate
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())


def is_rejected(r):
    return any(w.startswith("[IntentShield]") for w in r.warnings) or r.status == "Not an Address"


def test_payment_messages_are_not_addresses():
    for text in ("ยอด 30000 บาท โอนแล้วค่ะ", "โอนแล้วค่ะ ยอด 30000 บาท", "ยอด 30000 บาทค่ะ", "30000 บาท โอนแล้วนะคะ"):
        r = P.parse(text)
        assert r.zipcode is None and r.province is None, text
        assert is_rejected(r), text


def test_address_with_amount_keeps_real_zipcode():
    r = P.parse("คุณเอ 1/1 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678 ยอด 30000 บาท")
    assert (r.zipcode, r.province, r.phone) == ("20130", "ชลบุรี", "0812345678")


def test_real_zipcode_30000_still_works():
    r = P.parse("คุณนก 7/7 ต.ในเมือง อ.เมืองนครราชสีมา จ.นครราชสีมา 30000 0861234567")
    assert (r.zipcode, r.province) == ("30000", "นครราชสีมา")


def test_dataset_unchanged_and_synced():
    clean = evaluate.run_evaluation(evaluate.DATASET, P)
    assert clean["micro_f1"] == 1.0 and (clean["tp"], clean["tn"], clean["fp"], clean["fn"]) == (100, 20, 0, 0)
    assert subprocess.run(["bash", "scripts/check_parser_sync.sh"]).returncode == 0
