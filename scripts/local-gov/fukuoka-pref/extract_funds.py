"""福岡県「実質収支・財産に関する調書」（決算。テキスト PDF）の「4 基金」から、基金ごとの現在高を抽出・検証する。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_funds.py <年度>=<調書.pdf または OCR の結果のディレクトリ> [...] > funds.json
    年度は決算年度（例 R6=272596.pdf R5=238290.pdf）。画像だけの年度は ocr/ocr_lines.py の出力ディレクトリを渡す。
    年度の頭に「~」（~H24=…）を付けた年度は補助の年度: 次の年度の調書にない基金（その年度の間に廃止した基金）だけを使う

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
# 基金の見出し。OCR は番号と名前の間にごみの1〜2字を挟むことがある（H24「(8)   1   福岡県環境保全基金」）
HEAD_RE = re.compile(r"^\s*[（(]\s*([0-9０-９]+)\s*[）)]\s*(?:\S{1,2}\s+)?(福岡県\S*?基金)(?:\s|$)")
# 額: 3桁ごとのコンマ（小数は土地の㎡）。左にも区切りを求める（OCR の「1234,567」を「234,567」と途中から読まない）
NUM_RE = re.compile(r"(▲\s*)?(?<![\d,.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|－|-)(?=\s|$)")
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
    # 「(」の読み違いは「(」「（」「C」「1」だけ（任意の1字にすると区分名の「現 ▲52,639)」の「現」まで消す）
    return re.sub(r"(?:^|\s)[(（C1]?\s*▲?\s*\d[\d,]*\s*[)）]", " ", line)


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


def seven_as_triangle(ln: str):
    """OCR が「▲」を独立した「7」と読んだ行（H29 減債基金の現金「83,224,249 7 29,207,769 …」）。独立した「7」を1つずつ「▲」に
    読み替え、5つの額になり、符号を変えれば 前年度末 ± 増減 = 年度末・年度末 ± 出納整理 = 出納閉鎖日 が成り立つものが
    ちょうど1通りならその額（ほかの ▲ の読み落としは後の fix_signs が直す）"""
    spots = [m.start() for m in re.finditer(r"(?:(?<=\s)|^)7(?=\s+\d)", ln)]
    found = []
    for p in spots:
        vals = numbers(ln[:p] + "▲" + ln[p + 1:])
        # 前年度末（行の頭）は負にならない（基金の現在高）。行の頭の「7」の読み替えで負になる候補は捨てる
        if vals and vals[0] < 0:
            continue
        if vals and any(vals[0] + s1 * abs(vals[1]) == vals[2] for s1 in (1, -1)) and \
                any(vals[2] + s2 * abs(vals[3]) == vals[4] for s2 in (1, -1)):
            found.append(vals)
    return found[0] if len(found) == 1 else None


def parse(text: str, ocr: bool = False) -> dict:
    """調書のテキスト → {基金名: {"no", "kind", "holdings": {区分: [前年度末, 増減, 年度末, 出納整理, 出納閉鎖]}}}
    ocr: OCR の結果のテキスト（OCR の読みの直し「7 → ▲」「0 を1つ落とした行」をこのときだけ使う）"""
    lines = fix_shifted(text).splitlines()
    # 目次にも同じ見出しが並ぶので、本文の「4 基金」の表（区分の見出しのある最初の基金）から読む
    kind = None
    funds: dict = {}
    cur = None
    label = None
    partial = ""  # 前の行の、区分の名前の切れ端（2行に割れた区分名）
    for ln in lines:
        f = re.sub(r"\s", "", ln)
        if SECTION_STOCK in f:
            kind, partial = "積立", ""
            continue
        if SECTION_RUN in f:
            kind, partial = "運用", ""
            continue
        if kind is None:
            continue
        m = HEAD_RE.match(ln)
        if m:
            name = m.group(2)
            if "……" in ln or "…" in f:
                continue  # 目次の行
            cur = funds.setdefault(name, {"no": int(m.group(1).translate(Z2H)), "kind": kind, "holdings": {}})
            label, partial = None, ""
            continue
        if cur is None:
            continue
        if f.startswith("運用状況"):
            cur, partial = None, ""  # 運用基金の運用状況の表は読まない（現在高は上の表にある）
            continue
        if re.match(r"^\s*[（(]", ln):
            continue  # 前年度の出納整理期間中増高（内数）。区分の名前の切れ端（partial）はこの行を挟んで続くので残す
        ln = clean_ocr_line(ln)
        # 区分と額が同じ行（どの額も「－」の基金・OCR の行）。区分だけの行より先に見る（区分の名前は行の頭の字で決まるので）
        mm = re.match(r"^(\s*[^\d▲－-]+?)\s{2,}([\d▲－-].*)$", ln)
        if mm and label_of(mm.group(1)) and numbers(mm.group(2)) is not None:
            put(cur, label_of(mm.group(1)), numbers(mm.group(2)))
            cur.setdefault("labels", []).append(label_of(mm.group(1)))
            label = None
            continue
        lb = label_of(ln)
        compact = re.sub(r"\s", "", ln)
        if not lb and partial and compact and not re.search(r"\d", compact):
            # 区分の名前が注記を挟んで2行に割れる（H24「現 ▲52,639)」「金」）。つないで区分になれば区分
            lb = label_of(partial + compact)
        if lb:
            label = lb
            partial = ""
            cur.setdefault("labels", []).append(lb)
            continue
        partial = compact if compact and not re.search(r"\d", compact) else ""
        vals = numbers(ln)
        if vals is None and label and ocr:
            # OCR が「▲」を独立した「7」と読んだ行。検算が成り立つ読み替えがちょうど1通りなら使い、記録する
            vals = seven_as_triangle(ln)
            if vals is not None:
                cur.setdefault("ocr_fixed", []).append(f"{label}: 「7」を「▲」に読み替えた（{ln.strip()[:50]}）")
        if vals is None and label and ocr and re.fullmatch(r"\s*0(\s+0){3}\s*", ln):
            # OCR が 0 を1つ読み落とした行（H24「0 0 0 0」）。4つの額が 0 なら、前年度末 + 増減 = 年度末・年度末 + 出納整理 = 出納閉鎖日
            # から、欠けた額も 0 にしか決まらない（どの位置が欠けても）。記録して 0 で埋める
            vals = [0, 0, 0, 0, 0]
            cur.setdefault("ocr_fixed", []).append(f"{label}: 0 の4つの行の欠けた額を 0 とした")
        if vals is None and label and len(re.findall(r"\d", ln)) >= 3:
            # 区分の後の額の行が5つの額として読めない（OCR がコンマを「.」と読んだ・数が欠けた）。黙って区分を落とさず FAIL にする
            cur.setdefault("rejected", []).append(f"{label}: {ln.strip()}")
            label = None
            continue
        if vals is not None and label:
            put(cur, label, vals)
            label = None
        elif vals is not None:
            cur.setdefault("unlabeled", []).append(ln.strip())  # 区分の名前が一覧（LABELS）にない行。検算で FAIL にする
    for fd in funds.values():
        labels = fd.pop("labels", [])
        if not fd["holdings"] and labels and not fd.get("rejected") and not fd.get("unlabeled"):
            # 区分の行だけで額がない基金（OCR は「－」を読まない）。ここでは 0 にしない（額の行を丸ごと読み落としたのと区別できない）。
            # main で、原本で全部「－」と確かめた年度・基金（NO_FIGURES_CONFIRMED）だけ 0 にする。それ以外は「区分の行がない」で FAIL
            fd["labels_only"] = list(dict.fromkeys(labels))
            continue
        # 区分の名前を読んだのに額が入らなかった区分（「現金」の後の額の行が5つに足りず、次の基金に移った、など）を黙って落とさない
        noted = {r.split(":", 1)[0] for r in fd.get("rejected", [])}
        for lb in dict.fromkeys(labels):
            if lb not in fd["holdings"] and lb not in noted:
                fd.setdefault("rejected", []).append(f"{lb}: 区分の名前の後に額の行がない")
    return funds


# 区分の行だけで額のない基金（OCR は「－」を読まない）のうち、原本の画像で全部「－」と確かめた年度・基金（2026-11-20）。
# ここにあるものだけ 0 として持ち、印（no_figures）を付ける
NO_FIGURES_CONFIRMED = {
    # 有価証券・現金とも5列すべて「－」（H27 p58・H28 p58・H29 p57・R4 p61 の画像で確認）
    ("H27", "福岡県県営林造成事業振興基金"), ("H28", "福岡県県営林造成事業振興基金"),
    ("H29", "福岡県県営林造成事業振興基金"), ("R4", "福岡県県営林造成事業振興基金"),
}


def fill_no_figures(year: str, funds: dict) -> list[str]:
    """区分の行だけの基金を、確かめた表にあれば 0 で埋める。表にない基金は残し（check_rows が「区分の行がない」で FAIL）、記録を返す"""
    log = []
    for name, fd in funds.items():
        labels = fd.pop("labels_only", None)
        if labels is None:
            continue
        if (year, name) in NO_FIGURES_CONFIRMED:
            fd["holdings"] = {lb: [0, 0, 0, 0, 0] for lb in labels}
            fd["no_figures"] = True
        else:
            log.append(f"{year} {name}: 区分の行だけで額がない（原本で全部「－」なら NO_FIGURES_CONFIRMED に足す）")
    return log


def put(fund: dict, label: str, vals: list[int]):
    if label in fund["holdings"]:
        # 区分が2度ある: 次の基金の見出しを読めず、その行がこの基金に混ざった。止めずに記録して検算で FAIL にする（どの年度かが分かる）
        fund.setdefault("rejected", []).append(f"区分「{label}」が2度ある（次の基金の見出しを読めていない）")
        return
    fund["holdings"][label] = vals


def check_rows(year: str, funds: dict) -> list[str]:
    fails = []
    for name, fd in funds.items():
        if not fd["holdings"]:
            fails.append(f"{year} {name}: 区分の行がない")
        for ln in fd.get("unlabeled", []):
            fails.append(f"{year} {name}: 区分の名前の分からない額の行「{ln[:60]}」")
        for ln in fd.get("rejected", []):
            fails.append(f"{year} {name}: 額として読めない行「{ln[:60]}」")
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
    # R4 に改称（R3 末の現金 2,508,273 千円が R4 の前年度末と一致。R3 の調書は画像・OCR。2026-11-20）
    "福岡県緊急経済対策資金信用保証料補填臨時基金": "福岡県緊急経済対策資金等信用保証料補填臨時基金",
}


def check_chain(prev_year: str, prev: dict, year: str, cur: dict) -> list[str]:
    """後の年度の前年度末 = 前の年度の年度末（両方の年度にある基金・区分。改称は RENAMES でつなぐ）。基金の出入りは呼び出し側で示す"""
    fails = []
    prev = {RENAMES.get(n, n): fd for n, fd in prev.items()}
    for name, fd in cur.items():
        p = prev.get(name)
        if p is None:
            continue
        # 基金の合計でも比べる（片方の年度で区分の行が落ちると、区分ごとの比較だけでは気づけない）
        p_end = sum(v[2] for v in p["holdings"].values())
        c_start = sum(v[0] for v in fd["holdings"].values())
        if p_end != c_start:
            fails.append(f"{prev_year}→{year} {name}: 前の年度末の合計 {p_end} ≠ 前年度末の合計 {c_start}"
                         f"（区分 {sorted(p['holdings'])} / {sorted(fd['holdings'])}）")
        for lb, vals in fd["holdings"].items():
            pv = p["holdings"].get(lb)
            if pv is not None and pv[2] != vals[0]:
                fails.append(f"{prev_year}→{year} {name} {lb}: 前の年度末 {pv[2]} ≠ 前年度末 {vals[0]}")
    return fails


OCR_GLYPHS = str.maketrans({"减": "減", "债": "債", "齡": "齢", "產": "産", "增": "増", "·": "・", "电": "電", "讓": "譲", "查": "査"})


# OCR の読みの崩れのうち、字形の表（OCR_GLYPHS）で直せないもの。確かめた名前だけ（2026-11-20）。
# 小書きの「ャ」を大きい「ヤ」と読む: テキストの年度（H23・H25・H30・R2・R5・R6 の PDF の文字）の名前はすべて「アンビシャス」で、
# 「アンビシヤス」の基金はない。OCR の年度（H27・H28・H29・R4）の前年度末は、前の年度のこの基金の年度末と一致する（check_chain）
OCR_NAME_FIXES = {
    "福岡県アンビシヤス外国留学支援基金": "福岡県アンビシャス外国留学支援基金",
}


def canonical_names(year: str, funds: dict, known: set[str]) -> tuple[dict, list[str], list[str]]:
    """OCR の年度の基金の名前を、テキストの年度にある名前に直す（OCR は簡体字・異体字・小書きの崩れ「减债」「アンビシヤス」を出す）。
    直すのは字形の表（OCR_GLYPHS）と、画像で確かめた名前の表（OCR_NAME_FIXES）だけ。似ているだけの名前には寄せない
    （原本が別の名前の基金でも、検算は額しか確かめないので通ってしまう）。直した記録と、テキストの年度にない名前（FAIL）を返す。
    FAIL には似た名前を候補として書く（画像で確かめて OCR_NAME_FIXES に足すため）"""
    import difflib
    out, log, fails = {}, [], []
    for name, fd in funds.items():
        n = name.translate(OCR_GLYPHS)
        n = OCR_NAME_FIXES.get(n, n)
        if n not in known:
            close = difflib.get_close_matches(n, sorted(known), n=2, cutoff=0.85)
            fails.append(f"{year} {name}: テキストの年度に同じ名前の基金がない（似た名前 {close}。画像で確かめて OCR_NAME_FIXES に足す）")
            n = name
        if n != name:
            log.append(f"{year}: 名前を寄せた: {name} → {n}")
        if n in out:
            # 失敗の行は寄せた後の名前で始める（補助の年度で、残した基金の失敗だけを選ぶため）
            fails.append(f"{year} {n}: 寄せた名前が2つになる（{name} ほか）")
        out[n] = fd
    return out, log, fails


YEAR_ORDER ={f"H{n}": 1988 + n for n in range(23, 32)} | {f"R{n}": 2018 + n for n in range(1, 20)}


def main():
    pairs = [a.split("=", 1) for a in sys.argv[1:]]
    years = {}
    signs = {}
    supplement = [y.lstrip("~") for y, _ in pairs if y.startswith("~")]
    for year, src in pairs:
        year = year.lstrip("~")
        if os.path.isdir(src):
            # 画像の年度: ocr/ocr_lines.py の結果（ページごとのテキスト）。▲ の読み落としは検算で直す（fix_signs。名前を寄せた後で記録する）
            # OCR を終えた印（done.json。ocr_lines.py が範囲のページがそろったときに書く）のないディレクトリは読まない
            # （途中で止まった OCR だと、一部の基金だけの年度になる）。印の範囲のページだけを読む
            done = os.path.join(src, "done.json")
            if not os.path.exists(done):
                raise SystemExit(f"{year}: {src} に done.json がない（OCR が終わっていない。ocr_lines.py を流し直す）")
            first, last = json.load(open(done, encoding="utf-8"))["pages"]
            pages = [os.path.join(src, f"p{p:04d}.txt") for p in range(first, last + 1)]
            if not all(os.path.exists(p) for p in pages):
                raise SystemExit(f"{year}: {src} のページがそろっていない（done.json の範囲 {first}-{last}）")
            txt = "\n".join(open(p, encoding="utf-8").read() for p in pages)
            years[year] = parse(txt, ocr=True)
            signs[year] = []
        else:
            txt = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", src, "-"], capture_output=True, text=True, check=True).stdout
            years[year] = parse(txt)
    fails = []
    known = {n for y, fd in years.items() if y not in signs for n in fd}
    renamed = {}
    name_fails = {}
    for y in signs:
        years[y], log, name_fails[y] = canonical_names(y, years[y], known)
        renamed[y] = log
        for s in log:
            print(s, file=sys.stderr)
        # OCR の読みの直し（寄せた後の名前で記録する）
        signs[y] = [f"{n} {x}" for n, fd in years[y].items() for x in fd.pop("ocr_fixed", [])] + fix_signs(years[y])
    # 補助の年度（「~H24=…」）: 次の年度の調書にない基金（その年度の間に廃止した基金）だけを残す。ほかの基金の年度末は
    # 次の年度の調書の前年度末で足りる（読み取りの質の低い OCR の年度の行を全部は使わない）
    for y in supplement:
        nxt = next((x for x in years if YEAR_ORDER[x] == YEAR_ORDER[y] + 1), None)
        if nxt is None:
            fails.append(f"{y}: 補助の年度の次の年度の調書がない")
            continue
        keep = {n: fd for n, fd in years[y].items() if n not in years[nxt] and RENAMES.get(n, n) not in years[nxt]}
        print(f"{y}: 補助の年度。次の年度（{nxt}）の調書にない基金 {len(keep)} を残す {sorted(keep)}", file=sys.stderr)
        years[y] = keep
        for n, fd in keep.items():
            # 残すのはその年度の間に廃止した基金なので、年度末は 0 のはず。0 でなければ、次の年度で名前が変わった（RENAMES にない改称）か
            # 名前の読み違いで、そのまま使うと次の年度の前年度末と二重に数える
            end = sum(v[2] for v in fd["holdings"].values())
            if end != 0:
                fails.append(f"{y} {n}: 補助の年度で残した基金の年度末が 0 でない（{end}。改称か名前の読み違い。RENAMES を確かめる）")
        # 名前の寄せの失敗も、残した基金のものだけ（捨てた基金の名前の崩れは使わないので問わない）
        # ただし名前が2つの基金に寄る失敗はいつも残す（片方の基金の値が上書きで消えている。捨てた基金の名前でも、消えたのは残すべき基金かもしれない）
        name_fails[y] = [f for f in name_fails.get(y, []) if any(f.startswith(f"{y} {n}:") for n in keep) or "寄せた名前が2つ" in f]
        if y in signs:  # テキスト（PDF）の補助の年度には OCR の読みの直しの記録がない
            signs[y] = [s for s in signs[y] if any(s.startswith(f"{n} ") for n in years[y])]
    for f2 in name_fails.values():
        fails += f2
    # 区分の行だけの基金は、原本で確かめた年度・基金だけ 0 にする（名前を直し、補助の年度で残す基金を決めた後で表を引く）
    for y in years:
        for s in fill_no_figures(y, years[y]):
            print(s, file=sys.stderr)
    for y, ss in signs.items():
        for s in ss:
            print(f"{y}: OCR の読みを検算で直した: {s}", file=sys.stderr)
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
            if (gone or new) and a not in supplement and b not in supplement:  # 補助の年度は一部の基金だけなので並べない
                print(f"{a}→{b}: なくなった {gone} / 新しい {new}", file=sys.stderr)
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    json.dump({"unit": "千円", "columns": ["前年度末現在高", "決算年度中増減高", "決算年度末現在高", "出納整理期間中増高", "出納閉鎖日現在高"],
               "years": years, "ocr_years": sorted(signs), "supplement_years": supplement, "signs_fixed": signs, "names_fixed": renamed,
               # 検算の失敗（書き出し export_funds.build はこれが空でなければ止める。終了コードを見ない使い方でも通さない）
               "fails": fails},
              sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
