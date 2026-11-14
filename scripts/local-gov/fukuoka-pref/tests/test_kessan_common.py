"""決算書類（テキスト PDF）の行の組み立て（kessan_common.py）の単体テスト。"""
from conftest import load

kc = load("kessan_common.py", "kessan_common")


class TestSplitNote:
    def test_note_after_numbers(self):
        # 右端の備考欄（R6 決算の款項目別明細表）
        body, note = kc.split_note("   67,539,819   3,285,777    予備費補充　3,285,777 円")
        assert body.rstrip().endswith("3,285,777") and note.startswith("予備費補充")

    def test_number_after_moku_no_is_not_a_note(self):
        # 行頭の目番号の直後を備考と取り違えない（非貪欲マッチで起きた実例）
        line = "2    賦課徴収費     1,234,567    1,200,000"
        assert kc.split_note(line) == (line, None)

    def test_no_note(self):
        line = "1 議会費   3,034,708,000   2,929,992,078"
        assert kc.split_note(line) == (line, None)


class TestExplainReader:
    def test_two_tables_and_continuation(self):
        # R6 概要説明書の項の下の「説明」（教育費 6項 社会教育費。内容は折り返す）
        lines = [
            "（1） 決算の内容",
            "     目           目       の       名   称                    主                       な                         内                容",
            "     1       社 会 教 育 総 務 費                人件費 社会教育活動促進費 社会教育推進費 社会教育事業費補助金",
            "                                                 奨学事業助成費",
            "     3       文 化 財 保 護 費                  文化財管理費 文化財普及活動費",
            "（2） 不用額の内容",
            "     目           目       の       名   称                    主                       な                        内               容",
            "     1       社 会 教 育 総 務 費                社会教育推進費 （2,028千円）、人件費 （1,594千円）",
        ]
        r = kc.ExplainReader()
        for ln in lines:
            r.feed(ln, lambda _: False)
        out = r.result()
        assert out["決算の内容"][1].endswith("奨学事業助成費") and out["決算の内容"][3] == "文化財管理費 文化財普及活動費"
        assert out["不用額の内容"][1].startswith("社会教育推進費")

    def test_attach_strips_spilled_last_char(self):
        # 字間を空けた目の名前「積 立 金」の最後の字「金」が内容の欄にはみ出る（R6 財政調整基金特別会計）
        moku = [{"no": 1, "name": "積立金"}]
        kc.attach_explain(moku, {"決算の内容": {1: "金 基金積立金"}})
        assert moku[0]["決算の内容"] == "基金積立金"


class TestNumbers:
    def test_to_int(self):
        assert kc.to_int("▲ 1,234") == -1234
        assert kc.to_int("2,296,925,549,451") == 2296925549451

    def test_printed_page(self):
        assert kc.printed_page("…\n   -53-   \n") == 53
        # 目次の「教育庁……186」の直後の全角の章番号を巻き込まない（全角数字は \\d に一致する実例）
        assert kc.printed_page("教育庁……186７") is None
