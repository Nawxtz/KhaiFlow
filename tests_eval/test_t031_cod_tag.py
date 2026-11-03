"""T-031: cash-on-delivery requests become the COD tag and leave address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def parse(d):
    return P.parse("คุณโอ๋ 10/1 " + d + TAIL)


def test_cod_phrases_tagged_and_dropped():
    for d in ("เก็บเงินปลายทาง", "เก็บปลายทางค่ะ", "ชำระเงินปลายทาง", "จ่ายปลายทางนะคะ", "COD", "cod นะคะ"):
        r = parse(d)
        assert "COD" in r.tags, d
        assert r.address_detail == "10/1", d


def test_negated_cod_not_tagged():
    for d in ("ไม่เก็บเงินปลายทาง", "ไม่ต้องเก็บปลายทาง", "ไม่ต้อง เก็บเงินปลายทาง"):
        r = parse(d)
        assert "COD" not in r.tags, d
        assert r.address_detail == "10/1", d


def test_similar_words_kept_untagged():
    r = parse("Codeville")
    assert r.address_detail == "10/1 Codeville" and "COD" not in r.tags
    r = parse("ปลายทางซอย 3")
    assert r.address_detail == "10/1 ปลายทางซอย 3" and "COD" not in r.tags


def test_other_tags_unchanged():
    r = parse("เก็บเงินปลายทาง ห้ามพับ")
    assert sorted(r.tags) == ["COD", "Do_not_fold"]
    assert r.address_detail == "10/1"
