from pathlib import Path

from research_engine.interactive import parse_path_list, run_research_wizard
from research_engine.models import ResearchRunResult


def input_from(answers):
    iterator = iter(answers)

    def fake_input(prompt):
        return next(iterator)

    return fake_input


def test_research_wizard_no_args_asks_topic_and_runs_default_deep_public():
    calls = {}
    output = []

    def engine_factory(**kwargs):
        calls["engine_kwargs"] = kwargs

        class FakeEngine:
            def run(self, topic, **run_kwargs):
                calls["topic"] = topic
                calls["run_kwargs"] = run_kwargs
                return ResearchRunResult(
                    run_id="run-1",
                    run_dir="/tmp/research-run",
                    topic=topic,
                    pack_id="generic",
                    status="complete",
                    dry_run=False,
                    raw_rows=1,
                    loop_status="complete_with_review_required",
                    stop_reason="completed_with_review_required",
                    feedback_action_count=1,
                )

        return FakeEngine()

    exit_code = run_research_wizard(
        [],
        input_func=input_from(["DRAM HBM cycle", "", "1", "y"]),
        output_func=output.append,
        engine_factory=engine_factory,
    )

    assert exit_code == 0
    assert calls["engine_kwargs"]["source_timeout_seconds"] == 10.0
    assert calls["topic"] == "DRAM HBM cycle"
    assert calls["run_kwargs"]["depth"] == "deep"
    assert calls["run_kwargs"]["platform_scope"] == "broad"
    assert calls["run_kwargs"]["agent_reach"] is False
    assert calls["run_kwargs"]["external_evidence_paths"] == []
    assert any("loop status: complete_with_review_required" in line for line in output)


def test_research_wizard_topic_uses_all_read_only_sources_and_jsonl_paths():
    calls = {}
    output = []

    def engine_factory(**kwargs):
        calls["engine_kwargs"] = kwargs

        class FakeEngine:
            def run(self, topic, **run_kwargs):
                calls["topic"] = topic
                calls["run_kwargs"] = run_kwargs
                return ResearchRunResult(
                    run_id="run-2",
                    run_dir="/tmp/research-run",
                    topic=topic,
                    pack_id="generic",
                    status="complete_with_warnings",
                    dry_run=False,
                    raw_rows=2,
                    loop_status="complete_with_review_required",
                    stop_reason="completed_with_review_required",
                    feedback_action_count=2,
                    warnings=["external_jsonl skipped missing source"],
                )

        return FakeEngine()

    exit_code = run_research_wizard(
        ["medical billing denial trend"],
        input_func=input_from(["3", "4", "/tmp/a.jsonl, ~/b.jsonl", "yes"]),
        output_func=output.append,
        engine_factory=engine_factory,
    )

    paths = calls["run_kwargs"]["external_evidence_paths"]
    assert exit_code == 0
    assert calls["topic"] == "medical billing denial trend"
    assert calls["run_kwargs"]["depth"] == "audit"
    assert calls["run_kwargs"]["platform_scope"] == "all"
    assert calls["run_kwargs"]["agent_reach"] is True
    assert [path.name for path in paths] == ["a.jsonl", "b.jsonl"]
    assert any("Do not paste cookies" in line for line in output)
    assert any("warnings" in line for line in output)


def test_research_wizard_can_cancel_before_run():
    calls = {}

    def engine_factory(**kwargs):
        calls["engine_created"] = True
        raise AssertionError("engine should not be created after cancel")

    exit_code = run_research_wizard(
        ["contract clause research"],
        input_func=input_from(["1", "1", "n"]),
        output_func=lambda line: None,
        engine_factory=engine_factory,
    )

    assert exit_code == 130
    assert calls == {}


def test_research_wizard_help_does_not_run_engine():
    calls = {}
    output = []

    def engine_factory(**kwargs):
        calls["engine_created"] = True
        raise AssertionError("engine should not be created for help")

    exit_code = run_research_wizard(
        ["--help"],
        input_func=input_from([]),
        output_func=output.append,
        engine_factory=engine_factory,
    )

    assert exit_code == 0
    assert calls == {}
    assert output[0] == "Usage: research [research topic]"


def test_parse_path_list_accepts_comma_separated_paths():
    paths = parse_path_list("/tmp/a.jsonl, relative.jsonl,")

    assert paths == [Path("/tmp/a.jsonl"), Path("relative.jsonl")]
