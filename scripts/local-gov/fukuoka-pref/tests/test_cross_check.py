"""2通りの読み取りの突き合わせ（ocr/cross_check.py）と多数決（ocr/vote.py）の単体テスト。"""
from conftest import load

cc = load("ocr/cross_check.py", "cross_check")
vote = load("ocr/vote.py", "vote")


def setsu(*pairs):
    return [{"no": no, "amount": a, "top": True} for no, a in pairs]


def moku(h, ss, **kw):
    m = {"本年度": h, "前年度": h, "比較": 0, "side": "歳入", "節": ss, "説明": [], "財源": {}, "会計": "一般会計",
         "款": 1, "項": [1, "x"], "目番号": 1, "目名": "x", "kind": "目"}
    m.update(kw)
    return m


class TestResolveSetsu:
    def test_add_missing_setsu_from_textlayer(self):
        # OCR が節26（5）を取りこぼし、文字層は節12を「186」と誤読（p179 保健環境研究所費。正しくは 179,186）。
        # 文字層から節26だけを足し、節12は OCR のまま（最小の変更で1通り）
        m = moku(8185583, setsu((12, 179186), (14, 8006392)))
        t = moku(8185583, setsu((12, 186), (14, 8006392), (26, 5)))
        new, notes = cc.resolve_setsu(m, t)
        assert sorted((s["no"], s["amount"]) for s in new) == [(12, 179186), (14, 8006392), (26, 5)]
        assert notes == ["節26 5 を文字層から足す"]

    def test_drop_unnumbered_extra_row(self):
        # OCR が細節を節と誤認した番号なしの行（p280 森林環境費の 799）
        m = moku(1000, setsu((1, 600), (None, 799), (2, 400)))
        t = moku(1000, setsu((1, 600), (2, 400)))
        new, notes = cc.resolve_setsu(m, t)
        assert sorted((s["no"], s["amount"]) for s in new) == [(1, 600), (2, 400)]

    def test_ambiguous_is_rejected(self):
        # 合う組み合わせが同じ変更数で2通りあるときは採用しない
        m = moku(100, setsu((1, 50), (2, 40)))
        t = moku(100, setsu((1, 60), (2, 50)))
        assert cc.resolve_setsu(m, t) is None

    def test_no_solution(self):
        m = moku(100, setsu((1, 10)))
        t = moku(100, setsu((1, 20)))
        assert cc.resolve_setsu(m, t) is None


class TestChecks:
    def test_revenue_checks(self):
        assert all(cc.checks_of(moku(10, setsu((1, 10)))).values())
        assert not cc.checks_of(moku(10, setsu((1, 9))))["D"]

    def test_no_setsu_column(self):
        # 予備費は節の欄が空（p419）。解釈の段階で「節なし」の印が付いたものは D を通す
        m = moku(200000, [], side="歳出", 説明なし=True, 財源={"一般財源": 200000}, 節なし=True)
        assert cc.checks_of(m)["D"]


class TestVote:
    def test_setsu_compared_as_amounts(self):
        # 節番号の読み違い（「8」→「80」）があっても、金額が同じなら同じ値として数える
        a = vote.values(moku(10, setsu((8, 7), (2, 3))))
        b = vote.values(moku(10, setsu((80, 7), (2, 3))))
        assert {k: v for k, v in a.items() if k.startswith("節")} == {k: v for k, v in b.items() if k.startswith("節")}

    def test_duplicate_amounts_counted(self):
        v = vote.values(moku(10, setsu((1, 5), (2, 5))))
        assert sorted(k for k in v if k.startswith("節")) == ["節 5#1", "節 5#2"]
