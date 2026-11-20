"""福岡県「実質収支・財産に関する調書」（決算。テキスト PDF）の「4 基金」から、基金ごとの現在高を抽出・検証する。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_funds.py <年度>=<調書.pdf または OCR の結果のディレクトリ> [...] > funds.json
    年度は決算年度（例 R6=272596.pdf R5=238290.pdf）。画像だけの年度は ocr/ocr_lines.py の出力ディレクトリを渡す

構造（R6・R5・R2・H30・H25・H23 で確認。地方版の基金の設計 2章）:
    「○…資金を積み立てるために設置されたもの」（積立基金）と「○…定額の資金を運用するために設置されたもの」（運用基金）の下に、
    「（1） 福岡県財政調整基金」ごとの表。行は 区分（有価証券・現金・一般会計貸付金・貸付金・美術作品…）と、その下の行の
    5つの額: 前年度末現在高・決算年度中増減高・決算年度末現在高・出納整理期間中増高・出納閉鎖日現在高（千円。▲ は負）。
    「（ ）は前年度の出納整理期間中増高を内数で示す」の括弧の行・土地（㎡）・運用基金の「運用状況」の表は読まない。
検証（stderr。終了コード 1 = FAIL あり）:
    行ごとに 前年度末 + 増減 = 年度末、年度末 + 出納整理期間中増高 = 出納閉鎖日。
    続く2つの年度があれば、後の年度の前年度末 = 前の年度の年度末（基金・区分ごと。check_chain）
"""
import json
import os
import re
import subprocess
import sys

Z2H = str.maketrans("０１２３４５６７８９", "0123456789")
HEAD_RE = re.compile(r"^\s*[（(]\s*([0-9０-９]+)\s*[）)]\s*(福岡県\S*?基金)(?:\s|$)")
NUM_RE = re.compile(r"(▲\s*)?(\d{1,3}(?:,\d{3})*(?:\.\d+)?|－|-)(?=\s|$)")
SECTION_STOCK = "資金を積み立てるために設置されたもの"
SECTION_RUN = "定額の資金を運用するために設置されたもの"
# 行の区分として読む名前（空白を除いた形）。縦書きの「動産」「不動産」の字が前に付くことがある
LABELS = ("一般会計貸付金", "有価証券", "現金", "貸付金", "美術作品", "預金", "出資金", "債権", "備蓄物資")


def fix_shifted(text: str) -> str:
    """一部の年度（H25）は数字・記号のフォントの対応表が崩れ、pdftotext が「0」を「㻜」（U+3EDC）、「,」を「㻘」と出す。
    どの字も元の ASCII から U+3EAC だけずれているので戻す（U+3ECC〜U+3F2A は CJK 統合漢字拡張 A で、調書の本文には出ない）"""
    return "".join(chr(ord(c) - 0x3EAC) if 0x3ECC <= ord(c) <= 0x3F2A else c for c in text)


def clean_ocr_line(line: str) -> str:
    """OCR の行から、単位（「千円」）と括弧の注記（前年度の出納整理期間中増高の内数「(▲2,838)」）を除く。
    OCR は単位の行・注記の行を区分の行や額の行と1行にまとめ、「(」を「C」「1」と読む（「C ▲ 2,838)」「1 1,800,000)」）"""
    line = line.replace("千円", " ")
    return re.sub(r"(?:^|\s)\S?\s*▲?\s*\d[\d,]*\s*[)）]", " ", line)


def label_of(line: str):
    f = re.sub(r"\s", "", line)
    f = re.match(r"^([^\d(（▲]*)", f).group(1)  # 区分の名前は行の頭の字（後ろに単位・注記が混ざる）
    f = re.sub(r"^[不動産產]+", "", f)
    if f == "般会計貸付金":
        f = "一般会計貸付金"  # OCR が横線1本の「一」を落とす（R4 の画像）
    return f if f in LABELS else None


def fix_signs(funds: dict) -> list[str]:
    """OCR の読み取り（▲ を読み落とすことがある）の符号を、行の検算で決める。増減・出納整理期間中増高の符号を変えて
    前年度末 + 増減 = 年度末、年度末 + 出納整理 = 出納閉鎖日 になる向きがちょうど1つのときだけ直す。直した箇所を返す"""
    fixed = []
    for name, fd in funds.items():
        for lb, vals in fd["holdings"].items():
            start, chg, end, seiri, close = vals
            if start + chg != end and start - chg == end:
                vals[1] = -chg
                fixed.append(f"{name} {lb} 増減 {chg} → {-chg}")
            if end + seiri != close and end - seiri == close:
                vals[3] = -seiri
                fixed.append(f"{name} {lb} 出納整理 {seiri} → {-seiri}")
    return fixed


def numbers(line: str):
    """行の額（5つ）。頭に縦書きの字（「産」）が付くことがある。小数（㎡）の行は None"""
    body = re.sub(r"^\s*[^\d▲\s－-]+", "", line)
    vals = []
    for m in NUM_RE.finditer(body):
        tok = m.group(2)
        if "." in tok:
            return None
        v = 0 if tok in ("－", "-") else int(tok.replace(",", ""))
        vals.append(-v if m.group(1) else v)
    return vals if len(vals) == 5 else None


def parse(text: str) -> dict:
    """調書のテキスト → {基金名: {"no", "kind", "holdings": {区分: [前年度末, 増減, 年度末, 出納整理, 出納閉鎖]}}}"""
    lines = fix_shifted(text).splitlines()
    # 目次にも同じ見出しが並ぶので、本文の「4 基金」の表（区分の見出しのある最初の基金）から読む
    kind = None
    funds: dict = {}
    cur = None
    label = None
    for ln in lines:
        f = re.sub(r"\s", "", ln)
        if SECTION_STOCK in f:
            kind = "積立"
            continue
        if SECTION_RUN in f:
            kind = "運用"
            continue
        if kind is None:
            continue
        m = HEAD_RE.match(ln)
        if m:
            name = m.group(2)
            if "……" in ln or "…" in f:
                continue  # 目次の行
            cur = funds.setdefault(name, {"no": int(m.group(1).translate(Z2H)), "kind": kind, "holdings": {}})
            label = None
            continue
        if cur is None:
            continue
        if f.startswith("運用状況"):
            cur = None  # 運用基金の運用状況の表は読まない（現在高は上の表にある）
            continue
        if re.match(r"^\s*[（(]", ln):
            continue  # 前年度の出納整理期間中増高（内数）
        ln = clean_ocr_line(ln)
        # 区分と額が同じ行（どの額も「－」の基金・OCR の行）。区分だけの行より先に見る（区分の名前は行の頭の字で決まるので）
        mm = re.match(r"^(\s*[^\d▲－-]+?)\s{2,}([\d▲－-].*)$", ln)
        if mm and label_of(mm.group(1)) and numbers(mm.group(2)) is not None:
            put(cur, label_of(mm.group(1)), numbers(mm.group(2)))
            cur.setdefault("labels", []).append(label_of(mm.group(1)))
            label = None
            continue
        lb = label_of(ln)
        if lb:
            label = lb
            cur.setdefault("labels", []).append(lb)
            continue
        vals = numbers(ln)
        if vals is not None and label:
            put(cur, label, vals)
            label = None
        elif vals is not None:
            cur.setdefault("unlabeled", []).append(ln.strip())  # 区分の名前が一覧（LABELS）にない行。検算で FAIL にする
    for fd in funds.values():
        labels = fd.pop("labels", [])
        if not fd["holdings"] and labels:
            # 区分の行だけで額がない基金（県営林造成事業振興基金。テキストの年度は全部「－」で、OCR は「－」を読まない）。0 として持ち、印を付ける
            fd["holdings"] = {lb: [0, 0, 0, 0, 0] for lb in labels}
            fd["no_figures"] = True
    return funds


def put(fund: dict, label: str, vals: list[int]):
    if label in fund["holdings"]:
        raise SystemExit(f"基金 {fund['no']} の区分「{label}」が2度ある")
    fund["holdings"][label] = vals


def check_rows(year: str, funds: dict) -> list[str]:
    fails = []
    for name, fd in funds.items():
        if not fd["holdings"]:
            fails.append(f"{year} {name}: 区分の行がない")
        for ln in fd.get("unlabeled", []):
            fails.append(f"{year} {name}: 区分の名前の分からない額の行「{ln[:60]}」")
        for lb, (start, chg, end, seiri, close) in fd["holdings"].items():
            if start + chg != end:
                fails.append(f"{year} {name} {lb}: 前年度末 {start} + 増減 {chg} ≠ 年度末 {end}")
            if end + seiri != close:
                fails.append(f"{year} {name} {lb}: 年度末 {end} + 出納整理 {seiri} ≠ 出納閉鎖日 {close}")
    return fails


# 基金の改称（前の名前 → 後の名前）。前の年度末と後の年度の前年度末が区分ごとに一致することを check_chain で確かめる
RENAMES = {
    # R5 に改称（R4 末の有価証券 2,059,977・現金 41,876 千円が、R5 の前年度末と一致。2026-11-20）
    "福岡県こども育成基金": "福岡県出産・子育て安心基金",
}


def check_chain(prev_year: str, prev: dict, year: str, cur: dict) -> list[str]:
    """後の年度の前年度末 = 前の年度の年度末（両方の年度にある基金・区分。改称は RENAMES でつなぐ）。基金の出入りは呼び出し側で示す"""
    fails = []
    prev = {RENAMES.get(n, n): fd for n, fd in prev.items()}
    for name, fd in cur.items():
        p = prev.get(name)
        if p is None:
            continue
        for lb, vals in fd["holdings"].items():
            pv = p["holdings"].get(lb)
            if pv is not None and pv[2] != vals[0]:
                fails.append(f"{prev_year}→{year} {name} {lb}: 前の年度末 {pv[2]} ≠ 前年度末 {vals[0]}")
    return fails


OCR_GLYPHS = str.maketrans({"减": "減", "债": "債", "齡": "齢", "產": "産", "增": "増", "·": "・", "电": "電"})


def canonical_names(year: str, funds: dict, known: set[str]) -> tuple[dict, list[str], list[str]]:
    """OCR の年度の基金の名前を、テキストの年度にある名前に寄せる（OCR は簡体字・小書きの崩れ「减债」「アンビシヤス」を出す）。
    字形を直してから、いちばん近い名前（difflib の比が 0.85 以上で、ちょうど1つ）に寄せる。寄せた記録と、寄せられない名前（FAIL）を返す"""
    import difflib
    out, log, fails = {}, [], []
    for name, fd in funds.items():
        n = name.translate(OCR_GLYPHS)
        if n not in known:
            close = difflib.get_close_matches(n, sorted(known), n=2, cutoff=0.85)
            if len(close) == 1 or (len(close) == 2 and difflib.SequenceMatcher(None, n, close[0]).ratio() >
                                   difflib.SequenceMatcher(None, n, close[1]).ratio() + 0.05):
                n = close[0]
            else:
                fails.append(f"{year} {name}: テキストの年度に同じ名前の基金がない（候補 {close}。画像で確かめる）")
                n = name
        if n != name:
            log.append(f"{year}: 名前を寄せた: {name} → {n}")
        if n in out:
            fails.append(f"{year} {name}: 寄せた名前 {n} が2つになる")
        out[n] = fd
    return out, log, fails


YEAR_ORDER ={f"H{n}": 1988 + n for n in range(23, 32)} | {f"R{n}": 2018 + n for n in range(1, 20)}


def main():
    pairs = [a.split("=", 1) for a in sys.argv[1:]]
    years = {}
    signs = {}
    for year, src in pairs:
        if os.path.isdir(src):
            # 画像の年度: ocr/ocr_lines.py の結果（ページごとのテキスト）。▲ の読み落としは検算で直す（fix_signs）
            txt = "\n".join(open(os.path.join(src, f), encoding="utf-8").read() for f in sorted(os.listdir(src)) if f.endswith(".txt"))
            years[year] = parse(txt)
            signs[year] = fix_signs(years[year])
            for s in signs[year]:
                print(f"{year}: 符号を検算で直した: {s}", file=sys.stderr)
        else:
            txt = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", src, "-"], capture_output=True, text=True, check=True).stdout
            years[year] = parse(txt)
    fails = []
    known = {n for y, fd in years.items() if y not in signs for n in fd}
    renamed = {}
    for y in signs:
        years[y], log, f2 = canonical_names(y, years[y], known)
        renamed[y] = log
        fails += f2
        for s in log:
            print(s, file=sys.stderr)
    for y, fd in years.items():
        fails += check_rows(y, fd)
        n_stock = sum(1 for v in fd.values() if v["kind"] == "積立")
        print(f"{y}: 基金 {len(fd)}（積立 {n_stock}・運用 {len(fd) - n_stock}）", file=sys.stderr)
    ordered = sorted(years, key=YEAR_ORDER.get)
    for a, b in zip(ordered, ordered[1:]):
        if YEAR_ORDER[b] == YEAR_ORDER[a] + 1:
            fails += check_chain(a, years[a], b, years[b])
            # 基金の廃止・新設（名前の読み違いで黙ってつながりの検算から漏れないよう、出入りを並べる）
            pa = {RENAMES.get(n, n) for n in years[a]}
            gone, new = sorted(pa - set(years[b])), sorted(set(years[b]) - pa)
            if gone or new:
                print(f"{a}→{b}: なくなった {gone} / 新しい {new}", file=sys.stderr)
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    json.dump({"unit": "千円", "columns": ["前年度末現在高", "決算年度中増減高", "決算年度末現在高", "出納整理期間中増高", "出納閉鎖日現在高"],
               "years": years, "ocr_years": sorted(signs), "signs_fixed": signs, "names_fixed": renamed},
              sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
