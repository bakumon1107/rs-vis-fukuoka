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


class TestNumbers:
    def test_to_int(self):
        assert kc.to_int("▲ 1,234") == -1234
        assert kc.to_int("2,296,925,549,451") == 2296925549451

    def test_printed_page(self):
        assert kc.printed_page("…\n   -53-   \n") == 53
        # 目次の「教育庁……186」の直後の全角の章番号を巻き込まない（全角数字は \\d に一致する実例）
        assert kc.printed_page("教育庁……186７") is None
