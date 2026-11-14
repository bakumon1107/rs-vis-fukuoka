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
