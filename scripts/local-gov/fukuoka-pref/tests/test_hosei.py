"""補正予算の議案・総括の抽出（extract_hosei.py）の単体テスト。R8 6月補正（289924・289925）の行の形を小さく再現する。"""
from conftest import load

eh = load("extract_hosei.py", "extract_hosei")

GIAN = """
 第1条     歳入歳出予算の総額に歳入歳出それぞれ 2,545,648 千円を追加し、歳入歳出予算の総額を歳入歳出それぞれ
     2,302,572,676 千円とする。
第１表     歳入歳出予算補正
         歳               入
             款                                   項               補   正   前    の    額      補   正       額          計
9   国   庫        支       出       金                                         217,166,261            2,545,648       219,711,909
                                     2   国   庫       補   助   金             105,542,805            2,545,648       108,088,453
         歳                   入           合           計                   2,300,027,028            2,545,648     2,302,572,676
         歳               出
2   総            務               費                                           82,908,436           1,604,118          84,512,554
                                     6   防           災       費                1,599,154           1,604,118           3,203,272
7   商       工       費                     235,771,435     941,530     236,712,965
                        1   商   業   費     222,672,763     941,530     223,614,293
        歳       出           合   計       2,300,027,028   2,545,648   2,302,572,676
"""

SOUKATSU = """
                                          令和８年度福岡県一般会計歳入歳出補正予算事項別明細書
     （歳           入）                                                                          （単位：千円）
1    県                                    税                830,805,619                   0         830,805,619
9    国        庫           支       出       金                217,166,261            2,545,648        219,711,909
     歳        入           合           計                   1,047,971,880           2,545,648       1,050,517,528
     （歳           出）                                                                                                                      （単位：千円）
2    総        務              費      82,908,436        1,604,118        84,512,554                 0               0                       0               1,604,118
7    商        工              費      235,771,435           941,530     236,712,965                 0               0                       0                941,530
     歳       出       合       計        318,679,871     2,545,648     321,225,519
"""


def test_parse_gian_rows_and_article():
    fails = []
    g = eh.parse_gian(GIAN, fails)
    assert fails == []
    assert (g["追加額"], g["総額"]) == (2_545_648, 2_302_572_676)
    assert [(k["no"], k["補正額"], [q["no"] for q in k["項"]]) for k in g["歳出"]] == [(2, 1_604_118, [6]), (7, 941_530, [1])]
    assert g["合計"]["歳入"]["計"] == 2_302_572_676


def test_soukatsu_side_heading_with_unit_and_funding():
    fails = []
    s = eh.parse_soukatsu(SOUKATSU, fails)
    assert [k["no"] for k in s["歳入"]] == [1, 9] and [k["no"] for k in s["歳出"]] == [2, 7]
    assert s["歳出"][0]["財源"]["一般財源"] == 1_604_118


def test_verify_finds_kou_sum_and_article_mismatch():
    fails = []
    g = eh.parse_gian(GIAN, fails)
    g["歳出"][0]["項"][0]["補正額"] = 1   # 項の補正額の合計 ≠ 款
    g["追加額"] = 999                      # 第1条と合わない
    s = {"歳入": [], "歳出": [], "合計": {}}
    eh.verify(g, s, fails)
    assert any("項の補正額の合計" in f for f in fails) and any("第1条の追加額" in f for f in fails)


def test_verify_checks_bill_total_rows():
    # 議案の合計の行の補正前の読み違い（補正額・計は第1条と合う）も、補正前 + 補正額 = 計 で見つける
    fails = []
    g = eh.parse_gian(GIAN, fails)
    g["合計"]["歳入"] = dict(g["合計"]["歳入"], 補正前=999)
    eh.verify(g, {"歳入": [], "歳出": [], "合計": {}}, fails)
    assert any("議案 歳入 合計" in f for f in fails) and any("歳入の合計の行 ≠ 歳出の合計の行" in f for f in fails)


mn = load("ocr/mark_negatives.py", "mark_negatives")


def test_mark_negatives_prefers_the_same_line():
    # △ の中心（y=106）が同じ行の数字（y 90〜110）の高さにある。次の行の数字（y 120〜140、より左）は選ばない
    same = {"text": "40,040", "x0": 200, "x1": 300, "y0": 90, "y1": 110}
    nxt = {"text": "137,491", "x0": 160, "x1": 300, "y0": 120, "y1": 140}
    rec = {"vlines": [0, 400], "tables": [{"cols": [[same, nxt]]}]}
    assert mn.mark(rec, [{"x0": 100, "x1": 120, "y0": 100, "y1": 112}]) == 1
    assert same["text"] == "△40,040" and nxt["text"] == "137,491"


def test_mark_negatives_does_not_mark_another_line():
    # 同じ行の数字を OCR が読めなかった（同じ行に数字がない）: 次の行の数字には付けず、付けられなかった △ として返す
    nxt = {"text": "137,491", "x0": 160, "x1": 300, "y0": 120, "y1": 140}
    rec = {"vlines": [0, 400], "tables": [{"cols": [[nxt]]}]}
    unplaced = []
    tri = {"x0": 100, "x1": 120, "y0": 100, "y1": 112}
    assert mn.mark(rec, [tri], unplaced) == 0
    assert nxt["text"] == "137,491" and unplaced == [tri]


ex_h = load("export_hosei.py", "export_hosei")


def test_moku_name_correction_is_applied_before_the_name_check(tmp_path, monkeypatch):
    # OCR の崩れた目の名前（「道路橋りよう総務貨」）は当初の名前と照合できずに止まる。修正表（level moku）を当てると照合が通る
    import json
    initial = {"schema_version": 1, "gov_id": "fukuoka-pref", "accounts": [{"id": "general", "kind": "general", "name": "一般会計"}],
               "rows": [{"id": "general/expense/8-2-1", "account": "general", "side": "expense",
                         "kan": {"no": 8, "name": "県土整備費"}, "kou": {"no": 2, "name": "道路橋りょう費"},
                         "moku": {"no": 1, "name": "道路橋りょう総務費"}, "amount": {"v": 100000, "src": "ocr"}}]}
    m = {"kind": "目", "会計": "一般会計", "side": "歳出", "款": 8, "項": [2], "目番号": 1, "目名": "道路橋りよう総務貨",
         "本年度": 5, "前年度": 100, "比較": 105, "財源": {"国庫支出金": 0, "地方債": 0, "その他": 0, "一般財源": 5},
         "説明": [], "節": [], "pages": [27], "checks": {"C": True}}
    gs = {"総括": {"歳入": [], "歳出": [{"no": 8, "補正額": 5}]}}
    r = {"id": "R8-09-3", "round": "9月補正（第3号）", "kind": "定例", "bill_no": None, "src": "x", "text": False}

    def run(fixes):
        p = tmp_path / "fix.json"
        p.write_text(json.dumps({"修正": fixes}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(ex_h, "NAME_CORRECTIONS", str(p))
        fails = []
        out = ex_h.build_round(r, gs, [dict(m)], initial, fails)
        return out, fails
    out, fails = run([])
    assert any("目の名前が当初と違う" in f for f in fails) and out["rows"] == []
    out, fails = run([{"round": "R8-09-3", "id": "general/expense/8-2-1", "level": "moku",
                       "was": "道路橋りよう総務貨", "name": "道路橋りょう総務費"}])
    assert fails == [] and [x["id"] for x in out["rows"]] == ["general/expense/8-2-1"]
    # 当たる目のない修正は止める
    _, fails = run([{"round": "R8-09-3", "id": "general/expense/9-9-9", "level": "moku", "was": "x", "name": "y"}])
    assert any("当たる目がない" in f for f in fails)


def test_derive_soukatsu_from_previous_and_bill():
    prev = {"歳入": [{"no": 9, "name": "国庫支出金", "補正前": 1, "補正額": 0, "計": 100}],
            "歳出": [{"no": 2, "name": "総務費", "補正前": 1, "補正額": 0, "計": 60}, {"no": 7, "name": "商工費", "補正前": 1, "補正額": 0, "計": 40}]}
    gian = {"歳入": [{"no": 9, "補正額": 5}], "歳出": [{"no": 7, "補正額": 5}]}
    s = eh.derive_soukatsu(prev, gian)
    assert [(k["no"], k["補正前"], k["補正額"], k["計"]) for k in s["歳出"]] == [(2, 60, 0, 60), (7, 40, 5, 45)]
    assert s["合計"]["歳出"] == {"補正前": 100, "補正額": 5, "計": 105}
