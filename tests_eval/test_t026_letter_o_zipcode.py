"""T-026: a zipcode typed with letter O/o for zero reads as the zipcode and leaves address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
GEO = "ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี"


def parse(text):
    return P.parse(text)


def test_letter_o_zipcode_read_as_digits():
    for z in ("2O13O", "2o13o", "2O130"):
        r = parse(f"คุณโอ๋ 10/1 {GEO} {z} 0812345678")
        assert r.zipcode == "20130", z
        assert r.address_detail == "10/1", z
        assert r.status == "Ready", z


def test_letter_o_zipcode_after_phone():
    r = parse(f"คุณโอ๋ 10/1 {GEO} 0812345678 2O13O")
    assert r.address_detail == "10/1"
    assert r.status == "Ready"


def test_other_letter_o_tokens_kept():
    # not five characters, or fewer than three real digits: not a zipcode, stays as typed
    assert parse(f"คุณโอ๋ 10/1 ห้อง 1O2 {GEO} 20130 0812345678").address_detail == "10/1 ห้อง 1O2"
    assert parse(f"คุณโอ๋ 10/1 OTOP {GEO} 20130 0812345678").address_detail == "10/1 OTOP"
    assert parse(f"คุณโอ๋ 10/1 ห้อง O1OO2 {GEO} 20130 0812345678").address_detail == "10/1 ห้อง O1OO2"
