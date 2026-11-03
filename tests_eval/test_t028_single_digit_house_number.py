"""T-028: a one-character house number ("3") stays in address_detail; other one-character leftovers still go."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
GEO = "ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี"


def test_single_digit_house_number_kept():
    assert P.parse(f"คุณโอ๋ 3 {GEO} 20130 0812345678").address_detail == "3"
    assert P.parse(f"คุณโอ๋ 7 {GEO} 20130 02-123-4567").address_detail == "7"
    assert P.parse(f"คุณโอ๋ 3 {GEO} 0812345678").address_detail == "3"


def test_single_non_digit_leftover_still_dropped():
    clean = SmartAddressParser._clean_address_detail
    assert clean("ก") is None
    assert clean("-") is None
    assert clean("ค่ะ") is None
    assert clean("3") == "3"
