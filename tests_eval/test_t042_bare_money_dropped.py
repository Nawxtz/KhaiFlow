"""T-042: bare money ("590 บาท", "ราคา 590 บาท") leaves address_detail; house numbers and quantities stay."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
HEAD = "คุณมะลิ 5/7 ม.3 ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678 "


def test_bare_money_dropped():
    for note in ["590 บาท", "590บาท", "ราคา 590 บาท", "ราคา590บาท", "ราคา: 1,290.50 บาท", "ส่ง Kerry ค่ะ 590 บาท COD"]:
        r = P.parse(HEAD + note)
        assert r.status == "Ready", note
        assert r.zipcode == "20150", note
        assert r.address_detail == "5/7 หมู่ 3", note


def test_house_number_and_soi_not_dropped():
    r = P.parse("คุณมะลิ 5/7 ซอย 12 ม.3 ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678")
    assert "5/7" in r.address_detail
    assert "12" in r.address_detail


def test_money_after_soi_dropped():
    r = P.parse("คุณมะลิ 5/7 ซอย 12 ม.3 ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678 590 บาท")
    assert "บาท" not in r.address_detail


def test_quantity_still_in_detail():
    r = P.parse(HEAD + "2 ชิ้น")
    assert "2 ชิ้น" in r.address_detail


def test_money_only_message_unchanged():
    r = P.parse("ยอด 30000 บาท โอนแล้วค่ะ")
    assert r.status == "Cannot ship"
    assert r.zipcode is None
