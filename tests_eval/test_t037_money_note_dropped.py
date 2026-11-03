"""T-037: money notes leave address_detail; a money-only message still cannot ship."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
HEAD = "คุณมะลิ 5/7 ม.3 ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678 "


def test_money_note_dropped():
    for note in ["ยอด 590 บาท", "ค่าส่ง 50", "ยอดโอน 1,290.50 บาท", "ค่าส่ง: 40บ.", "ยอดรวม 890 บาท ค่าส่ง 50 บาท",
                 "ยอด590บาท"]:
        r = P.parse(HEAD + note)
        assert r.status == "Ready", note
        assert r.zipcode == "20150", note
        assert r.address_detail == "5/7 หมู่ 3", note


def test_money_only_message_still_cannot_ship():
    r = P.parse("ยอด 30000 บาท โอนแล้วค่ะ")
    assert r.status == "Cannot ship"
    assert r.zipcode is None


def test_plain_address_unchanged():
    r = P.parse(HEAD.strip())
    assert r.address_detail == "5/7 หมู่ 3"
