"""一般財源の中身（general_fund.py）の単体テスト。小さな行と組み替えの表で、款そのもの・組み替え・差し引きの組み立てと止める条件を見る。"""
from conftest import load

gf = load("general_fund.py", "general_fund")


def v(n):
    return {"v": n, "src": "ocr"}


def rev(id_, kan, kan_name, amount, setsu=None):
    r = {"id": id_, "account": "general", "side": "revenue", "kan": {"no": kan, "name": kan_name}, "amount": v(amount)}
    if setsu:
        r["setsu"] = [{"no": no, "name": f"節{no}", "amount": v(a)} for no, a in setsu]
    return r


def exp(id_, general):
    return {"id": id_, "account": "general", "side": "expense", "kan": {"no": 2, "name": "総務費"}, "amount": v(general),
            "funding": {"national": v(0), "bond": v(0), "other": v(0), "general": v(general)}}


ROWS = [
    rev("general/revenue/1-1-1", 1, "県税", 1000_000),
    rev("general/revenue/1-1-2", 1, "県税", 500_000),
    rev("general/revenue/9-2-1", 9, "国庫支出金", 300_000, setsu=[(1, 100_000), (4, 200_000)]),
    rev("general/revenue/11-1-1", 11, "寄附金", 50_000),
    # 特別会計の行は数えない
    {**rev("special:x/revenue/1-1-1", 1, "県税", 9_999_000), "account": "special:x"},
    exp("general/expense/2-1-1", 1_500_000 + 200_000 + 30_000 + 70_000),
]

TABLE = {
    "確認日": "2026-11-14",
    "款そのもの": [1],
    "組み替え": [
        {"label": "国庫支出金のうち 臨時交付金", "basis": "matched", "refs": [{"id": "general/revenue/9-2-1", "setsu": 4}], "額": 200},
        {"label": "寄附金のうち", "basis": "summed", "refs": [{"id": "general/revenue/11-1-1"}], "部分": True, "額": 30},
    ],
    "差し引き": {"label": "諸収入のうち（差し引き）", "概算": 71, "許す差": 2},
    "注": ["注1"],
}


def test_builds_rows_and_residual():
    out, fails = gf.build(ROWS, TABLE)
    assert fails == []
    assert [(x["label"], x["amount"], x["basis"]) for x in out["rows"]] == [
        ("県税", 1_500_000, "revenue_kan"),
        ("国庫支出金のうち 臨時交付金", 200_000, "matched"),
        ("寄附金のうち", 30_000, "summed"),
        ("諸収入のうち（差し引き）", 70_000, "residual"),
    ]
    assert out["total"] == 1_800_000 and sum(x["amount"] for x in out["rows"]) == out["total"]
    assert out["notes"] == ["注1"] and out["checked_on"] == "2026-11-14"


def test_stops_when_an_amount_is_unreadable():
    # 読めない額（None）を 0 円にして足りない内訳を作らない（款そのもの・一般財源の合計・組み替えの元）
    for rows in (ROWS + [rev("general/revenue/1-1-3", 1, "県税", None)],
                 ROWS + [{**exp("general/expense/2-1-9", 0), "funding": {"general": v(None)}}],
                 [rev("general/revenue/9-2-1", 9, "国庫支出金", 300_000, setsu=[(4, None)])] + ROWS[:2] + ROWS[3:]):
        out, fails = gf.build(rows, TABLE)
        assert out is None and any("額が読めない" in f for f in fails)


def test_stops_when_table_does_not_match_data():
    bad = {**TABLE, "組み替え": [{**TABLE["組み替え"][0], "額": 201}, TABLE["組み替え"][1]]}
    out, fails = gf.build(ROWS, bad)
    assert out is None and any("表の額" in f for f in fails)
    # 部分の行は、表の額が目の額を超えたら止める
    over = {**TABLE, "組み替え": [TABLE["組み替え"][0], {**TABLE["組み替え"][1], "額": 51}]}
    assert gf.build(ROWS, over)[0] is None
    # 差し引きが概算から許す差を超えて違う
    far = {**TABLE, "差し引き": {**TABLE["差し引き"], "概算": 60}}
    assert gf.build(ROWS, far)[0] is None
    # 表の目・節がない
    missing = {**TABLE, "組み替え": [{**TABLE["組み替え"][0], "refs": [{"id": "general/revenue/9-2-1", "setsu": 9}]}]}
    assert gf.build(ROWS, missing)[0] is None


# 歳入の款 → 財源（かんたんの図の3列）。差し引き 70,000 は諸収入・財産収入から（概算 60 + 11 = 71 千円。差の -1,000 は大きい諸収入で吸収）
FLOW_ROWS = [
    *ROWS[:-1],
    rev("general/revenue/14-1-1", 14, "諸収入", 80_000),
    rev("general/revenue/10-1-1", 10, "財産収入", 20_000),
    exp("general/expense/2-1-1", 1_800_000),
    # 国庫支出金 300,000 − 臨時交付金 200,000 = 100,000。その他 = 寄附金 20,000 + 諸収入 21,000 + 財産収入 9,000
    {**exp("general/expense/2-1-2", 0), "funding": {"national": v(100_000), "bond": v(0), "other": v(50_000), "general": v(0)}},
]
FLOW_TABLE = {**TABLE, "歳入の款と財源": {"説明": "x", "国庫支出金": "national"}, "差し引きの款ごとの概算": {"説明": "x", "14": 60, "10": 11}}


def test_flows_return_general_fund_to_revenue_kan():
    out, fails = gf.build(FLOW_ROWS, FLOW_TABLE)
    assert fails == []
    flows = [(x["kan_name"], x["funding"], x["amount"], x.get("estimated", False)) for x in out["flows"]]
    assert flows == [
        ("県税", "general", 1_500_000, False),
        ("国庫支出金", "general", 200_000, False),
        ("国庫支出金", "national", 100_000, False),
        ("財産収入", "general", 11_000, True),
        ("財産収入", "other", 9_000, False),
        ("寄附金", "general", 30_000, False),
        ("寄附金", "other", 20_000, False),
        ("諸収入", "general", 59_000, True),
        ("諸収入", "other", 21_000, False),
    ]
    residual = out["rows"][-1]
    assert residual["split"] == [{"kan": 10, "amount": 11_000}, {"kan": 14, "amount": 59_000}]
    assert out["rows"][1]["kan"] == 9  # 組み替えの行に元の款


def test_flows_stop_when_totals_do_not_match():
    # 財源の合計が歳出の財源内訳と合わない（国庫支出金を other にしてしまった）
    wrong = {**FLOW_TABLE, "歳入の款と財源": {"国庫支出金": "other"}}
    out, fails = gf.build(FLOW_ROWS, wrong)
    assert out is None and any("national の合計" in f for f in fails)
    # 帯が負（概算が款の額より大きい）
    big = {**FLOW_TABLE, "差し引きの款ごとの概算": {"14": 10, "10": 61}}
    out, fails = gf.build(FLOW_ROWS, big)
    assert out is None and any("帯が負" in f for f in fails)
    # 表の款が歳入にない・財源が不正
    stale = {**FLOW_TABLE, "歳入の款と財源": {"国庫支出金": "national", "地方債": "bond", "県債": "loan"}}
    _, fails = gf.build(FLOW_ROWS, stale)
    assert any("款「地方債」が歳入にない" in f for f in fails) and any("県債 の財源が不正" in f for f in fails)
    # 差し引きの実額が概算の合計より小さすぎて、一番大きい款の分が負になる
    # （実額 70 千円・概算 80 + 80。差の -90 を 80 の款で吸収すると -10）
    tiny = {**FLOW_TABLE, "差し引き": {**FLOW_TABLE["差し引き"], "概算": 70}, "差し引きの款ごとの概算": {"14": 80, "10": 80}}
    out, fails = gf.build(FLOW_ROWS, tiny)
    assert out is None and any("負になる" in f for f in fails)
    # 表に「歳入の款と財源」がなければ flows を作らない（今までどおり）
    assert "flows" not in gf.build(ROWS, TABLE)[0]
