from research_engine.packs import build_pack_queries, load_research_packs, pack_summary, select_research_pack


def test_load_and_select_default_packs():
    packs = load_research_packs()
    ids = {pack["id"] for pack in packs}

    assert {"generic", "memory_cycle"} <= ids
    assert select_research_pack("DRAM HBM shortage")["id"] == "memory_cycle"
    assert select_research_pack("restaurant lease negotiation")["id"] == "generic"


def test_empty_cwd_packs_does_not_mask_package_defaults(tmp_path, monkeypatch):
    (tmp_path / "packs").mkdir()
    monkeypatch.chdir(tmp_path)

    assert select_research_pack("DRAM HBM shortage")["id"] == "memory_cycle"


def test_pack_summary_and_queries_are_template_driven():
    pack = select_research_pack("DRAM HBM shortage")
    queries = build_pack_queries("DRAM HBM shortage", pack)

    assert pack_summary(pack)["intent"] == "financial_market_research"
    assert any(query["tier"] == "official_ir" for query in queries)
    assert all("{topic}" not in query["query"] for query in queries)
