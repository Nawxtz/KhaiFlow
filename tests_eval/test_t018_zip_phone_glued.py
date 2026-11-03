"""T-018: a zipcode glued to the phone number that follows it is split into both fields."""
import subprocess

import evaluate
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
GLUED = [
    ("คุณแม็ค99/9ต.แสนสุขอ.เมืองชลบุรีจ.ชลบุรี201300812345678", "20130", "0812345678"),
    ("คุณแดง1/1ต.บางนาอ.บางนากรุงเทพมหานคร10260081.111.2222", "10260", "0811112222"),
    ("คุณสมชาย1/1ต.แสนสุขอ.เมืองชลบุรีจ.ชลบุรี20130081-111-1111", "20130", "0811111111"),
]


def test_glued_zip_and_phone_are_split():
    for text, zipcode, phone in GLUED:
        r = P.parse(text)
        assert (r.zipcode, r.phone) == (zipcode, phone), text


def test_spaced_input_unchanged():
    r = P.parse("คุณแม็ค 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678")
    assert (r.zipcode, r.phone, r.province) == ("20130", "0812345678", "ชลบุรี")


def test_no_spaces_noise_improves_and_clean_stays_perfect():
    noisy = [c for c in evaluate.noisy_dataset(evaluate.DATASET) if c.category == "noise:no_spaces"]
    prf = evaluate.run_evaluation(noisy, P)["field_prf"]
    assert prf["zipcode"]["recall"] == 1.0
    assert prf["phone"]["recall"] >= 0.75
    clean = evaluate.run_evaluation(evaluate.DATASET, P)
    assert clean["micro_f1"] == 1.0


def test_parser_copies_synced():
    assert subprocess.run(["bash", "scripts/check_parser_sync.sh"]).returncode == 0
