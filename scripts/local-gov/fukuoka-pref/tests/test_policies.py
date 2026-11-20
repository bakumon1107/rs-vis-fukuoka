"""施策別資料の事項の書き出し（export_policies.py）の単体テスト。"""
import json

from conftest import load

ep = load("export_policies.py", "export_policies")


def _row(rid, kan, amount, setsu=(), items=()):
    return {"id": rid, "account": "general", "side": "expense", "kan": {"name": kan}, "amount": {"v": amount},
            "setsu": [{"no": n, "amount": {"v": v}} for n, v in setsu], "items": [{"name": n, "amount": {"v": v}} for n, v in items]}


ROWS = [
    _row("general/expense/9-1-2", "警察費", 10_000_000, setsu=[(2, 4_000_000)]),
    _row("general/expense/9-1-4", "警察費", 5_000_000),
    _row("general/expense/9-2-1", "警察費", 3_000_000),
    _row("general/expense/9-1-1", "警察費", 1_000_000),
    _row("general/expense/12-1-1", "公債費", 2_000_000),
    _row("general/expense/13-1-1", "諸支出金", 1_500_000),
    _row("general/expense/7-1-1", "商工費", 1_000_000, items=[("中小企業振興資金融資費", 900_000)]),
]


def _item(name, kamoku, amount, **kw):
    return {"柱": "３．感染症や災害に負けない強靭な社会をつくる", "区分": "地域防災力と危機管理の強化", "課名": "警察本部",
            "科目": kamoku, "新規": False, "事項名": name, "予算額": amount, "前年度": None, "説明": [], "source": "277217.pdf",
            "pdf_page": 5, **kw}


def test_scope_kamoku_and_outside(tmp_path):
    items = [
        _item("災害対応力強化費", ["9 1 2", "9 ? 4", "9 2 1"], 1_000),       # 項が決まらない目4: 予算に 9-1-4 だけ → 9-1-4
        _item("少年補導員等活動費", ["9 1 2", "9 ? 1", "9 2 2"], 500),      # 目1: 9-1-1・9-2-1 とも予算にある → 決めない
        _item("認知症医療センター事業費", ["3 2 5"], 100),                     # 予算にない科目
        _item("県立学校施設整備費（債務負担行為）", ["10 2 1"], 9_999),        # 除く（限度額）
        _item("林業改善資金助成事業費", ["特別会計"], 7),                       # 除く（特別会計）
    ]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    pol, lines, fails = ep.build(str(tmp_path), ROWS)
    assert fails == []
    names = [i["name"] for i in pol["items"]]
    assert names == ["災害対応力強化費", "少年補導員等活動費", "認知症医療センター事業費"]
    assert pol["excluded"] == {"special": {"count": 1, "amount": 7_000}, "debt_burden": {"count": 1, "amount": 9_999_000}}
    k = pol["items"][0]["kamoku"]
    assert k[1] == {"kan": 9, "kou": 1, "moku": 4, "row": "general/expense/9-1-4"}
    assert pol["items"][1]["kamoku"][1]["kou_unresolved"] and pol["items"][2]["kamoku"][0]["unmatched"]
    assert pol["pillars"] == [{"no": 3, "name": "感染症や災害に負けない強靭な社会をつくる"}]
    out = {o["key"]: o["amount"] for o in pol["outside"]}
    assert out["tax_transfers"] == 1_500_000 and out["debt_service"] == 2_000_000
    assert out["personnel"] == 4_000_000 and out["loans"] == 900_000
    # 事項の合計 + 図に載らない経費 = 一般会計の歳出
    assert sum(i["amount"] for i in pol["items"]) + sum(out.values()) == pol["expense_total"] == 23_500_000


def test_other_negative_fails(tmp_path):
    items = [_item("大きすぎる事項", ["9 1 2"], 30_000)]  # 3,000万円 > 歳出 2,350万円
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("その他" in f for f in fails)
