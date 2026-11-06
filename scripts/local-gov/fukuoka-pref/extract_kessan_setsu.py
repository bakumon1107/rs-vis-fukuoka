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
import re
import sys

import pdfplumber

SETSU = {1: "報酬", 2: "給料", 3: "職員手当等", 4: "共済費", 5: "災害補償費", 6: "恩給及び退職年金", 7: "報償費", 8: "旅費",
         9: "交際費", 10: "需用費", 11: "役務費", 12: "委託料", 13: "使用料及び賃借料", 14: "工事請負費", 15: "原材料費",
         16: "公有財産購入費", 17: "備品購入費", 18: "負担金、補助及び交付金", 19: "扶助費", 20: "貸付金",
         21: "補償、補塡及び賠償金", 22: "償還金、利子及び割引料", 23: "投資及び出資金", 24: "積立金", 25: "寄附金",
         26: "公課費", 27: "繰出金"}


# 文字単位で列を組み立てる x の範囲（R6 実測）。単語単位だと、1文字ずつの層の数字（x≈352〜376）と
# 1語の層の節の金額（x≈377〜399）の間隔が数字どうしの間隔と同じなので、つながって「424502909644」のようになる（実例）
# 右寄せの列なので、範囲は「前の列の右端〜この列の右端」と隙間なく取る。狭く取ると桁の多い金額の先頭が欠ける
# （繰越明許費の大きい目 28件が対応しなかった実例あり）
BANDS = [("節の金額", 376.8, 399.5), ("支出済額", 400.0, 503.0), ("継続費逓次繰越", 503.0, 540.5),
         ("繰越明許費", 540.5, 578.0), ("事故繰越し", 578.0, 615.5), ("不用額", 615.5, 653.5)]
LABEL_BAND = (294.0, 318.5)   # 1語の層の節の区分（番号＋名称）
MOKU_BAND = (40.0, 290.0)     # 款・項・目の行の予算現額の内訳（ここに数字があれば新しい款・項・目の行）


def rows_of(page):
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


def main():
    pdf_path, kmk_path = sys.argv[1], sys.argv[2]
    kmk = json.load(open(kmk_path, encoding="utf-8"))
    groups: list[dict] = []  # 目の単位（目の行で区切る）
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for row in rows_of(page):
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
                    ref.append((side, kan["no"], kou["no"], mo["no"], mo))
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    cand = [g for g in groups if g["節"]]
    out = []
    gi = 0
    for side, ka, ko, mo_no, mo in ref:
        if side != "expense":
            continue  # 歳入の節（現年課税分など）は名称が規則で決まっていないので今回は歳出のみ
        if mo["予算現額"] == 0 and mo["支出済額"] == 0:
            continue
        # 目はページ境界で複数の区画に分かれることがあるので、連続する 1〜4 区画をつないだ合計で照合する。
        # 最初の歳出の目は、歳入の区画を飛ばす必要があるので探索範囲を広く取る
        found = None
        window = len(cand) if not out else 8
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
            fail(f"対応なし {ka}款{ko}項{mo_no}目 {mo['name']}（予算現額 {mo['予算現額']:,}、支出済額 {mo['支出済額']:,}）")
            continue
        j, k = found
        if j != gi and out:
            print(f"WARN {ka}款{ko}項{mo_no}目 {mo['name']}: 区画を {j - gi} 個飛ばして対応", file=sys.stderr)
        g = {"pdf_page": cand[j]["pdf_page"], "節": [s for x in cand[j:j + k] for s in x["節"]]}
        gi = j + k
        out.append({"款": ka, "項": ko, "目": mo_no, "目名": mo["name"], "予算現額": mo["予算現額"], "支出済額": mo["支出済額"],
                    "節": g["節"], "pdf_page": g["pdf_page"]})
    all_s = [s for o in out for s in o["節"]]
    match = sum(s["節の金額_読み取り一致"] for s in all_s)
    print(f"節 {len(all_s)} 件のうち、節の金額の列から読めた値が計算値と一致: {match} 件", file=sys.stderr)
    print(f"節の区画 {len(cand)} 件、明細表の歳出の目に対応 {len(out)} 件、FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "円", "目": out}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


main()
