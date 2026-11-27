"""公営企業会計の名前の決め方（kigyo_names.py）と書き出し（export_kigyo.py）の単体テスト。入力は R8 の病院事業会計の形を小さくしたもの。"""
import json

from conftest import load

kn = load("kigyo_names.py", "kigyo_names")
ek = load("export_kigyo.py", "export_kigyo")


def _kigyo():
    return {"unit": "千円", "fails": [], "会計": [{
        "会計": "病院事業会計",
        "収益的収入及び支出": {
            "収入": [{"no": 1, "name": "病院事業収益", "pdf_page": 134, "項": [
                {"no": 1, "name": "医業収益", "pdf_page": 134, "目": [
                    {"no": 1, "name": "入院収益", "pdf_page": 134, "金額": 100},
                    {"no": 2, "name": "その他区業収益", "pdf_page": 134, "金額": 20}]}]}],
            "支出": [{"no": 1, "name": "病院事業費", "pdf_page": 135, "項": [
                {"no": 1, "name": "医業費用", "pdf_page": 135, "目": [{"no": 1, "name": "経費", "pdf_page": 135, "金額": 110}]}]}]},
        "資本的収入及び支出": {
            "収入": [{"no": 1, "name": "資本的収入", "pdf_page": 137, "項": [
                {"no": 1, "name": "企業債", "pdf_page": 137, "目": [{"no": 1, "name": "企業債", "pdf_page": 137, "金額": 30}]}]}],
            "支出": [{"no": 1, "name": "資本的支出", "pdf_page": 138, "項": [
                {"no": 1, "name": "建至几叔改良費", "pdf_page": 138, "目": [{"no": 1, "name": "建設改良費", "pdf_page": 138, "金額": 50}]}]}]},
    }]}


def _yosansho():
    return {"会計": [{"会計": "病院事業会計", "条": {
        "3": {"収入": [{"no": 1, "name": "病院事業収益", "金額": 120, "項": [{"no": 1, "name": "医業収益", "金額": 120}]}],
              "支出": [{"no": 1, "name": "病院事業費", "金額": 110, "項": [{"no": 1, "name": "医業費用", "金額": 110}]}]},
        "4": {"収入": [{"no": 1, "name": "資本的収入", "金額": 30, "項": [{"no": 1, "name": "企業債", "金額": 30}]}],
              "支出": [{"no": 1, "name": "資本的支出", "金額": 50, "項": [{"no": 1, "name": "建設改良費", "金額": 50}]}]}},
        "補填": {"不足額": 20, "内訳": [{"name": "過年度分損益勘定留保資金", "金額": 20}], "pdf_page": 86}}]}


FIXES = [{"会計": "病院事業会計", "page": 134, "段": "目", "読み": "その他区業収益", "名前": "その他医業収益"},
         {"会計": "病院事業会計", "page": 138, "段": "項", "読み": "建至几叔改良費", "名前": "建設改良費"}]
# 新 OCR の行（番号・金額・簡体字の「费」・空白を含む）。目の「入院収益」「経費」「企業債」「建設改良費」がある。
# 「建設改良費」は「建 設 改」「良 费」の2行に分かれている
PAGES = {p: kn.ocr_lines(t) for p, t in {
    134: "1病院事業収益   120\n1 医業収益   120\n入 院 収 益   100",
    135: "1病院事業费 110\n1 医業費用 110\n1 経 费   110",
    137: "1資本的収入 30\n1 企業債 30\n1 企業債 30",
    138: "1資本的支出 50\n1 建 設 改\n良 费 50"}.items()}


def test_names_from_readings_yosansho_and_fixes():
    named, fails, counts = kn.decide(_kigyo(), _yosansho(), FIXES, PAGES)
    assert fails == []
    a = named["会計"][0]
    m2 = a["収益的収入及び支出"]["収入"][0]["項"][0]["目"][1]
    assert (m2["name"], m2["name_src"], m2["name_read"]) == ("その他医業収益", "correction", "その他区業収益")
    kou = a["資本的収入及び支出"]["支出"][0]["項"][0]
    assert (kou["name"], kou["name_src"]) == ("建設改良費", "correction")
    assert a["収益的収入及び支出"]["支出"][0]["項"][0]["目"][0]["name_src"] == "readings"  # 「経費」は新 OCR の「経 费」と一致
    assert counts == {"readings": 11, "correction": 2}


def test_unconfirmed_name_and_unused_fix_fail():
    k = _kigyo()
    k["会計"][0]["収益的収入及び支出"]["支出"][0]["項"][0]["目"][0]["name"] = "経嚢"  # 新 OCR にも予算書の本体にもない
    _, fails, _ = kn.decide(k, _yosansho(), FIXES + [{"会計": "病院事業会計", "page": 999, "段": "目", "読み": "x", "名前": "y"}], PAGES)
    assert any("経嚢" in f for f in fails) and any("使われていない" in f for f in fails)
    # 同じページの別の名前の頭だけ（「医業費用」の「医業」）は一致にしない
    k = _kigyo()
    k["会計"][0]["収益的収入及び支出"]["支出"][0]["項"][0]["目"][0]["name"] = "医業"
    assert any("「医業」" in f for f in kn.decide(k, _yosansho(), FIXES, PAGES)[1])
    # 2行に分かれた名前の上の行だけ（金額のない行のかけら）は一致にしない。上下をつないだものは一致
    lines = kn.ocr_lines("1 支払利息及び\n企業債取扱諸費 50\n2 雑支出 3")
    assert "支払利息及び企業債取扱諸費" in lines and "支払利息及び" not in lines
    assert "企業債取扱諸費雑支出" not in lines  # 2つの目にまたがるつなぎ
    # 抽出の失敗は引き継ぐ。fails のない古い kigyo.json は止める
    k = {**_kigyo(), "fails": ["目の合計が項と合わない"]}
    assert any("実施計画の抽出: 目の合計" in f for f in kn.decide(k, _yosansho(), FIXES, PAGES)[1])
    k = _kigyo()
    del k["fails"]
    assert any("fails がない" in f for f in kn.decide(k, _yosansho(), FIXES, PAGES)[1])


def test_kan_matched_by_number_not_position():
    # 実施計画に第1款がなく第2款だけあるとき、予算書の本体の第1款の名前と比べない
    k = _kigyo()
    kan = k["会計"][0]["資本的収入及び支出"]["収入"][0]
    kan["no"], kan["name"] = 2, "資本的収入"
    y = _yosansho()
    y["会計"][0]["条"]["4"]["収入"].append({"no": 2, "name": "別の款", "金額": 0, "項": []})
    named, fails, _ = kn.decide(k, y, FIXES, {**PAGES, 137: kn.ocr_lines("1 企業債 30")})
    assert any("款「資本的収入」" in f for f in fails)


def test_load_ocr_stops_on_duplicate_page(tmp_path):
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "done.json").write_text("{}")
        (tmp_path / d / "p0134.txt").write_text("入院収益", encoding="utf-8")
    try:
        kn.load_ocr([str(tmp_path / "a"), str(tmp_path / "b")])
        assert False, "止まるはず"
    except SystemExit as e:
        assert "p134" in str(e)


def test_export_rows_accounts_and_checks(tmp_path):
    named, _, _ = kn.decide(_kigyo(), _yosansho(), FIXES, PAGES)
    (tmp_path / "kigyo-named.json").write_text(json.dumps({**named, "fails": []}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "yosansho.json").write_text(json.dumps(_yosansho(), ensure_ascii=False), encoding="utf-8")
    accounts, rows, lines, fails, external = ek.build(str(tmp_path))
    assert fails == []
    assert "一致 4/4" in external["公営企業会計_予算書"]
    assert accounts[0]["id"] == "enterprise:byoin"
    assert accounts[0]["enterprise"]["capital_shortfall"]["amount"] == 20_000
    ids = [r["id"] for r in rows]
    assert ids == ["enterprise:byoin/revenue/3-1-1-1", "enterprise:byoin/revenue/3-1-1-2", "enterprise:byoin/expense/3-1-1-1",
                   "enterprise:byoin/revenue/4-1-1-1", "enterprise:byoin/expense/4-1-1-1"]
    assert rows[1]["moku"] == {"no": 2, "name": "その他医業収益", "name_src": "correction"}
    assert rows[0]["enterprise_section"] == "収益的" and rows[-1]["enterprise_section"] == "資本的"
    assert rows[0]["amount"] == {"v": 100_000, "src": "text"}
    # 目の合計が予算書の本体と合わなければ止める
    y = _yosansho()
    y["会計"][0]["条"]["3"]["支出"][0]["金額"] = 999
    (tmp_path / "yosansho.json").write_text(json.dumps(y, ensure_ascii=False), encoding="utf-8")
    assert any("第3条 支出" in f for f in ek.build(str(tmp_path))[3])
    # 款の合計は合うが、目が別の項に付いている（項ごとの合計が予算書の本体と合わない）
    y = _yosansho()
    y["会計"][0]["条"]["3"]["収入"][0]["項"] = [{"no": 1, "name": "医業収益", "金額": 100}, {"no": 2, "name": "医業外収益", "金額": 20}]
    (tmp_path / "yosansho.json").write_text(json.dumps(y, ensure_ascii=False), encoding="utf-8")
    assert any("項ごとの目の合計" in f for f in ek.build(str(tmp_path))[3])
    # 予算書の本体にある事業会計が実施計画にない
    y = _yosansho()
    y["会計"].append({"会計": "電気事業会計", "条": {}})
    (tmp_path / "yosansho.json").write_text(json.dumps(y, ensure_ascii=False), encoding="utf-8")
    assert any("電気事業会計" in f and "取れていない" in f for f in ek.build(str(tmp_path))[3])
    # 目の金額が読めていない
    (tmp_path / "yosansho.json").write_text(json.dumps(_yosansho(), ensure_ascii=False), encoding="utf-8")
    broken = json.loads(json.dumps(named))
    broken["会計"][0]["収益的収入及び支出"]["収入"][0]["項"][0]["目"][0]["金額"] = None
    (tmp_path / "kigyo-named.json").write_text(json.dumps({**broken, "fails": []}, ensure_ascii=False), encoding="utf-8")
    assert any("金額が読めていない" in f for f in ek.build(str(tmp_path))[3])
    # 名前の決め方が失敗していれば・名前のステップの出力がなければ止める
    (tmp_path / "kigyo-named.json").write_text(json.dumps({**named, "fails": ["x"]}, ensure_ascii=False), encoding="utf-8")
    assert ek.build(str(tmp_path))[3]
    (tmp_path / "kigyo-named.json").unlink()
    assert "kigyo-named.json" in ek.build(str(tmp_path))[3][0]
