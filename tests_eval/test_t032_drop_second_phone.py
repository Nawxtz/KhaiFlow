"""T-032: only the first phone number is kept; any further phone and its separator leave address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
HEAD = "คุณโอ๋ 10/1 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 "


def test_second_phone_and_separator_dropped():
    for tail in ("0812345678 / 0898765432", "081-234-5678 / 089-876-5432", "0812345678/0898765432",
                 "0812345678 , 02-123-4567", "0812345678 หรือ 0898765432", "0812345678, 0898765432"):
        r = P.parse(HEAD + tail)
        assert r.phone == "0812345678", tail
        assert r.address_detail == "10/1", tail


def test_house_number_slash_and_zipcode_kept():
    r = P.parse("คุณโอ๋ 10/1 ซอย 5/2 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678 / 0898765432")
    assert r.address_detail == "10/1 ซอย 5/2"
    assert r.zipcode == "20130"
    r = P.parse(HEAD + "0812345678")
    assert r.phone == "0812345678" and r.address_detail == "10/1"
