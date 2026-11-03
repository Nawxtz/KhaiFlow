"""T-039: order codes with letters or a "เลข"/"order" label leave address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
HEAD = "คุณมะลิ 5/7 ม.3 ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678 "


def test_order_code_dropped():
    for note in ["เลขออเดอร์ #A12345", "ออเดอร์ #A12345", "เลขออเดอร์ 12345", "order #A12345", "Order: AB123"]:
        r = P.parse(HEAD + note)
        assert r.status == "Ready", note
        assert r.zipcode == "20150", note
        assert r.address_detail == "5/7 หมู่ 3", note


def test_plain_order_number_still_dropped():
    for note in ["ออเดอร์ 12345", "รหัสลูกค้า 123"]:
        assert P.parse(HEAD + note).address_detail == "5/7 หมู่ 3", note


def test_plain_address_unchanged():
    r = P.parse(HEAD.strip())
    assert r.address_detail == "5/7 หมู่ 3"
