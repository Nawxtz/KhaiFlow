"""T-046: surnames that are geo names or start with a stop word stay in the receiver (full geo DB)."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser, build_mock_geo_db

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
MOCK = SmartAddressParser(build_mock_geo_db())


def _recv(text):
    return FULL.parse(text).receiver


def test_geo_name_surname_in_receiver():
    assert _recv("นายมาลัย ใจดี 0915908301 72/71 หมู่ 2 ซอยวัดใหม่ ต.แหลมกลัด อ.เมืองตราด จ.ตราด 23000") == "นายมาลัย ใจดี"
    assert _recv("คุณวิภา ศรีสุข 0812345678 12 ม.3 ต.ท่ายาง อ.ท่ายาง จ.เพชรบุรี 76130") == "คุณวิภา ศรีสุข"
    assert _recv("ชื่อ: นายณัฐวุฒิ ศรีสุข\nเบอร์: 0855835865\nที่อยู่: 346 ซ.5 สกาด ปัว น่าน 55120") == "นายณัฐวุฒิ ศรีสุข"


def test_stop_word_prefix_surname_in_receiver():
    assert _recv("น.ส.สมหญิง แก้วมณี 063-667-1276 905/56 ถ.พหลโยธิน ต.โพนสูง อ.ปทุมรัตต์ จ.ร้อยเอ็ด 45190") == "น.ส.สมหญิง แก้วมณี"
    assert _recv("นางสาวปวีณา หอมจันทร์ 0898765432 55/1 ถ.มิตรภาพ ต.ในเมือง อ.เมืองขอนแก่น จ.ขอนแก่น 40000") == "นางสาวปวีณา หอมจันทร์"
    assert _recv("ส่งที่ สุดารัตน์ บ้านสวน 0861112222 9 ม.1 ต.หนองบัว อ.เมืองอุดรธานี จ.อุดรธานี 41000") == "สุดารัตน์ บ้านสวน"


def test_long_first_name_at_end_whole():
    r = FULL.parse("137/1 ม.15 ต.ท่าจำปา อ.ท่าอุเทน จ.นครพนม 31130 เกียรติศักดิ์ ศรีสุข 0910499641")
    assert r.receiver == "เกียรติศักดิ์ ศรีสุข"


def test_stop_words_still_end_the_name():
    tail = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"
    assert MOCK.parse("คุณเอ ซอยวัดใหม่ 9" + tail).receiver == "คุณเอ"
    assert MOCK.parse("คุณเอ หอพักป้าจุ๋ม ห้อง 305" + tail).receiver == "คุณเอ"
    assert MOCK.parse("คุณเอ แก้ว 9 หมู่ 2" + tail).receiver == "คุณเอ"
    assert MOCK.parse("คุณเอ ถนนสุขุมวิท 9" + tail).receiver == "คุณเอ"
