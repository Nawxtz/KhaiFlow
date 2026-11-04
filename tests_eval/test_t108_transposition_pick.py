"""T-108: typo_sub_zip_autofill_guess: on equal fuzzy scores pick the candidate fewest edits away, an adjacent swap counting as one (backlog4 S-6)"""
import os

from geo_engine import GeoDatabase, correct_typo
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

def test_transposed_sub_picks_closest():
    # The candidate order of a set is random per process, so check both orders.
    for cands in (["หนองยาง", "หนองฉาง"], ["หนองฉาง", "หนองยาง"]):
        assert correct_typo("หนองาฉง", cands)[0] == "หนองฉาง"


def test_transposed_sub_parse_picks_closest():
    r = P.parse("คุณเอ 0871798416 99 ม.3 ต.หนองาฉง อ.หนองฉาง จ.อุทัยธานี")
    assert (r.sub_district, r.district) == ("หนองฉาง", "หนองฉาง")
    assert r.status == "Needs confirmation"


def test_exact_sub_still_ready_unchanged():
    r = P.parse("คุณเอ 0871798416 99 ม.3 ต.หนองยาง อ.หนองฉาง จ.อุทัยธานี 61110")
    assert (r.sub_district, r.status) == ("หนองยาง", "Ready")


def test_single_substitution_typo_unchanged():
    r = P.parse("คุณเอ 0871798416 99 ม.3 ต.หนองยาน อ.หนองฉาง จ.อุทัยธานี")
    assert r.sub_district == "หนองยาง"
