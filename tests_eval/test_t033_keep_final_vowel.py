"""T-033: the last word of address_detail keeps its vowels and tone marks ("สีดา", not "สีด")."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def detail(d):
    return P.parse("คุณมะลิ " + d + TAIL).address_detail


def test_final_word_kept_whole():
    assert detail("5/7 หมู่บ้านสีดา") == "5/7 หมู่บ้านสีดา"
    assert detail("5/7 ตรงข้ามร้านป้าดี") == "5/7 ตรงข้ามร้านป้าดี"
    assert detail("5/7 ไซส์ M สีดำ") == "5/7 ไซส์ M สีดำ"


def test_stray_marks_still_dropped():
    clean = P._clean_address_detail
    assert clean("5/7 ่") == "5/7"
    assert clean("5/7 ะ") == "5/7"
    assert detail("10/1 ฝากรปภ.ได้เลยค่ะ") == "10/1"
