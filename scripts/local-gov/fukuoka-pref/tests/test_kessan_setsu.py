"""決算の節の抽出（extract_kessan_setsu.py）の単体テスト。特別会計のページの読み方（R6 の事項別明細書 272615 の 262ページ〜）。"""
from conftest import load

ks = load("extract_kessan_setsu.py", "extract_kessan_setsu")


class _Page:
    def __init__(self, chars):
        self.chars = chars


def _ch(text, x0, x1, top, color=(0.0,)):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "non_stroking_color": color}


class TestDigitOf:
    def test_cid_digits(self):
        # 特別会計のページでは一部の数字が文字コードなしで描かれる。(cid:N) は N − 19（R6 公債管理の支出済額で確かめた）
        assert [ks.digit_of(f"(cid:{n})") for n in (19, 20, 22, 26, 28)] == ["0", "1", "3", "7", "9"]
        assert ks.digit_of("5") == "5"
        # 範囲の外の (cid:N) は数字ではない（(cid:15) は桁区切りの「,」など、(cid:5754) は漢字）
        assert ks.digit_of("(cid:15)") is None and ks.digit_of("(cid:5754)") is None


class TestSpecialRows:
    def test_shift_and_values(self):
        # 支出済額の列の右端が 583.2 なら特別会計の並び（ずれ 0）。節の番号・金額の (cid:N) を数字に直して読む
        chars = [
            _ch(" ", 460.0, 465.0, 166), _ch("(cid:20)", 465.9, 470.0, 166), _ch("(cid:20)", 470.0, 474.0, 166),
            _ch("需", 474.0, 480.0, 166),
            _ch("(cid:26)", 522.6, 527.0, 166), _ch("8", 527.0, 531.0, 166), _ch("5", 531.0, 535.0, 166), _ch("4", 535.0, 545.6, 166),
            _ch("2", 560.1, 565.0, 166), _ch("(cid:22)", 565.0, 570.0, 166), _ch("0", 570.0, 583.2, 166),
            _ch("0", 600.0, 620.8, 166), _ch("0", 640.0, 658.3, 166), _ch("0", 680.0, 695.8, 166),
            _ch("(cid:20)", 712.8, 720.0, 166), _ch("0", 720.0, 733.3, 166),
        ]
        page = _Page(chars)
        assert ks.special_shift(page) == 0.0
        rows = [r for r in ks.rows_of(page, special=True) if r["支出済額"] is not None]
        assert len(rows) == 1
        r = rows[0]
        assert r["label"].startswith("11") and r["節の金額"] == 7854 and r["支出済額"] == 230 and r["不用額"] == 10

    def test_shift_counts_cid_digits(self):
        # 支出済額の右端の数字がすべて文字コードなし（(cid:N)）でも、特別会計の並びと見分ける（ずれ 9.7）
        page = _Page([_ch("(cid:20)", 588.0, 592.9, 166), _ch("(cid:22)", 588.0, 592.9, 180)])
        assert ks.special_shift(page) == 9.7

    def test_general_page_is_not_special(self):
        # 一般会計の並び（支出済額の右端 501.9）では特別会計の読み方をしない
        page = _Page([_ch("9", 495.0, 501.9, 166), _ch("1", 640.0, 652.0, 166)])
        assert ks.special_shift(page) is None


def _group(page, acc, budget, spent):
    return {"pdf_page": page, "会計": acc, "節": [{"no": 1, "節の金額": budget, "支出済額": spent}]}


class TestRevenuePagesExcluded:
    # 歳入と歳出に、予算現額（節の金額）と支出済額が同じ額の区画がある会計（特別会計は会計ごとに歳入→歳出の順）
    PAGES = [
        "款項目予算現額調定額収入済額不納欠損額収入未済額",  # p1 歳入
        "款項目予算現額支出済額翌年度繰越額不用額",  # p2 歳出
        "歳入歳出決算総括表収入済額支出済額",  # p3 両方の見出し（総括）は歳入にしない
    ]

    def test_revenue_page_numbers(self):
        assert ks.revenue_page_numbers(self.PAGES) == {1}

    def test_expense_block_is_chosen_over_same_amount_revenue_block(self):
        revenue = _group(1, "A", 1000, 900)
        expense = _group(2, "A", 1000, 900)
        groups = [revenue, expense, {"pdf_page": 2, "節": []}]
        cand = ks.expense_candidates(groups, ks.revenue_page_numbers(self.PAGES))
        # 歳入のページの区画と節のない区画は候補にならない
        assert cand == [expense]
        # 照合は歳出の区画を選ぶ（歳入の区画を候補から外さないと、先にある歳入の区画が同じ額で選ばれる）
        assert ks.find_segment(cand, 0, len(cand), "A", 1000, 900) == (0, 1)
        assert cand[0] is expense
        assert ks.find_segment([revenue, expense], 0, 2, "A", 1000, 900) == (0, 1)  # 外さなかった場合（歳入を拾う）

    def test_find_segment_joins_blocks_of_the_same_account_only(self):
        a1, a2, b1 = _group(2, "A", 600, 500), _group(3, "A", 400, 400), _group(4, "B", 1000, 900)
        # ページをまたぐ目は連続する区画をつないで照合する
        assert ks.find_segment([a1, a2, b1], 0, 3, "A", 1000, 900) == (0, 2)
        # 別の会計の区画は、額が同じでも選ばない
        assert ks.find_segment([b1], 0, 1, "A", 1000, 900) is None
