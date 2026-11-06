"""福岡県の決算書類（テキスト PDF）を読むための共通部品。

pdftotext -layout の出力を前提に、「番号 名称 数値…」の表の行を組み立てる。
名称の長い科目は折り返されるので、R6 で確認した2通りの形に対応する:
  A) 上の行「小規模企業者等設備導入」/ 番号付きの行「1資金貸付事業 数値…」/ 下の行「特別会計繰入金」
  B) 上の行「住宅管理」/ 番号だけの行「2」/ 数値の行「特別会計繰入金 数値…」
過誤納金（内数）がある歳入の科目は、収入済額が次の行に単独で出て、上の行に「(過誤納金)」が出る。
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

NUM = r"▲?\s?[\d,]+"
DATA_RE = re.compile(rf"^(?P<indent>\s*)(?P<label>.*?)\s+(?P<nums>(?:{NUM}\s+)*{NUM})\s*$")
PAREN_RE = re.compile(r"\s*\(([\d,]+)\)\s*")


def to_int(s: str) -> int:
    s = s.replace(" ", "").replace(",", "")
    return -int(s[1:]) if s.startswith("▲") else int(s)


def flat(s: str) -> str:
    return re.sub(r"\s", "", s)


def pdftext(pdf: str, page: int) -> str:
    return subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", "-f", str(page), "-l", str(page), pdf, "-"],
                          capture_output=True, text=True, check=True).stdout


def page_count(pdf: str) -> int:
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", info).group(1))


def printed_page(text: str) -> int | None:
    """ページ上の印字ページ番号（「-53-」など）。"""
    m = re.search(r"^\s*[-‑―]\s?(\d+)\s?[-‑―]\s*$", text, re.M)
    return int(m.group(1)) if m else None


@dataclass
class Row:
    indent: int
    no: int | None
    name: str
    nums: list[int]
    line_index: int
    extra: dict = field(default_factory=dict)


# 備考は行の右端。本体は「最後に数字が来て、2文字以上の空白の後に数字以外で始まる文字列が続く」位置まで（貪欲）。
# 行頭の目番号の直後（「2    賦課徴収費 …」）を備考と取り違えないよう、非貪欲にはしない。
NOTE_RE = re.compile(r"^(?P<body>.*[\d,])\s{2,}(?P<note>[^\d\s▲,(（].*)$")


def split_note(line: str) -> tuple[str, str | None]:
    """数値の後ろに続く備考欄（例「予備費補充 3,280」「流用」）を切り離す。"""
    m = NOTE_RE.match(line)
    if m and re.search(r"[\d,]{3,}\s*$", m.group("body")):
        return m.group("body"), re.sub(r"\s+", " ", m.group("note")).strip()
    return line, None


def assemble_rows(lines: list[str], want: int, *, split_income_col: int | None = None,
                  skipped: list[str] | None = None, label: str = "",
                  strip_notes: bool = False) -> list[tuple[str, Row | str]]:
    """lines（見出しを除いた非空行）から表の行を組み立てる。

    want: 数値列の数。split_income_col: 過誤納金で次の行に出る列の位置（歳入の収入済額 = 2）。
    戻り値: ("row", Row) と ("text", 行) の列（呼び出し側が見出しなどを解釈できるよう、使わなかった行も返す）。
    """
    out: list[tuple[str, Row | str]] = []
    buf: list[str] = []
    pending_no: tuple[int, int] | None = None
    expect_below: Row | None = None
    consumed: set[int] = set()
    for i, line in enumerate(lines):
        if i in consumed:
            continue
        if re.fullmatch(r"\s*\d+\s*", line):
            pending_no = (int(line), len(line) - len(line.lstrip()))
            expect_below = None
            continue
        note = None
        if strip_notes:
            line, note = split_note(line)
        # C) 名前が番号行をはさんで上下に分かれ、数値だけの行が後に来る形（R6 財政調整基金特別会計繰出金など）
        only_nums = re.fullmatch(rf"\s*((?:{NUM}\s+)*{NUM})\s*", line)
        if only_nums and pending_no is not None and len(re.findall(NUM, only_nums.group(1))) == want:
            line = " " * pending_no[1] + "\x01 " + only_nums.group(1)
        m = DATA_RE.match(line)
        nums = re.findall(NUM, m.group("nums")) if m else []
        is_data = m is not None and m.group("label").strip() != "" and len(nums) in (want, want - 1)
        if not is_data:
            if PAREN_RE.fullmatch(line):
                continue
            # D) 名前の前半の行 / 「6 事務費」（番号＋名前の後半、数値なし）/ 数値だけの行（R6 都市計画開発行為許可事務費）
            md = re.match(r"^(\s*)(\d+)\s+(\D.*)$", line)
            if md and not re.search(r"\d{3}", md.group(3)) and expect_below is None:
                pending_no = (int(md.group(2)), len(md.group(1)))
                buf.append(" " * (len(md.group(1)) + 20) + md.group(3))
                out.append(("text", line))
                continue
            if expect_below is not None and len(line) - len(line.lstrip()) > expect_below.indent:
                expect_below.name += flat(line)
                expect_below = None
            else:
                buf.append(line)
                out.append(("text", line))
            continue
        extra: dict = {"備考": note} if note else {}
        if len(nums) == want - 1:
            if split_income_col is None:
                buf.append(line)
                out.append(("text", line))
                continue
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            prv = lines[i - 1] if i > 0 else ""
            mn = re.fullmatch(rf"\s*({NUM})\s*", nxt)
            if not mn:
                if skipped is not None:
                    skipped.append(f"{label}: 列数 {len(nums)}（想定 {want}）: {line.strip()[:120]}")
                continue
            nums.insert(split_income_col, mn.group(1))
            consumed.add(i + 1)
            mp = PAREN_RE.fullmatch(prv)
            if mp:
                extra["過誤納金（内数）"] = to_int(mp.group(1))
        lab = m.group("label")
        mnum = re.match(r"^\s*(\d+)\s*(.*)$", lab)
        # 名前の断片は、直前の数値行より後で、字下げが番号の位置より深いものだけを使う
        no_indent = len(m.group("indent")) if mnum else (pending_no[1] if pending_no else len(m.group("indent")))
        frags = [b for b in buf if len(b) - len(b.lstrip()) > no_indent]
        if mnum:
            row = Row(len(m.group("indent")), int(mnum.group(1)), "".join(flat(b) for b in frags) + flat(mnum.group(2)),
                      [to_int(x) for x in nums], i, extra)
            expect_below = row if frags else None
        elif pending_no is not None:
            row = Row(pending_no[1], pending_no[0], "".join(flat(b) for b in frags) + flat(lab).replace("\x01", ""),
                      [to_int(x) for x in nums], i, extra)
            expect_below = None
        else:
            # 番号のない数値行（「計」など）
            row = Row(len(m.group("indent")), None, flat(lab), [to_int(x) for x in nums], i, extra)
            expect_below = None
        buf, pending_no = [], None
        out.append(("row", row))
    return out
