"""T-107: surname_dropped: a surname equal to a sub-district must not override the typed exact district (backlog4 S-5, Q2/W2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

def test_surname_is_no_sub():
    r = P.parse("ศุภชัย ศรีสุข 0919952903 882 หมู่ 12 ต.หนองแงซ อ.บ้านแฮด จ.ขอนแก่น")
    assert (r.sub_district, r.district) == ("หนองแซง", "บ้านแฮด")
    assert r.status == "Needs confirmation"


def test_exact_sub_still_ready_unchanged():
    r = P.parse("ศุภชัย ศรีสุข 0919952903 882 หมู่ 12 ต.หนองแซง อ.บ้านแฮด จ.ขอนแก่น")
    assert (r.sub_district, r.district, r.status) == ("หนองแซง", "บ้านแฮด", "Ready")


def test_prefixed_sub_equal_to_surname_still_used():
    r = P.parse("สมชาย 0919952903 882 หมู่ 12 ต.ศรีสุข อ.สีชมพู จ.ขอนแก่น")
    assert (r.sub_district, r.district) == ("ศรีสุข", "สีชมพู")


def test_district_without_sub_unchanged():
    r = P.parse("ศุภชัย 0919952903 882 หมู่ 12 อ.สีชมพู จ.ขอนแก่น")
    assert r.district == "สีชมพู"
