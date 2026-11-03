"""T-038: a plain "Line: <handle>" leaves address_detail; words containing "line" stay."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
HEAD = "คุณมะลิ 5/7 ม.3 ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678 "


def test_line_handle_dropped():
    for note in ["Line: mali99", "line : mali99", "LINE:mali99", "Line ID: mali99"]:
        r = P.parse(HEAD + note)
        assert r.status == "Ready", note
        assert r.zipcode == "20150", note
        assert r.address_detail == "5/7 หมู่ 3", note


def test_online_words_kept():
    r = P.parse(HEAD + "สั่งออนไลน์ online")
    assert "online" in r.address_detail
    assert "สั่งออนไลน์" in r.address_detail


def test_plain_address_unchanged():
    r = P.parse(HEAD.strip())
    assert r.address_detail == "5/7 หมู่ 3"
