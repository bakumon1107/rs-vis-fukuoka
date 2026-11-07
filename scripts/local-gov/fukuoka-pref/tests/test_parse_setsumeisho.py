"""予算説明書の OCR 結果の解釈（ocr/parse_setsumeisho.py）の単体テスト。

どのテストも、実際に起きた読み取りの崩れ方（コメントに出典のページ）を小さな入力で再現している。
直したはずの崩れ方が、後のロジックの変更で再発しないことを確かめる。
"""
import pytest

from conftest import load

ps = load("ocr/parse_setsumeisho.py", "parse_setsumeisho")


def item(text, x0, y0, x1=None, y1=None):
    return {"text": text, "x0": x0, "y0": y0, "x1": x1 if x1 is not None else x0 + 20 * len(text),
            "y1": y1 if y1 is not None else y0 + 30}


class TestNormName:
    @pytest.mark.parametrize("text, want", [
        ("O管理事務費", "○管理事務費"),      # 先頭の事項の印が英字の O に
        ("0管理事務費", "○管理事務費"),      # 数字の 0 に
        ("〇管理事務費", "○管理事務費"),
        ("職員費10人", "職員費10人"),          # 名前の途中の 0 は数字のまま（「1○人」にしない。R8 で実例）
        ("ＦＯＦ事務所管理費負担金", "ＦＯＦ事務所管理費負担金"),  # 名前の途中の O は英字のまま
        ("0歳児保育事業費", "0歳児保育事業費"),  # 先頭の 0 でも、次が年齢の単位なら本当の数字
        ("0人材活躍・労働総務費", "○人材活躍・労働総務費"),  # 「人」で始まる名前の前の 0 は事項の印（R8 で実例）
        ("0次世代育成支援費", "○次世代育成支援費"),
    ])
    def test_norm_name(self, text, want):
        assert ps.norm_name(text) == want


class TestAmount:
    @pytest.mark.parametrize("text, want", [
        ("17,854,435", 17854435),
        ("17,854, 435", 17854435),   # PP-OCRv6 は数字の途中に空白を入れる（p131）
        ("△152,892", -152892),
        ("1", 1),
        ("l", 1),                    # 「1」が英字の l で返る
        ("I,000", 1000),
        ("2,444管理事務费", None),    # 隣の列とつながった文字列は金額ではない
        ("職員費", None),
    ])
    def test_amount(self, text, want):
        assert ps.amount(text) == want


class TestChooseKou:
    CANDS_KEN = [(1, "県民税"), (2, "事業税"), (3, "地方消費税"), (4, "不動産取得税"), (5, "県たばこ税"),
                 (6, "ゴルフ場利用税"), (7, "軽油引取税"), (8, "自動車税"), (9, "鉱区税")]

    def test_page_number_with_kanji_one_is_not_a_new_kou(self):
        # PP-OCRv6 はページ番号「-138-」の末尾を「一」と読む。残った「一」で項を進めていた（p146）
        assert ps.choose_kou("(単位：千円)-138一", [(1, "総務管理費"), (2, "企画費"), (3, "徴税費")], 2) is None

    def test_unit_and_page_number_only(self):
        assert ps.choose_kou("（单位：千四）-134-", [(1, "総務管理費"), (2, "企画費")], 1) is None

    def test_kou_char_dropped(self):
        # 「2項」の「項」が落ちる（p19「2事業税（单位：千四）」）
        assert ps.choose_kou("2事業税（单位：千四）", self.CANDS_KEN, 1) == (2, "事業税")

    def test_number_after_name(self):
        # 番号が名前の後ろに回る（p21「場利用税6」）
        assert ps.choose_kou("場利用税6（单位：千内）", self.CANDS_KEN, 5) == (6, "ゴルフ場利用税")

    def test_one_char_name_with_explicit_kou_number(self):
        # PP-OCRv6 で「狩10項」。名前が1文字しか残らなくても、「10項」が読めていれば新しい項（p23）
        cands = self.CANDS_KEN + [(10, "狩猟税"), (11, "産業廃棄物税")]
        assert ps.choose_kou("狩10項(単位：千円)", cands, 9) == (10, "狩猟税")

    def test_kou_char_misread(self):
        # 「項」が「頂」になる（p22）
        assert ps.choose_kou("8頂自動車税（单位：千网）", self.CANDS_KEN, 7) == (8, "自動車税")


class TestMokuName:
    def test_two_line_name_with_centered_number(self):
        # 目番号が2行の名前の間の高さに単独で印字される。番号ごと行にまとめると「指導費生活衛生」になった（p186）
        items = [item("2", 10, 52, 22, 72), item("生活衛生", 30, 30, 110, 55), item("指導費", 30, 68, 90, 93)]
        assert ps.moku_name(items) == (2, "生活衛生指導費")

    def test_number_attached(self):
        assert ps.moku_name([item("1一般管理費", 10, 30)]) == (1, "一般管理費")

    def test_no_number(self):
        assert ps.moku_name([item("恩給及び退職年金費", 10, 30)]) == (None, "恩給及び退職年金費")


class TestParseSetsu:
    def test_two_line_name_with_centered_number(self):
        # 名前が2行の節（「13 使用料及び／賃借料」）: 金額は2行の真ん中、番号も2行の間に単独で印字される。
        # 金額にいちばん近い1行だけを名前にしていたので、片方の行と番号を取りこぼした（歳入の節で多数。2026-11-06）
        labels = [item("使用料及び", 30, 100, 150, 130), item("13", 5, 118, 20, 142), item("賃借料", 30, 135, 120, 165)]
        amounts = [item("1,789", 400, 118, 480, 148)]
        got = ps.parse_setsu(labels, amounts, col_left=0)
        assert [(s["no"], s["label"], s["top"], s["amount"]) for s in got] == [(13, "使用料及び賃借料", True, 1789)]

    def test_lines_go_to_nearest_amount(self):
        labels = [item("1報", 30, 100, 90, 130), item("酬", 30, 135, 60, 165), item("2給料", 30, 200, 110, 230)]
        amounts = [item("1,000", 400, 118, 480, 148), item("2,000", 400, 200, 480, 230)]
        got = ps.parse_setsu(labels, amounts, col_left=0)
        assert [(s["no"], s["label"]) for s in got] == [(1, "報酬"), (2, "給料")]

    def test_far_line_of_unread_setsu_is_not_joined(self):
        # 金額の読めなかった次の節（「2 雑入」、約130px 下）の行を、前の節の名前につながない（281299 p75）
        labels = [item("1 貸付金償還金", 30, 330, 300, 371), item("2 雑", 30, 462, 120, 516), item("入", 200, 466, 230, 514)]
        got = ps.parse_setsu(labels, [item("6,177", 400, 334, 480, 376)], col_left=0)
        assert [(s["no"], s["label"]) for s in got] == [(1, "貸付金償還金")]

    def test_separator_line_splits_setsu(self):
        # 次の節（金額が読めなかった「5 小規模企業者…」）の1行目は、5行の名前の外側の行と同じくらい金額から離れるので、
        # 高さの差ではなく節の区切りの横線で分ける（281299 p83。区切り y=2160）
        labels = [item("雇用保険料", 30, 2044, 200, 2089), item("4", 5, 2074, 20, 2112), item("納付金", 30, 2088, 150, 2141),
                  item("小規模企業者", 30, 2160 + 2, 250, 2202), item("5", 5, 2215, 20, 2242)]
        hlines = [{"y": 2023, "x0": 0, "x1": 3000}, {"y": 2160, "x0": 0, "x1": 3000}, {"y": 2150, "x0": 100, "x1": 300}]
        seps = ps.setsu_separators(hlines, labels)
        assert seps == [2023, 2160]     # 欄の左端まで届かない線（細節の枠など）は区切りにしない
        got = ps.parse_setsu(labels, [item("21", 400, 2071, 440, 2110)], col_left=0, seps=seps)
        assert [(s["no"], s["label"]) for s in got] == [(4, "雇用保険料納付金")]

    def test_number_only_from_head_of_fragment(self):
        # 番号の枠がないとき、名前の中の数字（「人生100年」）を節番号に拾わず、名前からも消さない
        got = ps.parse_setsu([item("人生100年時代づくり交付金", 30, 100, 400, 130)], [item("14,000", 450, 100, 520, 130)],
                             col_left=0)
        assert [(s["no"], s["label"]) for s in got] == [(None, "人生100年時代づくり交付金")]
        # 断片の頭の番号は拾う（「13使用料及び」→ 13）
        got = ps.parse_setsu([item("13使用料及び", 30, 100, 200, 130), item("賃借料", 30, 135, 120, 165)],
                             [item("1,789", 400, 118, 480, 148)], col_left=0)
        assert [(s["no"], s["label"]) for s in got] == [(13, "使用料及び賃借料")]

    def test_digit_right_of_name_is_part_of_name(self):
        # 名前の1行目の右端の数字（地区の番号）は名前の一部。節番号は名前より左の数字（281299 p96「7 苅田港本港6地区…」）
        labels = [item("苅田港本港", 60, 100, 250, 130), item("6", 260, 100, 280, 130), item("7", 5, 140, 20, 170),
                  item("地区埠頭用地", 60, 140, 280, 170), item("整備事業債", 60, 180, 250, 210)]
        got = ps.parse_setsu(labels, [item("21,700", 400, 140, 480, 170)], col_left=0)
        assert [(s["no"], s["label"]) for s in got] == [(7, "苅田港本港6地区埠頭用地整備事業債")]

    def test_bracket_line_is_not_part_of_name(self):
        # 細節を囲む括弧の線が「L」「I」と読まれる（「L証紙収入」「I高等学校使用料」）
        got = ps.parse_setsu([item("L証紙収入", 50, 100)], [item("1", 400, 100, 420, 130)], col_left=0)
        assert got[0]["label"] == "証紙収入"


class TestTitleNames:
    def test_two_row_title_with_spaced_letters(self):
        # 見出しは2段（款・項）で、字間の広い名前は1字ずつ別の単語になる。OCR の返した順につなぐと
        # 「1款事務費1项事費務」と段・字の順が混ざった（281299 p13）
        words = [item("3歳出", 213, 324), item("務費", 799, 460), item("1款事", 373, 462), item("1项事", 463, 603),
                 item("費", 1151, 603), item("務", 924, 606), item("(单位：千円)", 2940, 649)]
        assert ps.title_names(ps.title_rows(words)) == ("事務費", "事務費")

    def test_kan_and_kou_names_differ(self):
        words = [item("2款国庫支出金", 370, 1143), item("国庫補助金", 654, 1285), item("1項", 463, 1288)]
        assert ps.title_names(ps.title_rows(words)) == ("国庫支出金", "国庫補助金")

    def test_page_number_and_unit_are_dropped(self):
        words = [item("-502-", 3156, 76), item("11款予", 336, 176), item("備費", 799, 172), item("1 项予", 453, 314),
                 item("備", 914, 322), item("費", 1130, 317), item("(単位：千円)", 2936, 358)]
        assert ps.title_names(ps.title_rows(words)) == ("予備費", "予備費")


class TestKaikeiTitle:
    @pytest.mark.parametrize("title", [
        "令和8年度福岡県財政調整基金特別会計歳入歳出予算事項別明細書1総括",
        "今和8年度福公管理特别会計入出予算事项别明細書1括",       # 崩れた見出し（281299 p7）
        "今和8年度福网小规模企業者等設備導入資金貨付事業特别会计入出予算事项别明細書括1",
    ])
    def test_matches(self, title):
        assert ps.KAIKEI_RE.search(title)

    def test_not_salary_table(self):
        assert not ps.KAIKEI_RE.search("給与費明細書般職（1）括（单位：千四）")


class TestExplanations:
    def test_amount_after_name(self):
        rows = [item("○管理事務費", 10, 10), item("2,960,581", 400, 10, 500, 40),
                item("○維持修繕費", 10, 50), item("4,890,339", 400, 50, 500, 80)]
        out, rest = ps.parse_explanations(rows)
        assert [(e["name"], e["amount"]) for e in out] == [("○管理事務費", 2960581), ("○維持修繕費", 4890339)]
        assert rest == ""

    def test_single_item_without_amount_is_left_as_rest(self):
        # 1事項で金額の記載がない（p180「○病院事業会計への負担金」）。目の額を当てるのは検算の段階
        out, rest = ps.parse_explanations([item("○病院事業会計への負担金", 10, 10)])
        assert out == [] and rest == "○病院事業会計への負担金"
