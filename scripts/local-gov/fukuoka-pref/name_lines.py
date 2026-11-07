"""行に分かれて印字された名前をつなぐ（テキスト PDF の表で、番号と金額の行を挟んで名前が上下に分かれる書き方）。

例（R8 予算書の本体）:
    県 営 埠 頭 施 設 整 備      ← 上の行（名前の前半）
    1                8,044,889  ← 番号と金額の行（名前なし）
    運 営 事 業 費              ← 下の行（名前の後半）
例（R8 公営企業会計の予算実施計画）:
    支払利息及び                ← 上の行
    1                29,777     ← 番号と金額の行
    企業債取扱諸費              ← 下の行

番号と金額は名前の縦の真ん中に印字されるので、上の行の数と下の行の数は同じ（上が2行なら下も2行）。
上の行がなく、番号と金額の行の名前が空のときは、下の行を1行足す。

使い方（表を上から1行ずつ読む）:
    j = NameJoiner(prepend_to_named=False)
    ページの始まりで:                         j.reset()
    番号・金額のない行で名前の断片が読めたら: j.name_only(断片)
    番号と金額の行では:                       name = j.entry_name(行の名前) → 記録を作ったら j.opened(記録)
記録は dict で、"name" を書き換える（下の行が来たときに後半を足す）。
"""


class NameJoiner:
    def __init__(self, prepend_to_named: bool):
        """prepend_to_named: 番号と金額の行にも名前があるとき、上の行の名前を前に付け足すか。
        公営企業の予算実施計画は「流域下水道／1 管理費負担金 …」のように付け足す書き方がある（True）。
        予算書の本体は、上の行のかけら（ページ番号など）が前に付く誤りを防ぐため、空のときだけ使う（False）。"""
        self.prepend_to_named = prepend_to_named
        self.reset()

    def reset(self) -> None:
        """ページ・会計の始まりで呼ぶ。前のページの末尾のかけらを次のページの名前に付けないため。"""
        self.upper: list[str] = []   # 上の行の名前（次の記録の名前の前半。複数行ならつなぐ）
        self.open = None             # 下の行を待っている記録
        self.lower_left = 0          # その記録に足す下の行の残りの数
        self._n_upper = 0            # 直前の entry_name で使った上の行の数
        self._continues = False

    def name_only(self, part: str) -> None:
        """番号・金額のない行の名前の断片。下の行を待っている記録があればそれに足し、なければ上の行として持つ。"""
        if not part:
            return
        if self.open is not None and self.lower_left > 0:
            self.open["name"] += part
            self.lower_left -= 1
            if self.lower_left == 0:
                self.open = None
        else:
            self.upper.append(part)

    def entry_name(self, name: str) -> str:
        """番号と金額の行の名前から、記録に使う名前を返す。"""
        self._continues = False
        self._n_upper = 0
        if self.upper and (not name or self.prepend_to_named):
            self._continues = not name   # 番号の行に名前がなければ、下の行が続く
            self._n_upper = len(self.upper)
            name = "".join(self.upper) + name
        self.upper = []
        return name

    def opened(self, entry) -> None:
        """作った記録を渡す。下の行が続くときは、上の行と同じ数だけ次の名前の断片をこの記録に足す。"""
        self.open, self.lower_left = None, 0
        if entry is None:
            return
        if self._continues:
            self.open, self.lower_left = entry, self._n_upper
        elif not entry["name"]:
            self.open, self.lower_left = entry, 1
