"""T-012: evaluate.py measures F1 retention on noisy copies of the address cases (manuscript: noise robustness)."""
import evaluate
from parser import SmartAddressParser, build_mock_geo_db

CASE = evaluate.EvalCase(input="คุณมานี 88/1 ต.คลองหลวง อ.คลองหลวง จ.ปทุมธานี 12120", category="clean",
                         description="x", expect_address=True, expected={"province": "ปทุมธานี"})
REJECT = evaluate.EvalCase(input="สวัสดีครับ", category="rejection", description="y", expect_address=False)


def test_transforms_are_fixed_and_named():
    assert [name for name, _ in evaluate.NOISE_TRANSFORMS] == ["chat_prefix", "emoji_suffix", "newlines", "no_spaces"]
    out = {name: fn(CASE.input) for name, fn in evaluate.NOISE_TRANSFORMS}
    assert out["chat_prefix"] == "สวัสดีค่ะ รบกวนส่งที่นี่นะคะ " + CASE.input
    assert out["emoji_suffix"] == CASE.input + " ขอบคุณค่ะ 🙏😊"
    assert out["newlines"] == CASE.input.replace(" ", "\n")
    assert out["no_spaces"] == CASE.input.replace(" ", "")


def test_noisy_dataset_copies_only_address_cases():
    noisy = evaluate.noisy_dataset([CASE, REJECT])
    assert len(noisy) == 4
    assert all(c.expect_address and c.expected == CASE.expected for c in noisy)
    assert [c.category for c in noisy] == ["noise:chat_prefix", "noise:emoji_suffix", "noise:newlines", "noise:no_spaces"]


def test_robustness_report_on_dataset():
    parser = SmartAddressParser(build_mock_geo_db())
    r = evaluate.noise_robustness(evaluate.DATASET, parser)
    assert set(r) == {"clean_micro_f1", "per_transform", "retention"}
    assert set(r["per_transform"]) == {"chat_prefix", "emoji_suffix", "newlines", "no_spaces"}
    for v in r["per_transform"].values():
        assert 0.0 <= v <= 1.0
    noisy_mean = sum(r["per_transform"].values()) / 4
    # no_spaces is the hard one: it must actually cost something on DATASET, or the metric tells nothing
    assert r["per_transform"]["no_spaces"] < 1.0
    assert abs(r["retention"] - noisy_mean / r["clean_micro_f1"]) < 1e-9
    # deterministic: same numbers twice
    assert evaluate.noise_robustness(evaluate.DATASET, parser) == r


def test_report_line():
    parser = SmartAddressParser(build_mock_geo_db())
    results = evaluate.run_evaluation(evaluate.DATASET, parser)
    assert "F1 retention" not in evaluate.format_report(results, len(evaluate.DATASET))
    assert "F1 retention" in evaluate.format_robustness(evaluate.noise_robustness(evaluate.DATASET, parser))
