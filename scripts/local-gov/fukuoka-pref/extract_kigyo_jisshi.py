"""福岡県の特別会計の予算説明書（R8 は 281299.pdf）の後半にある、公営企業会計の「予算実施計画」から
款 → 項 → 目 の予定額を抽出し、予算書の本体（extract_yosansho.py の出力）の款・項と照合する。

このページには発行元が付けた文字層があり、OCR は不要（特別会計の前半は文字層が崩れていて OCR が必要）。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_kigyo_jisshi.py <説明書.pdf> <yosansho.json> > kigyo-jisshi.json

ページの構成（R8 で確認）:
- 会計ごとに「令和8年度福岡県○○事業会計予算実施計画」の見出しで始まり、
  「収益的収入及び支出」「資本的収入及び支出」の下に「収入」「支出」の表が続く。表の列は 款 / 項 / 目 / 予定額 / 備考
- 段（款・項・目）は行頭の番号の x 位置で決まる。基準は列見出しの「款」「項」「目」の x（ページごとに少しずれる）
- 金額が文字層で斜めに分断される（「1 / ,46 / 1」）ので、予定額の列の数字の断片を x 順につなぐ
- 実施計画の後は キャッシュ・フロー計算書・給与費明細書・貸借対照表（ここでは読まない）

検証（完全一致。FAIL で終了コード 1）:
- 目の合計 = 項、項の合計 = 款
- 款・項の金額 = 予算書の本体の第3条・第4条（並び順で対応）
"""
import json
import re
import sys

import pdfplumber

AMT = re.compile(r"^\d{1,3}(,\d{3})*$")


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
    pdf_path, yo_path = sys.argv[1], sys.argv[2]
    yo = {k["会計"]: k for k in json.load(open(yo_path, encoding="utf-8"))["会計"] if k["会計"].endswith("事業会計")}
    out: list[dict] = []
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    with pdfplumber.open(pdf_path) as pdf:
        cur = None
        anchors = None
        pending_name = ""
        for pno, page in enumerate(pdf.pages, 1):
            text = (page.extract_text() or "").replace(" ", "")
            m = re.search(r"令和\d+年度福岡県(\S+?事業会計)予算実施計画", text)
            if m:
                if out and out[-1]["会計"] == m.group(1):
                    out.pop()  # 直前のページ（目次）にも同じ見出しがある。本文の方を残す
                cur = {"会計": m.group(1), "pdf_page": pno, "収益的収入及び支出": {"収入": [], "支出": []},
                       "資本的収入及び支出": {"収入": [], "支出": []}}
                out.append(cur)
                sec = side = None
            elif cur is not None and re.search(r"キャッシュ|給与費明細書|貸借対照表|損益計算書", text):
                cur = None
            if cur is None:
                continue
            for row in rows_of(page):
                joined = "".join(w["text"] for w in row)
                if "収益的収入及び支出" in joined or "収益的収入及支出" in joined:
                    sec = "収益的収入及び支出"
                    continue
                if "資本的収入及び支出" in joined or "資本的収入及支出" in joined:
                    sec = "資本的収入及び支出"
                    continue
                if joined in ("収入",):
                    side = "収入"
                    continue
                if joined in ("支出", "支", "出"):
                    side = "支出"  # 「支出」の見出しは「出」と「支」が上下にずれて別の行になることがある
                    continue
                hdr = {w["text"]: w["x0"] for w in row if w["text"] in ("款", "項", "目")}
                if len(hdr) == 3:
                    anchors = hdr
                    continue
                if sec is None or side is None or anchors is None:
                    continue
                # 金額 0 は「〇」と印字され、文字層では「゜」になって列から少しはみ出す（電気事業会計の資本的収入、p204）。
                # 0 とみなしたものは予算書の本体の 0 と照合して確かめる
                zero = ("〇", "○", "゜")
                frags = [dict(w, text="0") if w["text"] in zero else w for w in row
                         if (re.fullmatch(r"[\d,]+", w["text"]) and 500 <= w["x0"] and w["x1"] <= 675)
                         or (w["text"] in zero and 500 <= w["x0"] and w["x1"] <= 695)]
                lead = row[0]
                mno = re.fullmatch(r"\d{1,2}", lead["text"])
                if not mno:
                    lst = cur[sec][side]
                    last = _last(lst)
                    if frags and last is not None:
                        # 番号のない行の金額＝前の行の金額の分断された続き（「1 / ,46 / 1」の後半）
                        last["_frag"] += "".join(w["text"] for w in frags)
                    namepart = "".join(w["text"] for w in row if w not in frags and 150 <= w["x0"] < 500)
                    if namepart and not frags:
                        # 2行に分かれた名前は「上の行／番号と金額だけの行／下の行」と並ぶ（病院事業「支払利息及び／企業債取扱諸費」）。
                        # 上の行は次の番号の行へ回し、下の行はその番号の行に足す
                        if last is not None and last.get("_name_open"):
                            last["name"] += namepart
                            last["_name_open"] = False
                        elif last is not None and not last["name"]:
                            last["name"] = namepart
                        else:
                            pending_name = namepart
                    continue
                x = lead["x0"]
                level = "款" if x < (anchors["款"] + anchors["項"]) / 2 else ("項" if x < (anchors["項"] + anchors["目"]) / 2 else "目")
                name = "".join(w["text"] for w in row[1:] if w not in frags and w["x0"] < 500)
                name_open = False
                if pending_name:
                    name_open = not name  # 番号の行に名前がなければ、下の行が続く
                    name = pending_name + name
                    pending_name = ""
                lst0 = _last(cur[sec][side])
                if lst0 is not None:
                    lst0.pop("_name_open", None)
                rec = {"no": int(lead["text"]), "name": name, "_frag": "".join(w["text"] for w in frags), "pdf_page": pno,
                       "_name_open": name_open}
                lst = cur[sec][side]
                if level == "款":
                    lst.append({**rec, "項": []})
                elif level == "項" and lst:
                    lst[-1]["項"].append({**rec, "目": []})
                elif level == "目" and lst and lst[-1]["項"]:
                    lst[-1]["項"][-1]["目"].append(rec)
                else:
                    fail(f"p{pno}: 親のない{level}の行「{joined}」")
    # 金額の確定と検算
    for k in out:
        for sec in ("収益的収入及び支出", "資本的収入及び支出"):
            for side in ("収入", "支出"):
                for kan in k[sec][side]:
                    for node in [kan] + kan["項"] + [mo for kou in kan["項"] for mo in kou["目"]]:
                        node.pop("_name_open", None)
                        f = node.pop("_frag")
                        node["金額"] = int(f.replace(",", "")) if AMT.match(f) else None
                        if node["金額"] is None:
                            fail(f"{k['会計']} {sec} {side} p{node['pdf_page']}: 金額が読めない「{f}」（{node['name']}）")
                    for kou in kan["項"]:
                        if kou["目"]:
                            s = sum(mo["金額"] or 0 for mo in kou["目"])
                            if s != kou["金額"]:
                                fail(f"{k['会計']} {sec} {side} {kou['name']}: 目の合計 {s:,} / 項 {kou['金額']}")
                    s = sum(kou["金額"] or 0 for kou in kan["項"])
                    if s != kan["金額"]:
                        fail(f"{k['会計']} {sec} {side} {kan['name']}: 項の合計 {s:,} / 款 {kan['金額']}")
                # 予算書の本体と照合（第3条＝収益的、第4条＝資本的）
                art = "3" if sec.startswith("収益的") else "4"
                ref = yo.get(k["会計"], {}).get("条", {}).get(art, {}).get(side, [])
                got = [(kan["金額"], [kou["金額"] for kou in kan["項"]]) for kan in k[sec][side]]
                want = [(kan["金額"], [kou["金額"] for kou in kan["項"]]) for kan in ref]
                if got != want:
                    fail(f"{k['会計']} {sec} {side}: 予算書と不一致 説明書 {got} / 予算書 {want}")
        n_moku = sum(len(kou["目"]) for sec in ("収益的収入及び支出", "資本的収入及び支出") for side in ("収入", "支出")
                     for kan in k[sec][side] for kou in kan["項"])
        print(f"{k['会計']}: 目 {n_moku} 件（p{k['pdf_page']}〜）", file=sys.stderr)
    print(f"会計 {len(out)} 件、FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "千円", "会計": out}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


def _last(lst):
    """款・項・目のうち最後に追加した節点。"""
    if not lst:
        return None
    kan = lst[-1]
    if kan["項"]:
        kou = kan["項"][-1]
        return kou["目"][-1] if kou["目"] else kou
    return kan


if __name__ == "__main__":
    main()
