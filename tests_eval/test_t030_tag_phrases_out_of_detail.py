"""T-030: guard/fold/dry instructions become tags only; their words never stay in address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def parse(d):
    return P.parse("คุณโอ๋ " + d + TAIL)


def test_instruction_words_dropped_tags_kept():
    cases = {
        "10/1 ฝากไว้ที่ป้อมยามได้เลย": "Drop_at_guard",
        "10/1 ฝากรปภ.ได้เลยค่ะ": "Drop_at_guard",
        "10/1 ห้ามพับ": "Do_not_fold",
        "10/1 อย่าพับเด็ดขาดนะคะ": "Do_not_fold",
        "10/1 ห้ามเปียกนะคะ": "Keep_dry",
    }
    for d, tag in cases.items():
        r = parse(d)
        assert r.address_detail == "10/1", d
        assert tag in r.tags, d


def test_landmark_with_similar_words_kept():
    r = parse("10/1 ตรงข้ามป้อมตำรวจ")
    assert r.address_detail == "10/1 ตรงข้ามป้อมตำรวจ"
    assert r.tags == []
