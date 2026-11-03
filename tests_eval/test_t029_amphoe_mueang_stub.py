"""T-029: the short district form "อ.เมือง" never stays in address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())


def test_short_mueang_district_dropped():
    for d in ("อ.เมือง", "อ. เมือง", "อำเภอเมือง"):
        r = P.parse(f"คุณซี 88 ต.สุเทพ {d} จ.เชียงใหม่ 50200 0812345678")
        assert r.address_detail == "88", d
        assert r.district == "เมืองเชียงใหม่", d
    r = P.parse("คุณดี 1/2 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000 0812345678")
    assert r.address_detail == "1/2"


def test_mueang_inside_place_name_kept():
    r = P.parse("คุณโอ๋ 99 หมู่บ้านเมืองทอง ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678")
    assert r.address_detail == "99 หมู่บ้านเมืองทอง"
