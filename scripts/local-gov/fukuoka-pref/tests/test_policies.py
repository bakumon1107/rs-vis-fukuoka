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


def _real(fails):
    """表の見直しを促す失敗（R8 の直しの表・例外の表の行が、この小さな入力では使われない）を除く。それは test_tables_unused で見る"""
    # 制度融資の事項がない入力も同じ（test_loans_item_must_appear_once で見る）
    return [f for f in fails if "直しの表の行が使われていない" not in f and "OVER_MOKU_OK の目" not in f
            and "中小企業振興資金融資費 の事項がない" not in f]


def _item(name, kamoku, amount, **kw):
    return {"柱": "３．感染症や災害に負けない強靭な社会をつくる", "区分": "地域防災力と危機管理の強化", "課名": "警察本部",
            "科目": kamoku, "新規": False, "事項名": name, "予算額": amount, "前年度": None, "説明": [], "source": "277217.pdf",
            "pdf_page": 5, **kw}


def test_scope_kamoku_and_outside(tmp_path):
    items = [
        _item("災害対応力強化費", ["9 1 2", "9 ? 4", "9 2 1"], 1_000),       # 項が決まらない目4: 予算に 9-1-4 だけ → 9-1-4
        _item("架空の事業費", ["9 1 2", "9 ? 3", "9 2 2"], 500),            # 目3: 予算に 9-?-3 の目がない → 予算にない印
        _item("認知症医療センター事業費", ["3 2 5"], 100),                     # 予算にない科目
        _item("少年補導員等活動費", ["9 1 2", "9 ? 1", "9 2 2"], 50),       # 同じ形でも、直しの表にある事項は表で決める
        # 債務負担行為の行: 今年度の額（200）は事項に載せ、限度額（9,999）だけを除いた分に数える
        _item("県立学校施設整備費", ["9 1 2"], 200, 債務負担行為=9_999),
        _item("林業改善資金助成事業費", ["特別会計"], 7),                       # 除く（特別会計）
        # 制度融資は事項の円にせず灰色の円（説明書の事項と同じ額であること）。限度額も数えない
        _item("中小企業振興資金融資費", ["7 1 1"], 900, 債務負担行為=3),
        # 今年度の額が 0 で限度額だけ: 円がないので事項に入れない（限度額は数える）
        _item("国際園芸博覧会出展事業費", ["9 1 2"], 0, 債務負担行為=13),
        # 特別会計の事項の債務負担行為は、一般会計の範囲の外なので数えない
        _item("流域下水道事業費", ["企業会計"], 5, 債務負担行為=100),
    ]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    pol, lines, fails = ep.build(str(tmp_path), ROWS)
    assert _real(fails) == []
    names = [i["name"] for i in pol["items"]]
    assert names == ["災害対応力強化費", "架空の事業費", "認知症医療センター事業費", "少年補導員等活動費", "県立学校施設整備費"]
    assert pol["items"][3]["kamoku"][1] == {"kan": 9, "kou": 2, "moku": 1, "row": "general/expense/9-2-1", "printed": "9 ? 1"}
    assert pol["excluded"] == {"special": {"count": 2, "amount": 12_000}, "debt_burden": {"count": 2, "amount": 10_012_000}}
    k = pol["items"][0]["kamoku"]
    # 項を予算の目（1つだけ）で決めた科目にも、資料の読みを残す
    assert k[1] == {"kan": 9, "kou": 1, "moku": 4, "row": "general/expense/9-1-4", "printed": "9 ? 4"}
    assert pol["items"][1]["kamoku"][1] == {"kan": 9, "kou": None, "moku": 3, "row": None, "unmatched": True}
    assert pol["items"][2]["kamoku"][0]["unmatched"]
    assert pol["pillars"] == [{"no": 3, "name": "感染症や災害に負けない強靭な社会をつくる"}]
    out = {o["key"]: o["amount"] for o in pol["outside"]}
    assert out["tax_transfers"] == 1_500_000 and out["debt_service"] == 2_000_000
    assert out["personnel"] == 4_000_000 and out["loans"] == 900_000
    # 事項の合計 + 図に載らない経費 = 一般会計の歳出
    assert sum(i["amount"] for i in pol["items"]) + sum(out.values()) == pol["expense_total"] == 23_500_000


def test_unreadable_kamoku_mixed_accounts_and_missing_file_fail(tmp_path):
    items = [
        _item("少年補導員等活動費", ["9 1 2", "9 ? 1"], 50),
        _item("款の決まらない事項", ["9 1 2", "? 1 4"], 10),   # 款の字が決まらない行は黙って落とさない
        _item("またがる事項", ["9 1 2", "特別会計"], 10),       # 一般会計と特別会計にまたがる: 額を分けられない
        _item("外のある事項", ["9 1 2", "外"], 10),             # 「外」は落とさず印で持つ（失敗にしない）
        _item("項の決まらない事項", ["9 ? 1"], 10),             # 予算に 9-1-1・9-2-1 の両方: 直しの表になければ止める
    ]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    pol, _, fails = ep.build(str(tmp_path), ROWS)
    fails = _real(fails)
    assert len(fails) == 3 and "'? 1 4'" in fails[0] and "またがる" in fails[1] and "項が決まらない" in fails[2]
    outer = next(i for i in pol["items"] if i["name"] == "外のある事項")
    assert outer["other_kamoku"] and len(outer["kamoku"]) == 1
    # 科目のない事項・予算額の読めない除く事項（債務負担行為）も止める
    items = [_item("科目のない事項", [], 10), _item("額のない（債務負担行為）", ["10 2 1"], None)]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("科目がない" in f for f in fails) and any("予算額が読めない" in f for f in fails)
    # 抽出の検算が通っていない・fails のない古い shisaku.json は止める
    for bad in ({"items": [], "fails": ["x: 内訳の合計 1 ≠ 予算額 2"]}, {"items": []}):
        (tmp_path / "shisaku.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        assert ep.build(str(tmp_path), ROWS)[2]
    # 制度融資の事項の額が説明書の事項と違えば止める（二重・漏れ）
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": [_item("中小企業振興資金融資費", ["7 1 1"], 1)], "fails": []},
                                                      ensure_ascii=False), encoding="utf-8")
    assert any("中小企業振興資金融資費" in f for f in ep.build(str(tmp_path), ROWS)[2])
    # 施策別資料の抽出の結果がない作業ディレクトリでは止める（公開データから policies が黙って消えないよう）
    _, _, fails = ep.build(str(tmp_path / "none"), ROWS)
    assert fails and "shisaku.json" in fails[0]


def test_unread_fields_pillar_and_fixed_costs(tmp_path):
    items = [
        _item("取組の読めない事項", ["9 1 2"], 10, 区分=""),
        _item("柱の読めない事項", ["9 1 2"], 10, 柱=None),
        _item("基盤の事項", ["9 1 2"], 10, 柱="計画推進の基盤づくり", 区分="行政改革の推進"),
        _item("特別会計の事項", ["特別会計", "外"], 7),   # 「外」があっても特別会計の事項として除く
    ]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    pol, _, fails = ep.build(str(tmp_path), ROWS)
    fails = _real(fails)
    assert len(fails) == 2 and "区分" in fails[0] and "柱" in fails[1]
    assert [(i["name"], i["pillar"]) for i in pol["items"]] == [("基盤の事項", None)]
    assert pol["excluded"]["special"]["count"] == 1
    # 4つの決まった出費のどれかが 0（名前が変わった）なら止める（円が消えて「その他」に黙って入らないよう）
    rows = [r for r in ROWS if r["kan"]["name"] != "公債費"] + [_row("general/expense/12-1-1", "公債", 2_000_000)]
    _, _, fails = ep.build(str(tmp_path), rows)
    assert any("公債費" in f and "が 0" in f for f in fails)


def test_moku_total_fixes_and_tables(tmp_path, monkeypatch):
    # 1つの目だけを科目に持つ事項の合計が目の額を超えれば止める（9-2-1 は 3,000,000 円）
    items = [_item("大きい事項", ["9 2 1"], 2_000), _item("もう1つ", ["9 2 1"], 1_500)]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ep, "KAMOKU_FIXES", {})
    monkeypatch.setattr(ep, "OVER_MOKU_OK", {})
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("9-2-1" in f and "超える" in f for f in fails)
    # 直しの表で別の目に直すと止まらず、直した科目に資料の印字が残る
    monkeypatch.setattr(ep, "KAMOKU_FIXES", {("大きい事項", "9 2 1"): "9 1 2"})
    pol, _, fails = ep.build(str(tmp_path), ROWS)
    assert _real(fails) == [] and pol["items"][0]["kamoku"][0] == {"kan": 9, "kou": 1, "moku": 2, "row": "general/expense/9-1-2", "printed": "9 2 1"}
    # 例外の表に理由を書いた目は止めない。表の行が使われない（超えていない）ときは見直しを促す
    monkeypatch.setattr(ep, "KAMOKU_FIXES", {})
    monkeypatch.setattr(ep, "OVER_MOKU_OK", {"general/expense/9-2-1": "理由", "general/expense/9-1-4": "理由"})
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert [f for f in fails if "の事項がない" not in f] == ["施策別資料: OVER_MOKU_OK の目 general/expense/9-1-4 はもう超えていない（表を見直す）"]
    # 例外の目の事項には、その事項だけで目の額を超えるときに印を付ける（ここではどちらも1件では 300 万円を超えない）
    pol, _, _ = ep.build(str(tmp_path), ROWS)
    assert not any(i.get("exceeds_moku") for i in pol["items"])
    items_big = [_item("大きい事項", ["9 2 1"], 3_500), _item("もう1つ", ["9 2 1"], 100)]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items_big, "fails": []}, ensure_ascii=False), encoding="utf-8")
    pol, _, _ = ep.build(str(tmp_path), ROWS)
    assert [i["name"] for i in pol["items"] if i.get("exceeds_moku")] == ["大きい事項"]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    # 直しの表の行き先が予算の目にないときは止める（「印字のまま」と「直した」を並べない）
    monkeypatch.setattr(ep, "OVER_MOKU_OK", {})
    monkeypatch.setattr(ep, "KAMOKU_FIXES", {("大きい事項", "9 2 1"): "9 9 9", ("もう1つ", "9 2 1"): "9 1 2"})
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("直しの表の科目 '9 9 9' が予算の目にない" in f for f in fails)
    # 複数の目にまたがる事項: その目の組の中だけの事項の合計が、組の目の額の合計を超えれば止める（9-2-1 + 9-1-1 = 4,000,000 円）
    monkeypatch.setattr(ep, "KAMOKU_FIXES", {})
    # またがる 3,500 千円 + 片方だけ 900 千円 = 440 万円 > 400 万円（片方だけの 9-1-1 は 90 万円 ≦ 100 万円で、1つの目の確かめは通る）
    items = [_item("またがる", ["9 2 1", "9 1 1"], 3_500), _item("片方だけ", ["9 1 1"], 900)]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("目の組" in f for f in fails)
    # 同じ番号の柱の名前がページで違えば止める
    items = [_item("甲", ["9 1 2"], 1), _item("乙", ["9 1 2"], 1, 柱="３．感染症や災害に負けない")]
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ep, "OVER_MOKU_OK", {})
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("柱 3 の名前が2通り" in f for f in fails)


def test_loans_item_must_appear_once(tmp_path):
    # 制度融資の事項がない（名前が変わった）・2度ある: 施策の円と灰色の円で二重に数える・片方が消えるので止める
    for items, word in (([_item("甲", ["9 1 2"], 1)], "の事項がない"),
                        ([_item("中小企業振興資金融資費", ["7 1 1"], 900)] * 2, "2度ある")):
        (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
        assert any(word in f for f in ep.build(str(tmp_path), ROWS)[2])


def test_other_negative_fails(tmp_path):
    items = [_item("大きすぎる事項", ["9 1 2"], 30_000)]  # 3,000万円 > 歳出 2,350万円
    (tmp_path / "shisaku.json").write_text(json.dumps({"items": items, "fails": []}, ensure_ascii=False), encoding="utf-8")
    _, _, fails = ep.build(str(tmp_path), ROWS)
    assert any("その他" in f for f in fails)
    # 直しの表の行が資料に出てこない（読み取りが変わった）ときも止める
    assert any("直しの表の行が使われていない" in f for f in fails)
