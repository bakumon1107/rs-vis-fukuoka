"""福岡県「一般会計予算及び特別会計予算」（予算書の本体＝議案。R8 は 281297.pdf）から、
会計ごとの「第1表（別表）歳入歳出予算」の款・項の金額を抽出する。

予算説明書（スキャン画像、OCR）の項の単位の照合基準にする。計上額調（テキスト）には款・会計の合計しかない。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_yosansho.py <予算書.pdf> > yosansho.json

PDF の癖（R8 で確認）:
- スキャン画像に発行元が付けた文字層がある。pdftotext -layout では数字が斜めに分断される（「1 / ,06 / 8,3 / 31」）が、
  pdfplumber の単語単位では金額は1語で取れる
- 文字の誤りがある（「軽油弓I取税」「県たばヽ•-税」、項番号「9」が「，」）。名前と番号は参考扱い。
  金額は検算（項の合計 = 款、款の合計 = 第1条の総額、歳入の総額 = 歳出の総額）で確かめる
- 列: 款の番号 x≈64・款の金額の右端 x≈580、項の番号 x≈275・項の金額の右端 x≈782（ページ幅 842）

検証（完全一致。FAIL で終了コード 1）:
- 項の合計 = 款（会計・歳入/歳出ごと）
- 款の合計 = 第1条の「歳入歳出それぞれ X千円」（歳入・歳出とも）
結果（R8）: 一般会計と特別会計14会計のすべてで一致（FAIL=0）。公営企業会計5会計は様式が違うので対象外
"""
import json
import re
import sys

import pdfplumber

AMT = re.compile(r"^\d{1,3}(,\d{3})*$")
KAN_RIGHT = (555, 605)   # 款の金額の右端
KOU_RIGHT = (755, 805)   # 項の金額の右端


def rows_of(page):
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= 4:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def main():
    pdf_path = sys.argv[1]
    kaikei: list[dict] = []
    cur = None
    side = None
    in_table = False
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            text = (page.extract_text() or "").replace(" ", "")
            m = re.search(r"令和\d+年度福岡県(\S+?会計)予算\n", text)
            if "号議案" in text and m:
                cur = {"会計": m.group(1), "pdf_page": pno, "総額": None, "歳入": [], "歳出": []}
                kaikei.append(cur)
                in_table = False
            if cur is None:
                continue
            mt = re.search(r"歳入歳出それぞれ([\d,]+)千円", text)
            if mt and cur["総額"] is None:
                cur["総額"] = int(mt.group(1).replace(",", ""))
            if re.search(r"(第1表|別表)歳入歳出予算", text):
                in_table = True
            elif in_table and re.search(r"第\d表(継続費|債務負担行為|地方債)|^第\d条", text, re.M) and not re.search(r"款項金額", text):
                in_table = False
            if not in_table:
                continue
            for row in rows_of(page):
                joined = "".join(w["text"] for w in row)
                if re.fullmatch(r"歳入", joined):
                    side = "歳入"
                    continue
                if re.fullmatch(r"歳出", joined):
                    side = "歳出"
                    continue
                if side is None:
                    continue
                # 金額は金額の列にあるものだけ（款・項の番号「1」も数字の形に一致する）。
                # 金額が2語に割れることがある（「133,719,」「243」）ので、列の中の数字の断片を x 順につなぐ
                frags = [w for w in row if re.fullmatch(r"[\d,]+", w["text"]) and w["x1"] > KAN_RIGHT[0] - 100]
                if not frags:
                    continue
                txt = "".join(w["text"] for w in frags)
                if not AMT.match(txt):
                    print(f"WARN p{pno}: 金額として読めない「{txt}」（{joined}）", file=sys.stderr)
                    continue
                a = dict(frags[-1], text=txt)
                val = int(txt.replace(",", ""))
                name_words = [w for w in row if w not in frags]
                if re.search(r"(歳入|歳出)合計", "".join(w["text"] for w in name_words)):
                    cur.setdefault("合計", {})[side] = val
                    continue
                no = re.match(r"^(\d{1,2})", name_words[0]["text"]) if name_words else None
                name = "".join(w["text"] for w in name_words)
                name = re.sub(r"^\d{1,2}", "", name)
                if KAN_RIGHT[0] <= a["x1"] <= KAN_RIGHT[1]:
                    cur[side].append({"no": int(no.group(1)) if no else None, "name": name, "金額": val, "pdf_page": pno,
                                      "項": []})
                elif KOU_RIGHT[0] <= a["x1"] <= KOU_RIGHT[1] and cur[side]:
                    cur[side][-1]["項"].append({"no": int(no.group(1)) if no else None, "name": name, "金額": val,
                                               "pdf_page": pno})
    for k in kaikei:
        # 款・項の番号は印字の読み取りが崩れる（警察費の「9」が読めない）ので、並び順で振り直す（款・項は 1 から連番）。
        # 読めた番号は no_印字 に残し、並び順と違えば知らせる
        for side in ("歳入", "歳出"):
            for i, kan in enumerate(k[side], 1):
                kan["no_印字"], kan["no"] = kan["no"], i
                if kan["no_印字"] not in (None, i):
                    print(f"WARN {k['会計']} {side}: 款の印字番号 {kan['no_印字']} が並び順 {i} と違う（{kan['name']}）", file=sys.stderr)
                for j, kou in enumerate(kan["項"], 1):
                    kou["no_印字"], kou["no"] = kou["no"], j
                    if kou["no_印字"] not in (None, j):
                        print(f"WARN {k['会計']} {side} {i}款: 項の印字番号 {kou['no_印字']} が並び順 {j} と違う（{kou['name']}）",
                              file=sys.stderr)
        if k["総額"] is None:
            # 公営企業会計の予算は款項の第1表ではなく「収益的収入及び支出」等の条文の形（別に扱う）
            print(f"{k['会計']}: 第1条の総額なし（公営企業会計の様式）", file=sys.stderr)
            continue
        for side in ("歳入", "歳出"):
            for kan in k[side]:
                s = sum(x["金額"] for x in kan["項"])
                if s != kan["金額"]:
                    fail(f"{k['会計']} {side} {kan['no']}款 {kan['name']}: 項の合計 {s:,} / 款 {kan['金額']:,}")
            tot = sum(x["金額"] for x in k[side])
            if tot != k["総額"]:
                fail(f"{k['会計']} {side}: 款の合計 {tot:,} / 第1条の総額 {k['総額']}")
            if k.get("合計", {}).get(side) != k["総額"]:
                # 合計の行は文字層が崩れていることがある（「歳出合計308.」「125」、行が見つからない）。
                # 款の合計 = 第1条の総額 で確かめられているので参考にとどめる
                print(f"WARN {k['会計']} {side}: {side}合計の行が読めない・一致しない（{k.get('合計', {}).get(side)}）",
                      file=sys.stderr)
        print(f"{k['会計']}: 総額 {k['総額']:,} 千円 / 歳入 {len(k['歳入'])}款 {sum(len(x['項']) for x in k['歳入'])}項"
              f" / 歳出 {len(k['歳出'])}款 {sum(len(x['項']) for x in k['歳出'])}項", file=sys.stderr)
    print(f"会計 {len(kaikei)} 件、FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "千円", "会計": kaikei}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
