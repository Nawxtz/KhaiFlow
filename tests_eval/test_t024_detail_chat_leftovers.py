"""T-024: chat leftovers never reach address_detail (it is printed on the shipping label)."""
import subprocess

import evaluate
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
GEO = "ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130"


def detail(text):
    return P.parse(text).address_detail


def test_labelled_order_or_customer_number_dropped():
    assert detail(f"ออเดอร์ 123450812345678 คุณโอ๋ 10/1 {GEO} 0812345678") == "10/1"
    assert detail(f"คุณโอ๋ 10/1 {GEO} เบอร์ 0812345678 รหัสลูกค้า 201300812345678") == "10/1"


def test_emoji_and_symbols_dropped():
    assert detail(f"🙏 คุณบี 12 ม.3 {GEO} ☎️ 0841234567") == "12 หมู่ 3"


def test_bracketed_note_dropped():
    assert detail(f"คุณโอ๋ 10/1 {GEO} เบอร์ 0812345678 (ตอนเย็น)") == "10/1"


def test_request_phrase_dropped():
    assert detail(f"คุณโอ๋ 10/1 {GEO} 0812345678 ขอใบกำกับภาษีด้วยค่ะ") == "10/1"


def test_real_details_kept():
    assert detail(f"คุณโอ๋ 10/1 ซ.สุขุมวิท 22 {GEO} 0812345678") == "10/1 ซอยสุขุมวิท 22"
    assert detail(f"ส่งที่ 55/5 หมู่ 2 {GEO} คุณต้น 0812345678") == "55/5 หมู่ 2"
    assert detail(f"John Smith 5/5 Sukhumvit Rd {GEO} 0899999999") == "5/5 Sukhumvit Rd"


def test_dataset_unchanged_and_synced():
    clean = evaluate.run_evaluation(evaluate.DATASET, P)
    assert clean["micro_f1"] == 1.0 and (clean["tp"], clean["tn"], clean["fp"], clean["fn"]) == (100, 20, 0, 0)
    assert subprocess.run(["bash", "scripts/check_parser_sync.sh"]).returncode == 0
