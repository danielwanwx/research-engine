import json

from research_engine.eval import DEFAULT_FIXTURE, main, run_eval, run_eval_v2


def test_offline_eval_exercises_connector_and_detects_all_invalid_probes(tmp_path):
    scorecard = run_eval(output_dir=tmp_path)

    assert scorecard["summary"]["passed"] is True
    assert scorecard["summary"]["invalid_probes_detected"] == 5
    assert scorecard["summary"]["invalid_probes_total"] == 5
    assert scorecard["summary"]["checks_passed"] == scorecard["summary"]["checks_total"]
    written = json.loads((tmp_path / "scorecard.json").read_text(encoding="utf-8"))
    assert written["summary"] == scorecard["summary"]


def test_eval_main_returns_success(tmp_path):
    assert main(["--output", str(tmp_path)]) == 0


def test_offline_v2_eval_passes_b1_through_b10_and_embeds_m0(tmp_path):
    scorecard = run_eval_v2(output_dir=tmp_path)

    assert scorecard["schema_version"] == "research_engine.eval.v2"
    assert scorecard["summary"]["passed"] is True
    assert scorecard["summary"]["checks_passed"] == 10
    assert scorecard["summary"]["checks_total"] == 10
    assert scorecard["summary"]["m0_checks_passed"] == 9
    assert scorecard["summary"]["invalid_probes_detected"] == 5
    assert [row["id"] for row in scorecard["benchmarks"]] == [
        f"B{index}" for index in range(1, 11)
    ]
    by_id = {row["id"]: row for row in scorecard["benchmarks"]}
    assert by_id["B2"]["detail"]["repositories"] == [
        "sgl-project/sglang",
        "vllm-project/vllm",
    ]
    assert "canonical-refetch" in by_id["B4"]["detail"]["pass_ids"]
    assert by_id["B4"]["detail"]["canonical_urls"]
    assert by_id["B7"]["detail"]["journal_entries"] == 2
    assert by_id["B7"]["detail"]["first_manifest_immutable"] is True
    assert by_id["B9"]["detail"]["coverage"]["required_facets_covered"] == 7


def test_eval_main_returns_failure_for_misclassified_fixture(tmp_path):
    payload = json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_valid"] = False
    fixture = tmp_path / "bad-fixture.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["--fixture", str(fixture), "--output", str(tmp_path / "result")]) == 1
    scorecard = json.loads((tmp_path / "result" / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["summary"]["passed"] is False
    assert scorecard["fixture"] == str(fixture.resolve())
