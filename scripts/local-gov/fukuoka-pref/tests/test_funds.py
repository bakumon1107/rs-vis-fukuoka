"""財産に関する調書の基金の抽出（extract_funds.py）の単体テスト。入力は R6 の調書（テキスト）と R4・H28 の OCR の行の形を小さく再現したもの。"""
from conftest import load

fu = load("extract_funds.py", "extract_funds")

TEXT = """
○地方自治法第２４１条第１項の規定に基づき、特定の目的のために財産を維持し、資金を積み立てるために設置されたもの
（１） 福岡県財政調整基金                                       ▲は減を示す。
        区                       分       前年度末現在高      決算年度中増減高      決算年度末現在高
                                                       千円              千円               千円          千円                千円
    有           価       証           券
                                                  0                        0                    0           0                 0
                                                            (   ▲ 13,374,161 )
    現                               金
                                          60,739,168            ▲ 7,396,921             53,342,247       14,131,389        67,473,636
    一       般   会   計   貸   付       金
                                           2,800,000              10,574,161            13,374,161        9,879,647        23,253,808
（４） 福岡県県営林造成事業振興基金
有        価         証       券           －                       －                  －          －              －
（５） 福岡県災害救助基金
動     備   蓄   物   資
産                                     58,021              1,740            59,761           0          59,761
○地方自治法第２４１条第１項の規定に基づき、特定の目的のために定額の資金を運用するために設置されたもの
（１） 福岡県土地開発基金
不                                                     ㎡ (           ▲ 241.08 )    ㎡                      ㎡            ㎡                        ㎡
動     土            地   宅           地
産                                          8,716.30                ▲ 7,386.62                  1,329.68         0.00                 1,329.68
 現                                 金
                                           379,475                     85,108                  464,583             ▲ 7,180             457,403
運用状況
 件                                 数             8                          7         8                             ▲1                       7
"""


class TestParseText:
    def test_rows_kinds_and_skips(self):
        funds = fu.parse(TEXT)
        fz = funds["福岡県財政調整基金"]
        assert fz["kind"] == "積立" and fz["no"] == 1
        assert fz["holdings"]["現金"] == [60739168, -7396921, 53342247, 14131389, 67473636]
        assert fz["holdings"]["一般会計貸付金"] == [2800000, 10574161, 13374161, 9879647, 23253808]
        # 区分と「－」の額が同じ行
        assert funds["福岡県県営林造成事業振興基金"]["holdings"] == {"有価証券": [0, 0, 0, 0, 0]}
        # 縦書きの「動産」が前に付く区分
        assert funds["福岡県災害救助基金"]["holdings"]["備蓄物資"] == [58021, 1740, 59761, 0, 59761]
        # 運用基金: 土地（㎡）と運用状況の表は読まない
        land = funds["福岡県土地開発基金"]
        assert land["kind"] == "運用" and list(land["holdings"]) == ["現金"]
        assert fu.check_rows("R6", funds) == []

    def test_shifted_digits(self):
        # H25 のフォント: 「0」→「㻜」、「,」→「㻘」（U+3EAC ずれ）
        assert fu.fix_shifted("㻝㻘㻜㻝㻥") == "1,019"


class TestOcr:
    def test_units_and_notes_mixed_into_lines(self):
        # OCR は単位の行・括弧の注記を区分や額の行に混ぜ、「(」を「C」「1」と読む（H27・H28）
        assert fu.label_of(fu.clean_ocr_line("有   価   証   券   千円   1   1,800,000)千円   千円   千円   千円")) == "有価証券"
        line = fu.clean_ocr_line("動   產   備   蓄   物   資   50,624   千円   C   ▲ 2,838)千円   1,488   52,112   千円   ▲ 9,257   千円   42,855   千円")
        assert fu.numbers(line.split("資", 1)[1]) == [50624, 1488, 52112, -9257, 42855]
        assert fu.label_of("般   会   計   貸   付   金") == "一般会計貸付金"  # 「一」を落とす

    def test_fund_with_no_figures(self):
        # OCR は「－」を読まない: 区分の行だけの基金は、原本で全部「－」と確かめた年度・基金（NO_FIGURES_CONFIRMED）だけ 0 にして印を付ける
        txt = "資金を積み立てるために設置されたもの\n(4)   福岡県県営林造成事業振興基金\n有   価   証   券\n現   金\n"
        funds = fu.parse(txt, ocr=True)
        assert funds["福岡県県営林造成事業振興基金"]["holdings"] == {}  # parse では 0 にしない
        assert fu.fill_no_figures("H28", funds) == []
        f = funds["福岡県県営林造成事業振興基金"]
        assert f["no_figures"] and f["holdings"]["現金"] == [0, 0, 0, 0, 0]
        # 表にない年度（額の行を丸ごと読み落としたのと区別できない）は 0 にせず、検算で FAIL
        funds = fu.parse(txt, ocr=True)
        assert len(fu.fill_no_figures("H24", funds)) == 1
        assert any("区分の行がない" in x for x in fu.check_rows("H24", funds))

    def test_label_without_figures_fails(self):
        # 区分の名前を読んだのに額が入らなかった区分（「現金」の後の額の行が5つに足りない）を黙って落とさない
        txt = ("資金を積み立てるために設置されたもの\n(1)   福岡県財政調整基金\n有   価   証   券\n0   0   0   0   0\n"
               "現   金\n0   0\n(2)   福岡県減債基金\n現   金\n1   0   1   0   1\n")
        funds = fu.parse(txt)
        assert list(funds["福岡県財政調整基金"]["holdings"]) == ["有価証券"]
        assert any("現金" in x and "額の行がない" in x for x in fu.check_rows("R6", funds))
        assert fu.check_rows("R6", {"福岡県減債基金": funds["福岡県減債基金"]}) == []
        # 同じ区分が2度出て、後の区分の額が読めない（先の区分には額がある）: 後の区分も見逃さない
        txt = ("資金を積み立てるために設置されたもの\n(1)   福岡県財政調整基金\n現   金\n0   0   0   0   0\n"
               "現   金\n0   0\n")
        funds = fu.parse(txt)
        assert any("現金" in x and "額の行がない" in x for x in fu.check_rows("R6", funds))
        # 次の区分が「区分と額が同じ行」でも、前の区分の読めない額を見逃さない
        txt = ("資金を積み立てるために設置されたもの\n(1)   福岡県財政調整基金\n有   価   証   券\n0   0   0   0   0\n"
               "現   金\n0   0\n一   般   会   計   貸   付   金      0   0   0   0   0\n")
        funds = fu.parse(txt)
        assert list(funds["福岡県財政調整基金"]["holdings"]) == ["有価証券", "一般会計貸付金"]
        assert any("現金" in x and "額の行がない" in x for x in fu.check_rows("R6", funds))

    def test_signs_fixed_only_by_arithmetic(self):
        funds = {"a": {"holdings": {"現金": [100, 20, 80, 5, 75], "有価証券": [100, 20, 130, 0, 130]}}}
        fixed = fu.fix_signs(funds)
        assert funds["a"]["holdings"]["現金"] == [100, -20, 80, -5, 75] and len(fixed) == 2
        # どちらの符号でも合わない行は直さない（検算で FAIL にする）
        assert funds["a"]["holdings"]["有価証券"] == [100, 20, 130, 0, 130]

    def test_triangle_read_as_seven(self):
        # OCR が「▲」を独立した「7」と読む（H29 減債基金の現金）。「▲」に戻して5つの額になれば使い、記録する
        txt = ("資金を積み立てるために設置されたもの\n(2)   福岡県減債基金\n現   金\n"
               "83,224,249   7   29,207,769   54,016,480   16,836,969   70,853,449\n")
        f = fu.parse(txt, ocr=True)["福岡県減債基金"]
        assert f["holdings"]["現金"] == [83224249, -29207769, 54016480, 16836969, 70853449] and f["ocr_fixed"]
        # テキストの年度では OCR の直しをしない（読めない行として FAIL）
        assert "現金" not in fu.parse(txt)["福岡県減債基金"]["holdings"]
        # 読み替えは1か所ずつ試し、検算の成り立つ1通りだけ（本当の額の 7 は変えない）
        assert fu.seven_as_triangle("100   7   7   93   0   93") == [100, -7, 93, 0, 93]
        assert fu.seven_as_triangle("107   7   100   7   107") is None
        # 行の頭の「7」も試す。ほかの ▲ の読み落としは後の fix_signs が直すので、符号を変えて成り立てば使う
        assert fu.seven_as_triangle("7   100   0   100") is None  # 5つの額にならない
        assert fu.seven_as_triangle("100   7   5   95   3   98") == [100, -5, 95, 3, 98]

    def test_h24_ocr_shapes(self):
        # 見出しの番号の後のごみ（「(8)   1   福岡県…」）・注記を挟んで割れた区分名（「現 ▲52,639)」「金」）・0 を1つ落とした行
        txt = ("資金を積み立てるために設置されたもの\n(7) 福岡県地域づくり基金\n有   価   証   券\n0   0   0   0\n"
               "(8)   1   福岡県環境保全基金   ▲は減を示す。\n現   ▲ 52,639)\n金\n466,782   1,541,245   2,008,027   ▲ 106,438   1,901,589\n")
        funds = fu.parse(txt, ocr=True)
        assert funds["福岡県地域づくり基金"]["holdings"] == {"有価証券": [0, 0, 0, 0, 0]}
        assert funds["福岡県環境保全基金"]["holdings"]["現金"] == [466782, 1541245, 2008027, -106438, 1901589]
        assert fu.check_rows("H24", funds) == []

    def test_unreadable_value_row_fails(self):
        # 区分の後の額の行が読めない（コンマを「.」と読んだ）ときは、区分を黙って落とさず FAIL にする
        txt = "資金を積み立てるために設置されたもの\n(1)   福岡県財政調整基金\n現   金\n41.876   0   41,876   0   41,876\n"
        funds = fu.parse(txt)
        assert any("額として読めない" in x for x in fu.check_rows("R4", funds))
        # 左に区切りのない数（「1234,567」）は途中から読まない
        assert fu.numbers("1234,567   0   1,234,567   0   1,234,567") is None

    def test_names_snapped_to_text_years(self):
        known = {"福岡県減債基金", "福岡県アンビシャス外国留学支援基金", "福岡県高齢者等保健福祉基金"}
        funds = {"福岡県减债基金": {}, "福岡県アンビシヤス外国留学支援基金": {}, "福岡県架空基金": {}}
        out, log, fails = fu.canonical_names("H28", funds, known)
        assert set(out) == {"福岡県減債基金", "福岡県アンビシャス外国留学支援基金", "福岡県架空基金"}
        assert len(log) == 2 and len(fails) == 1 and "架空" in fails[0]
        # 字形の表・確かめた名前の表にない崩れは、似ていても寄せない（別の基金かもしれない）。似た名前は FAIL に候補として書く
        out, log, fails = fu.canonical_names("H28", {"福岡県高齢者等保険福祉基金": {}}, known)
        assert list(out) == ["福岡県高齢者等保険福祉基金"] and log == []
        assert len(fails) == 1 and "福岡県高齢者等保健福祉基金" in fails[0]


def test_short_name_keeps_ken_ei_ken_ritsu():
    ef = load("export_funds.py", "export_funds")
    assert ef.short("福岡県財政調整基金") == "財政調整基金"
    assert ef.short("福岡県営住宅敷金積立基金") == "県営住宅敷金積立基金"
    assert ef.short("福岡県立美術館美術品取得基金") == "県立美術館美術品取得基金"
    assert ef.short("福岡県県営林造成事業振興基金") == "県営林造成事業振興基金"


class TestChain:
    def test_chain_and_rename(self):
        prev = {"福岡県こども育成基金": {"holdings": {"現金": [0, 0, 41876, 0, 41876]}}}
        cur = {"福岡県出産・子育て安心基金": {"holdings": {"現金": [41876, 0, 41876, 0, 41876]}}}
        assert fu.check_chain("R4", prev, "R5", cur) == []
        cur["福岡県出産・子育て安心基金"]["holdings"]["現金"][0] = 41875
        assert len(fu.check_chain("R4", prev, "R5", cur)) == 2  # 区分ごとと合計の両方

    def test_chain_catches_dropped_row(self):
        # 後の年度で区分の行が落ちた（OCR）: 区分ごとの比較では気づけないので、合計で比べる
        prev = {"福岡県減債基金": {"holdings": {"有価証券": [0, 0, 100, 0, 100], "現金": [0, 0, 50, 0, 50]}}}
        cur = {"福岡県減債基金": {"holdings": {"有価証券": [100, 0, 100, 0, 100]}}}
        assert any("合計" in x for x in fu.check_chain("H28", prev, "H29", cur))


def test_export_year_label_and_gaps(tmp_path):
    import json
    ef = load("export_funds.py", "export_funds")
    assert ef.year_label(2019) == "令和元年度" and ef.year_label(2024) == "令和6年度" and ef.year_label(2017) == "平成29年度"
    # H25（2013）にあり H27（2015）にない、残高のある基金: 2014 年度末の額が分からないので、警告して notes に書く
    h = lambda end: {"no": 1, "kind": "積立", "holdings": {"現金": [end, 0, end, 0, end]}}  # noqa: E731
    data = {"years": {"H25": {"福岡県甲基金": h(5), "福岡県乙基金": h(7)}, "H27": {"福岡県甲基金": h(5)}},
            "ocr_years": [], "signs_fixed": {}, "names_fixed": {}}
    (tmp_path / "funds.json").write_text(json.dumps({**data, "fails": []}, ensure_ascii=False), encoding="utf-8")
    out, lines = ef.build(str(tmp_path), 2015)
    assert any("乙基金" in x for x in lines) and any("乙基金" in n for n in out["notes"])
    assert out["statements"][0]["source"] == "h25-zaisan"
    # 抽出の検算が通っていない funds.json・fails のない古い funds.json は、決算のファイルに書かずに止める
    import pytest
    for bad in ({**data, "fails": ["H27 甲基金: 前年度末 + 増減 ≠ 年度末"]}, data):
        (tmp_path / "funds.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(SystemExit):
            ef.build(str(tmp_path), 2015)


def test_ocr_done_marker(tmp_path):
    # ocr_lines.py は範囲のページがそろったときだけ完了の印を書く（途中で止まった OCR を抽出に渡さない）
    import json
    import pytest
    ol = load("ocr/ocr_lines.py", "ocr_lines")
    (tmp_path / "p0001.txt").write_text("a", encoding="utf-8")
    with pytest.raises(SystemExit):
        ol.write_done(str(tmp_path), "x.pdf", 1, 2)
    (tmp_path / "p0002.txt").write_text("b", encoding="utf-8")
    ol.write_done(str(tmp_path), "x.pdf", 1, 2)
    assert json.loads((tmp_path / "done.json").read_text(encoding="utf-8")) == {"pdf": "x.pdf", "pages": [1, 2]}
    # OCR を始めるときに前の印を消す（範囲を広げてやり直し、途中で止まったときに古い範囲で抽出が進まないよう）。
    # 印がなければ抽出は止まる
    ol.invalidate_done(str(tmp_path))
    assert not (tmp_path / "done.json").exists()
    import sys
    fu_main = load("extract_funds.py", "extract_funds_main")
    old = sys.argv
    sys.argv = ["extract_funds.py", f"H27={tmp_path}"]
    try:
        with pytest.raises(SystemExit, match="done.json"):
            fu_main.main()
    finally:
        sys.argv = old
