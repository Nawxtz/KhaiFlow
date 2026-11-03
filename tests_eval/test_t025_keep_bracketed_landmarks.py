"""T-025: bracketed landmarks and building info stay in address_detail; only time/contact notes go."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def detail(d):
    return P.parse("คุณโอ๋ " + d + TAIL).address_detail


def test_landmarks_and_buildings_kept():
    assert detail("10/1 (ตึก A ชั้น 3)") == "10/1 (ตึก A ชั้น 3)"
    assert detail("10/1 (ตรงข้ามเซเว่น)") == "10/1 (ตรงข้ามเซเว่น)"
    assert detail("10/1 (หลังวัด)") == "10/1 (หลังวัด)"


def test_time_and_contact_notes_dropped():
    for note in ("(ตอนเย็น)", "(ช่วงเช้า)", "(หลัง 5 โมง)", "(โทรก่อนส่ง)", "(โทรก่อน)"):
        assert detail("10/1 " + note) == "10/1", note
