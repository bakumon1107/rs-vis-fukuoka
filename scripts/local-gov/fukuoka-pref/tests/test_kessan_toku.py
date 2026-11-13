"""特別会計の決算の抽出（extract_kessan_toku.py）の単体テスト。R6 の決算概要説明書（272595）7章で実際に起きた形を再現する。"""
from conftest import load

kt = load("extract_kessan_toku.py", "extract_kessan_toku")

SPLIT = 30  # 款の欄と項の欄の境目（本体では見出しの「項」の位置から決める。下のテストの行は款の欄が 28 字目まで・項の番号が 33 字目から）


def _blk(*rows):
    return [list(rows)]


class TestSummary:
    def test_kan_name_on_middle_line(self):
        # R6 国民健康保険 p211: 項が3つある款は、款の名前が真ん中の項の行に出る（1項の区画には款の欄がない）
        blocks = [
            ["                                 1   総   務       管       理       費             83,591,271"],
            ["1    総       務           費       2   運   営   協       議       会   費                404,670"],
            ["                                 3   共 同 運 営 事 業 費                              2,579,000"],
            ["2    保険給付費等交付金                   1   保険給付費等交付金                           363,585,540,870"],
            ["                             計                                           363,672,116,191"],
        ]
        fails = []
        out, total = kt.parse_summary(blocks, SPLIT, fails, "t")
        assert fails == []
        assert [(x["款"], x["款名"], x["項"], x["決算額"]) for x in out] == [
            (1, "総務費", 1, 83591271), (1, "総務費", 2, 404670), (1, "総務費", 3, 2579000),
            (2, "保険給付費等交付金", 1, 363585540870)]
        assert total == 363672116191

    def test_reserve_fund_zero(self):
        # 予備費は決算額 0（R6 国民健康保険 11款・住宅管理 3款）。0 も決算額として読む
        blocks = [["11   予       備           費       1   予           備               費                     0"]]
        fails = []
        out, _ = kt.parse_summary(blocks, SPLIT, fails, "t")
        assert fails == [] and out[0]["決算額"] == 0 and out[0]["款"] == 11

    def test_wrapped_names(self):
        # R6 母子父子寡婦 p221: 款・項の名前が上下の行に折り返し、番号と決算額は別の行
        blocks = [[
            "     母子父子寡婦福祉資金                               母子父子寡婦福祉資金",
            " 1",
            "     貸 付  事 業 費",
            "                                         1",
            "                                              貸 付  事 業 費",
            "                                                                                      313,995,011",
        ]]
        fails = []
        out, _ = kt.parse_summary(blocks, SPLIT, fails, "t")
        assert fails == []
        assert out[0]["款名"] == "母子父子寡婦福祉資金貸付事業費" and out[0]["決算額"] == 313995011


class TestRevenue:
    def test_rows_and_total(self):
        lines = [
            "1   財   産           収       入              58,589,000        58,588,998            58,588,998           0           0           ▲2   100.00",
            "2   繰           入           金           24,011,036,000   24,011,036,000       24,011,036,000            0           0            0   100.00",
            "            計                           24,069,625,000   24,069,624,998       24,069,624,998            0           0           ▲2   100.00",
        ]
        fails = []
        rows, total = kt.parse_revenue(lines, fails, "t")
        assert fails == []
        assert [(r["no"], r["name"], r["収入済額"], r["増減額"]) for r in rows] == [
            (1, "財産収入", 58588998, -2), (2, "繰入金", 24011036000, 0)]
        assert total["予算現額"] == 24069625000


class TestExplain:
    def test_entries_and_continuation(self):
        lines = [
            "     1       一       般       管       理       費    事務費 （3,694千円）",
            "     1       社 会 教 育 総 務 費                人件費 社会教育活動促進費",
            "                                              社会教育推進費",
        ]
        out = kt.parse_explain(lines, 30)
        assert out[1].endswith("社会教育推進費")


class TestVerify:
    def _acc(self, choutei):
        return {"会計": "福岡県住宅管理特別会計",
                "歳入": [{"no": 1, "name": "県営住宅管理費収入", "予算現額": 100, "調定額": choutei, "収入済額": 90,
                         "不納欠損額": 5, "収入未済額": 10, "増減額": -10}],
                "歳入の計": {"予算現額": 100, "調定額": choutei, "収入済額": 90, "不納欠損額": 5, "収入未済額": 10, "増減額": -10},
                "款項": [{"款": 1, "款名": "x", "項": 1, "項名": "x", "決算額": 90}], "款項の計": 90,
                "項": [{"款": 1, "項": 1, "項名": "x", "目": [{"no": 1, "name": "x", "予算現額": 100, "支出済額": 90,
                                                          "翌年度繰越額": 0, "不用額": 10}], "計": None}]}

    def test_overpayment_is_warning(self):
        # 収入済額 + 不納欠損額 + 収入未済額 が調定額より多い分は過誤納金（R6 住宅管理 1款 177,125 円）。FAIL にしない
        acc = self._acc(103)
        n = kt.verify([acc], [], [{"合計": False, "予算現額": 100, "歳入決算額": 90, "歳出決算額": 90},
                                  {"合計": True, "予算現額": 100, "歳入決算額": 90, "歳出決算額": 90}])
        assert n == 0 and acc["歳入"][0]["過誤納金"] == 2

    def test_choutei_too_large_fails(self):
        acc = self._acc(110)
        assert kt.verify([acc], [], [{"合計": False, "予算現額": 100, "歳入決算額": 90, "歳出決算額": 90},
                                     {"合計": True, "予算現額": 100, "歳入決算額": 90, "歳出決算額": 90}]) == 1
