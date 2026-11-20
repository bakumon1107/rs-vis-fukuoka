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
        # OCR は「－」を読まない: 区分の行だけの基金は 0 として持ち、印を付ける
        txt = "資金を積み立てるために設置されたもの\n(4)   福岡県県営林造成事業振興基金\n有   価   証   券\n現   金\n"
        f = fu.parse(txt)["福岡県県営林造成事業振興基金"]
        assert f["no_figures"] and f["holdings"]["現金"] == [0, 0, 0, 0, 0]

    def test_signs_fixed_only_by_arithmetic(self):
        funds = {"a": {"holdings": {"現金": [100, 20, 80, 5, 75], "有価証券": [100, 20, 130, 0, 130]}}}
        fixed = fu.fix_signs(funds)
        assert funds["a"]["holdings"]["現金"] == [100, -20, 80, -5, 75] and len(fixed) == 2
        # どちらの符号でも合わない行は直さない（検算で FAIL にする）
        assert funds["a"]["holdings"]["有価証券"] == [100, 20, 130, 0, 130]

    def test_names_snapped_to_text_years(self):
        known = {"福岡県減債基金", "福岡県アンビシャス外国留学支援基金", "福岡県高齢者等保健福祉基金"}
        funds = {"福岡県减债基金": {}, "福岡県アンビシヤス外国留学支援基金": {}, "福岡県架空基金": {}}
        out, log, fails = fu.canonical_names("H28", funds, known)
        assert set(out) == {"福岡県減債基金", "福岡県アンビシャス外国留学支援基金", "福岡県架空基金"}
        assert len(log) == 2 and len(fails) == 1 and "架空" in fails[0]


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
        assert len(fu.check_chain("R4", prev, "R5", cur)) == 1
