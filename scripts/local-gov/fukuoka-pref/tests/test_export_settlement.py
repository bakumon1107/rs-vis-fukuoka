"""決算の書き出し（export_settlement.py）の単体テスト。小さな入力で、行・部局の内訳・説明・節・歳入の款と検算を確かめる。"""
import json

from conftest import load

es = load("export_settlement.py", "export_settlement")

M = {"予算現額": 400, "支出済額": 300, "翌年度繰越額": 0, "不用額": 100}


def _write(tmp_path, kmk=None, bukyoku=None, toku=None, setsu=None):
    kmk = kmk or {
        "totals": {"expense": [400, 300, 0, 100, 100]},
        "expense": [{"no": 2, "name": "総務費", "children": [{"no": 1, "name": "総務管理費", "children": [
            {"no": 1, "name": "一般管理費", "pdf_page": 32, **M}]}]}],
        "revenue": [{"no": 1, "name": "県税", "予算現額": 10, "調定額": 12, "収入済額": 11, "不納欠損額": 0, "収入未済額": 1,
                     "過誤納金（内数）": 0}],
    }
    bukyoku = bukyoku or {"部局": [
        {"部局": "総務部", "款": [{"no": 2, "項": [{"no": 1, "目": [
            {"no": 1, "name": "一般管理費", "予算現額": 260, "支出済額": 200, "翌年度繰越額": 0, "不用額": 60, "決算の内容": "人件費"}]}]}]},
        {"部局": "会計管理局", "款": [{"no": 2, "項": [{"no": 1, "目": [
            {"no": 1, "name": "一般管理費", "予算現額": 140, "支出済額": 100, "翌年度繰越額": 0, "不用額": 40}]}]}]},
    ]}
    toku = toku or {"fail": 0, "会計": [{"会計": "福岡県住宅管理特別会計", "pdf_page": 250,
                             "歳入": [{"no": 1, "name": "県営住宅管理費収入", "予算現額": 10, "調定額": 9, "収入済額": 10,
                                      "不納欠損額": 0, "収入未済額": 0, "過誤納金": 1}],
                             "款項": [{"款": 1, "款名": "県営住宅管理費", "項": 1, "項名": "県営住宅管理費", "決算額": 50}], "款項の計": 50,
                             "項": [{"款": 1, "項": 1, "項名": "県営住宅管理費", "pdf_page": 251, "目": [
                                 {"no": 1, "name": "県営住宅管理費", "予算現額": 60, "支出済額": 50, "翌年度繰越額": 0, "不用額": 10,
                                  "決算の内容": "人件費 一般会計繰出金", "不用額の内容": "管理事務費 （10千円）"}]}]}]}
    setsu = setsu or {"目": [
        {"款": 2, "項": 1, "目": 1, "pdf_page": 46, "節": [{"no": 1, "支出済額": 100}, {"no": 2, "支出済額": 200}]},
        {"会計": "福岡県住宅管理特別会計", "款": 1, "項": 1, "目": 1, "pdf_page": 300, "節": [{"no": 27, "支出済額": 50}]},
    ]}
    for name, d in (("kessan-kmk.json", kmk), ("kessan-bukyoku.json", bukyoku), ("kessan-toku.json", toku),
                    ("kessan-setsu.json", setsu)):
        (tmp_path / name).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_build_rows_and_checks(tmp_path):
    _write(tmp_path)
    f, ok, _ = es.build(str(tmp_path), {"住宅管理": "jutaku-kanri"})
    assert ok and f["basis"] == "settlement" and f["year"] == 2024
    g = next(r for r in f["rows"] if r["id"] == "general/expense/2-1-1")
    assert g["amount"]["v"] == 300 and g["unused"]["v"] == 100
    # 部局の内訳と、部局ごとの説明（一般会計は部局の要素に持つ）
    assert [d["name"] for d in g["by_department"]] == ["総務部", "会計管理局"]
    assert g["by_department"][0]["explanation"] == {"content": "人件費"} and "explanation" not in g
    # 節は支出済額。名前は節番号で決まる名前（reference）
    assert [(s["no"], s["name"], s["amount"]["v"], s["name_src"]) for s in g["setsu"]] == [
        (1, "報酬", 100, "reference"), (2, "給料", 200, "reference")]
    assert {"source": "r6-kessan-jikou", "page": 46} in g["pages"]
    # 特別会計の目は行に説明を持つ
    t = next(r for r in f["rows"] if r["account"] == "special:jutaku-kanri")
    assert t["id"] == "special:jutaku-kanri/expense/1-1-1" and t["explanation"]["unused"].startswith("管理事務費")
    # 出典は、その項の目の表があるページ（会計の最初のページではない）
    assert {"source": "r6-kessan-gaiyou", "page": 251} in t["pages"]
    # 歳入は会計 × 款（過誤納金を含む）
    rk = {(r["account"], r["kan"]["no"]): r for r in f["revenue_by_kan"]}
    assert rk[("special:jutaku-kanri", 1)]["overpaid"]["v"] == 1 and "overpaid" not in rk[("general", 1)]
    assert f["checks"]["all_ok"] == 2


def test_special_account_extraction_must_pass(tmp_path):
    # 特別会計の抽出が FAIL を出した（または件数のない古い出力）・款項の表の計が読めない、のどれでも「検算済み」にしない
    for toku_patch in ({"fail": 2}, {"fail": None}, {"款項の計": None}):
        _write(tmp_path)
        p = tmp_path / "kessan-toku.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        if "fail" in toku_patch:
            if toku_patch["fail"] is None:
                d.pop("fail")
            else:
                d["fail"] = toku_patch["fail"]
        else:
            d["会計"][0]["款項の計"] = None
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        _, ok, _ = es.build(str(tmp_path), {"住宅管理": "jutaku-kanri"})
        assert not ok, toku_patch


def test_department_sum_mismatch_is_ng(tmp_path):
    _write(tmp_path, bukyoku={"部局": [{"部局": "総務部", "款": [{"no": 2, "項": [{"no": 1, "目": [
        {"no": 1, "name": "一般管理費", "予算現額": 260, "支出済額": 200, "翌年度繰越額": 0, "不用額": 60}]}]}]}]})
    f, ok, lines = es.build(str(tmp_path), {"住宅管理": "jutaku-kanri"})
    assert not ok and f["checks"]["rules"]["部局の内訳"] == 1 and any("general/expense/2-1-1" in x for x in lines)


def test_unknown_special_account_stops(tmp_path):
    _write(tmp_path)
    try:
        es.build(str(tmp_path), {"財政調整基金": "zaisei-chosei-kikin"})
    except SystemExit as e:
        assert "住宅管理" in str(e)
    else:
        raise AssertionError("知らない特別会計で止まらない")
