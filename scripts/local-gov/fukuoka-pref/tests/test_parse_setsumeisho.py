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
