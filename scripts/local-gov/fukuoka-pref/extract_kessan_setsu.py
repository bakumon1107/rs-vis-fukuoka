"""福岡県「歳入歳出決算事項別明細書」（テキスト PDF）から、目ごとの節（＝性質別）の決算を抽出し、款項目別明細表と突合する。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_kessan_setsu.py <事項別明細書.pdf> <kessan-kmk.json> > kessan-setsu.json

PDF の癖（R6 で確認）:
- 文字が2層で描かれている。片方は区分が x≈296〜317・金額が1語、もう片方は区分が x≈319〜343・金額が1文字ずつ。
  金額は「1語の層」だけを、列の右端の位置で拾う（節の金額 x1≈398.6 / 支出済額 ≈501.9 / 繰越3列 ≈539.4・576.9・614.5 / 不用額 ≈652.0）
- 目の行（予算現額の内訳つき）は列が詰まって数字がつながる（「0688497000」）ので数値は使わず、「新しい目の始まり」の印にだけ使う
- 目の名称の一部が文字コードなし（(cid:N)）。目の特定は、節の合計を款項目別明細表の目と順に照合して行う
節の名称は地方自治法施行規則の節の番号から付ける。

検証（完全一致。FAIL で終了コード 1）:
- 目ごとに: 節の金額の合計 = 明細表の予算現額、節の支出済額の合計 = 明細表の支出済額
- 節の金額は 1層しかない列から 支出済額 + 繰越額（3列）+ 不用額 で求める（節の金額の列は2層が重なり信頼できない）。
  その正しさは「目ごとの合計 = 明細表の予算現額」で確認する。列から読めた値との一致率も参考に出す
- 明細表のすべての目（予算現額が 0 でないもの）に対応が付く
"""
import json
import os
import re
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kessan_common import SETSU_NAMES as SETSU  # noqa: E402  節の名前（番号で決まる）


# 文字単位で列を組み立てる x の範囲（R6 実測）。単語単位だと、1文字ずつの層の数字（x≈352〜376）と
# 1語の層の節の金額（x≈377〜399）の間隔が数字どうしの間隔と同じなので、つながって「424502909644」のようになる（実例）
# 右寄せの列なので、範囲は「前の列の右端〜この列の右端」と隙間なく取る。狭く取ると桁の多い金額の先頭が欠ける
# （繰越明許費の大きい目 28件が対応しなかった実例あり）
BANDS = [("節の金額", 376.8, 399.5), ("支出済額", 400.0, 503.0), ("継続費逓次繰越", 503.0, 540.5),
         ("繰越明許費", 540.5, 578.0), ("事故繰越し", 578.0, 615.5), ("不用額", 615.5, 653.5)]
LABEL_BAND = (294.0, 318.5)   # 1語の層の節の区分（番号＋名称）
MOKU_BAND = (40.0, 290.0)     # 款・項・目の行の予算現額の内訳（ここに数字があれば新しい款・項・目の行）


# 特別会計の歳出のページ（R6 の PDF 262ページ〜）は、予算現額の内訳の列が多く、節の区分から右の列の位置が一般会計と違う。
# 列の幅は一般会計と同じ 37.5pt 間隔で、見開きの左右のページで 9.7pt ずれる2通りがある（支出済額の右端 583.2 / 592.9。R6 実測）
SPECIAL_BANDS = [("節の金額", 508.0, 546.5), ("支出済額", 546.5, 584.0), ("継続費逓次繰越", 584.0, 621.5),
                 ("繰越明許費", 621.5, 659.0), ("事故繰越し", 659.0, 696.5), ("不用額", 696.5, 734.0)]
SPECIAL_LABEL_BAND = (455.0, 508.0)
SPECIAL_MOKU_BAND = (40.0, 440.0)


def special_shift(page) -> float | None:
    """特別会計の歳出の並びなら、列のずれ（0 か 9.7）。一般会計の並びなら None。支出済額の列の数字の右端で見分ける。"""
    ends = [c["x1"] for c in page.chars if c["text"].isdigit() and repr(c.get("non_stroking_color")) == "(0.0,)"]
    a = sum(1 for x in ends if abs(x - 583.2) < 0.6)
    b = sum(1 for x in ends if abs(x - 592.9) < 0.6)
    general = sum(1 for x in ends if abs(x - 501.9) < 0.6)
    if max(a, b) == 0 or general > max(a, b):
        return None
    return 0.0 if a >= b else 9.7


def rows_of(page, special: bool = False):
    shift = special_shift(page) if special else None
    if shift is not None:
        return rows_of_special(page, shift)
    # 2層で描かれていないページもある（R6 の p55・p156。1語の層の色 (0,) が無い）。
    # そのページでは色で層を選ばず、列の位置だけで読む（選ぶと節の金額が全行 None になり、行ごと捨てていた実例）
    # 判定は節の金額の列の数字に限る（ページの他の場所には 1層のページにも (0,) の文字がある。p55 で確認）
    two_layers = any(repr(c.get("non_stroking_color")) == "(0,)" and c["text"].isdigit() and 340.0 <= c["x0"]
                     and c["x1"] <= 399.5 for c in page.chars)
    rows: dict[int, list] = {}
    for c in page.chars:
        rows.setdefault(round(c["top"] / 2) * 2, []).append(c)
    out = []
    for _, cs in sorted(rows.items()):
        cs = sorted(cs, key=lambda c: c["x0"])
        rec = {"two_layers": two_layers,
               "label": "".join(c["text"] for c in cs if LABEL_BAND[0] <= c["x0"] < LABEL_BAND[1]),
               # ページ上端の款・項の見出し（「1 議会費」が3層で描かれる）やページ番号にも数字があるので、
               # 4桁以上「続く」数字があるときだけ金額（＝款・項・目の行）とみなす
               "moku_digits": re.search(r"\d{4,}", "".join(c["text"] for c in cs if MOKU_BAND[0] <= c["x0"] < MOKU_BAND[1]))
               is not None}
        for name, a, b in BANDS:
            if name == "節の金額" and two_layers:
                # 2つの層は文字色の値の型だけが違う（1文字ずつの層は (0.0,)、1語の層は (0,)。R6 で確認）。
                # 桁の多い金額は 1語の層でも x≈373 から始まるので、x ではなく色の型で層を選ぶ
                ds = "".join(c["text"] for c in cs if 340.0 <= c["x0"] and c["x1"] <= b and c["text"].isdigit()
                             and repr(c.get("non_stroking_color")) == "(0,)")
            else:
                ds = "".join(c["text"] for c in cs if a <= c["x0"] and c["x1"] <= b and c["text"].isdigit())
            rec[name] = int(ds) if ds else None
        out.append(rec)
    return out


CID_RE = re.compile(r"\(cid:(\d+)\)")


def digit_of(text: str) -> str | None:
    """文字の数字。特別会計のページでは一部の数字が文字コードなし（(cid:N)）で描かれ、N − 19 がその数字
    （(cid:20)=1・(cid:22)=3・(cid:26)=7。概要説明書の値と照らして確かめた。R6 公債管理 支出済額「5244(cid:22)(cid:20)(cid:22)88090」= 524,431,388,090）"""
    if text.isdigit():
        return text
    m = CID_RE.fullmatch(text)
    if m and 19 <= int(m.group(1)) <= 28:
        return str(int(m.group(1)) - 19)
    return None


def rows_of_special(page, shift: float):
    """特別会計の歳出のページの行。右側の列は1つの層（(0.0,)）だけを読む。節の金額は呼び出し側で他の列から求め直す。"""
    rows: dict[int, list] = {}
    for c in page.chars:
        rows.setdefault(round(c["top"] / 2) * 2, []).append(c)
    out = []
    la, lb = SPECIAL_LABEL_BAND
    ma, mb = SPECIAL_MOKU_BAND
    for _, cs in sorted(rows.items()):
        cs = sorted(cs, key=lambda c: c["x0"])
        one = [c for c in cs if repr(c.get("non_stroking_color")) == "(0.0,)"]
        # 節の区分の番号も (cid:N) で描かれることがある（「(cid:20)(cid:20)需用費」= 11）。番号の部分だけ数字に直す
        label = "".join(c["text"] for c in one if la + shift <= c["x0"] < lb + shift).strip()
        # 数字の (cid:N) は 19〜28 だけ（digit_of と同じ範囲。29 は数字ではない）
        mlab = re.match(r"^((?:\d|\(cid:(?:19|2[0-8])\))+)(.*)$", label)
        if mlab:
            label = "".join(digit_of(x) for x in re.findall(r"\d|\(cid:\d+\)", mlab.group(1))) + mlab.group(2)
        rec = {"two_layers": False, "label": label,
               "moku_digits": re.search(r"\d{4,}", "".join(digit_of(c["text"]) or "x" for c in cs if ma <= c["x0"] < mb))
               is not None}
        for name, a, b in SPECIAL_BANDS:
            ds = "".join(digit_of(c["text"]) or "" for c in one if a + shift <= c["x0"] and c["x1"] <= b + shift)
            rec[name] = int(ds) if ds else None
        out.append(rec)
    return out


def main():
    pdf_path, kmk_path = sys.argv[1], sys.argv[2]
    kmk = json.load(open(kmk_path, encoding="utf-8"))
    # --toku <kessan-toku.json>: 一般会計の後に続く特別会計の歳出の目にも対応させる（extract_kessan_toku.py の出力。会計の順に並ぶ）
    toku = None
    if "--toku" in sys.argv:
        with open(sys.argv[sys.argv.index("--toku") + 1], encoding="utf-8") as f:
            toku = json.load(f)
    groups: list[dict] = []  # 目の単位（目の行で区切る）
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for row in rows_of(page, special=toku is not None):
                if row["moku_digits"] and (row["節の金額"] is None or not row["two_layers"]):
                    groups.append({"pdf_page": pno, "節": []})
                    continue
                label = row["label"].strip()
                # 2層のページでは、節の金額が読めない行は節ではない（款・項の合計の行など。拾うと 7目が崩れた実例）。
                # 1層のページでは節の金額の列の位置が違い読めないので、それを条件にしない（節の金額は下で他の列から求める）
                if (row["two_layers"] and row["節の金額"] is None) or row["支出済額"] is None or not groups:
                    continue
                m = re.match(r"^(\d{1,2})\s*(.*)$", label)
                rec = {"no": int(m.group(1)) if m else None, **{c: (row[c] or 0) for c, _, _ in BANDS}, "pdf_page": pno}
                # 節の金額の列は2層が重なり、ページによって二重に読める（p44「942666000942666000」）。
                # 1層しかない列から 支出済額 + 繰越額 + 不用額 で求め、読めた値と一致するかは参考に記録する
                read = rec["節の金額"]
                rec["節の金額"] = rec["支出済額"] + rec["継続費逓次繰越"] + rec["繰越明許費"] + rec["事故繰越し"] + rec["不用額"]
                rec["節の金額_読み取り一致"] = read == rec["節の金額"]
                if m:
                    rec["節"] = SETSU.get(rec["no"], "?")
                    groups[-1]["節"].append(rec)
                elif groups[-1]["節"]:
                    groups[-1]["節"][-1].setdefault("細節", []).append({**rec, "名称": label})
    # 明細表の目（歳入→歳出の順）に、節のある区画を順に対応させる
    ref = []
    for side in ("revenue", "expense"):
        for kan in kmk[side]:
            for kou in kan["children"]:
                for mo in kou["children"]:
                    ref.append((side, kan["no"], kou["no"], mo["no"], mo, "一般会計"))
    for acc in (toku or {}).get("会計", []):
        for kou in acc["項"]:
            for mo in kou["目"]:
                ref.append(("expense", kou["款"], kou["項"], mo["no"], mo, acc["会計"]))
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    cand = [g for g in groups if g["節"]]
    out = []
    gi = 0
    prev_acc = None
    last_failed = False
    for side, ka, ko, mo_no, mo, acc_name in ref:
        if side != "expense":
            continue  # 歳入の節（現年課税分など）は名称が規則で決まっていないので今回は歳出のみ
        if mo["予算現額"] == 0 and mo["支出済額"] == 0:
            continue
        # 目はページ境界で複数の区画に分かれることがあるので、連続する 1〜4 区画をつないだ合計で照合する。
        # 会計の最初の歳出の目は、その会計の歳入の区画を飛ばす必要があるので探索範囲を広く取る。
        # 直前の目が対応しなかったときも広く取る（狭いままだと、その会計の残りの目がまとめて対応しなくなる。R6 国民健康保険で実例）。
        # 予算現額と支出済額の両方がちょうど一致する区画だけを採るので、広く探しても取り違えにくい
        found = None
        window = len(cand) if (acc_name != prev_acc or last_failed) else 8
        prev_acc = acc_name
        for j in range(gi, min(gi + window, len(cand))):
            for k in range(1, 11):  # 節の多い目は 5ページ以上にまたがる
                seg = cand[j:j + k]
                if len(seg) < k:
                    break
                ss = [s for g in seg for s in g["節"]]
                if sum(s["節の金額"] for s in ss) == mo["予算現額"] and sum(s["支出済額"] for s in ss) == mo["支出済額"]:
                    found = (j, k)
                    break
            if found:
                break
        if found is None:
            fail(f"対応なし {acc_name} {ka}款{ko}項{mo_no}目 {mo['name']}（予算現額 {mo['予算現額']:,}、支出済額 {mo['支出済額']:,}）")
            last_failed = True
            continue
        last_failed = False
        j, k = found
        if j != gi and out and window == 8:
            print(f"WARN {acc_name} {ka}款{ko}項{mo_no}目 {mo['name']}: 区画を {j - gi} 個飛ばして対応", file=sys.stderr)
        g = {"pdf_page": cand[j]["pdf_page"], "節": [s for x in cand[j:j + k] for s in x["節"]]}
        gi = j + k
        rec = {"款": ka, "項": ko, "目": mo_no, "目名": mo["name"], "予算現額": mo["予算現額"], "支出済額": mo["支出済額"],
               "節": g["節"], "pdf_page": g["pdf_page"]}
        if acc_name != "一般会計":
            rec["会計"] = acc_name  # 一般会計の行は今までどおり会計を書かない（既存の出力を変えない）
        out.append(rec)
    all_s = [s for o in out for s in o["節"]]
    match = sum(s["節の金額_読み取り一致"] for s in all_s)
    print(f"節 {len(all_s)} 件のうち、節の金額の列から読めた値が計算値と一致: {match} 件", file=sys.stderr)
    print(f"節の区画 {len(cand)} 件、明細表の歳出の目に対応 {len(out)} 件、FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "円", "目": out}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
