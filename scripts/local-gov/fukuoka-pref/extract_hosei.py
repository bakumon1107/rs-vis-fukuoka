"""福岡県の補正予算の議案（第1表・別表「歳入歳出予算補正」）と説明書の総括から、款・項の補正前の額・補正額・計を抽出する。

テキストの PDF（R8 の 6月第1号・8月専決・9月追加提案）を読む。画像の PDF（9月第3号）は OCR の結果から別に作る。
設計: docs/local-gov/tasks/20261114_1317_R8補正予算の抽出の設計.md

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_hosei.py --id R8-06-1 --kind 定例 \
        [--gian <議案.pdf>] --setsumeisho <説明書.pdf> > hosei-R8-06-1.json

出力（金額は千円。印字のまま）:
    {"id", "kind", "gian": {"追加額", "総額", "歳入": [款…], "歳出": [款…]} | null,
     "総括": {"歳入": [款…], "歳出": [款…], "歳入合計", "歳出合計"}}
    款: {"no", "name", "補正前", "補正額", "計", "項": [{"no", "name", "補正前", "補正額", "計"}]}（総括の款は項なし）

検算（完全一致。FAIL で終了コード 1）:
- 行ごとに 補正前 + 補正額 = 計（議案の款・項、総括の款・合計）
- 議案: 項の補正額の合計 = 款の補正額（議案の表には補正のある項だけが載る。補正前・計は款の全体なので項から足せない）、
  款の補正額の合計 = 合計の行 = 第1条の追加額、合計の計 = 第1条の総額、歳入の合計 = 歳出の合計
- 総括: 款の合計 = 合計の行（補正前・補正額・計とも）、歳入の合計 = 歳出の合計
- 議案と総括: 議案に載った款の補正前・補正額・計 = 総括の同じ款
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata

NUM = r"[△▲\-]?[\d,]+"
ROW_RE = re.compile(rf"^(?P<indent>\s*)(?P<no>\d+)\s+(?P<name>.+?)\s+(?P<a>{NUM})\s+(?P<b>{NUM})\s+(?P<c>{NUM})(?P<rest>(?:\s+{NUM})*)\s*$")
TOTAL_RE = re.compile(rf"^\s*歳\s*(?P<side>入|出)\s*合\s*計\s+(?P<a>{NUM})\s+(?P<b>{NUM})\s+(?P<c>{NUM})")


def to_int(s: str) -> int:
    s = s.replace(",", "")
    return -int(s[1:]) if s[:1] in "△▲-" else int(s)


def flat(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def text_of(pdf: str) -> str:
    return subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout


def side_of(line: str) -> str | None:
    """「歳 入」「（歳 出）」の見出しの行なら、どちらの表か。総括では同じ行に「（単位：千円）」が続く。"""
    m = re.match(r"^[（(]?歳(入|出)[）)]?(?:[（(]単位:千円[）)])?$", flat(line))
    return ("歳入" if m.group(1) == "入" else "歳出") if m else None


ARTICLE1 = re.compile(r"第1条歳入歳出予算の総額に歳入歳出それぞれ([\d,]+)千円を(追加|減額)し、歳入歳出予算の総額を歳入歳出それぞれ([\d,]+)千円とする")


def article1(body: str) -> tuple[int | None, int | None]:
    """第1条の追加額（減額は負）と補正後の総額（千円）。読めなければ (None, None)"""
    m = ARTICLE1.search(body)
    if not m:
        return None, None
    return to_int(m.group(1)) * (1 if m.group(2) == "追加" else -1), to_int(m.group(3))


def parse_gian(text: str, fails: list[str]):
    """議案の第1条と第1表（別表）。"""
    add, total = article1(flat(text))
    if add is None:
        fails.append("議案: 第1条の追加額・総額が読めない")
    out = {"追加額": add, "総額": total, "歳入": [], "歳出": [], "合計": {}}
    side, in_table = None, False
    for ln in text.splitlines():
        if "歳入歳出予算補正" in flat(ln) and ("第1表" in flat(ln) or "別表" in flat(ln)):
            in_table = True
            continue
        if not in_table:
            continue
        if flat(ln).startswith("第2表") or flat(ln).startswith("第3表"):
            break
        s = side_of(ln)
        if s:
            side = s
            continue
        t = TOTAL_RE.match(ln)
        if t:
            out["合計"][t.group("side") == "入" and "歳入" or "歳出"] = {k: to_int(t.group(x)) for k, x in
                                                                     (("補正前", "a"), ("補正額", "b"), ("計", "c"))}
            continue
        r = ROW_RE.match(ln)
        if not r or side is None:
            continue
        rec = {"no": int(r.group("no")), "name": flat(r.group("name")),
               **{k: to_int(r.group(x)) for k, x in (("補正前", "a"), ("補正額", "b"), ("計", "c"))}}
        # 款は左端から、項は大きく字下げされて印字される（R8 の議案で款は 0〜1 字、項は 30 字以上）
        if len(r.group("indent")) >= 10:
            if not out[side]:
                fails.append(f"議案 {side}: 款より前に項がある {flat(ln)[:30]}")
                continue
            out[side][-1]["項"].append(rec)
        else:
            out[side].append({**rec, "項": []})
    return out


def parse_soukatsu(text: str, fails: list[str]):
    """説明書の「1 総括」（歳入・歳出の款ごとの 補正前の額・補正額・計）。歳出は財源内訳の4列が続く。"""
    out = {"歳入": [], "歳出": [], "合計": {}}
    side, started = None, False
    for ln in text.splitlines():
        f = flat(ln)
        if "歳入歳出補正予算事項別明細書" in f and not started:
            started = True
        if not started:
            continue
        s = side_of(ln)
        if s:
            if out[s] and s in out["合計"]:
                break  # 総括の後の「2 歳入」以降の表
            side = s
            continue
        t = TOTAL_RE.match(ln)
        if t:
            key = "歳入" if t.group("side") == "入" else "歳出"
            out["合計"][key] = {k: to_int(t.group(x)) for k, x in (("補正前", "a"), ("補正額", "b"), ("計", "c"))}
            if key == "歳出":
                break
            continue
        r = ROW_RE.match(ln)
        if not r or side is None:
            continue
        rec = {"no": int(r.group("no")), "name": flat(r.group("name")),
               **{k: to_int(r.group(x)) for k, x in (("補正前", "a"), ("補正額", "b"), ("計", "c"))}}
        if side == "歳出":
            rest = [to_int(x) for x in re.findall(NUM, r.group("rest"))]
            if len(rest) == 4:
                rec["財源"] = dict(zip(("国支出金", "地方債", "その他", "一般財源"), rest))
            else:
                fails.append(f"総括 歳出 {rec['no']}款: 財源内訳の列が {len(rest)} 個")
        out[side].append(rec)
    return out


# 画像の議案（9月第3号 298929）の文字層の列。金額の語の右端（pt。ページ幅 842）で列を決める
SCAN_COLS = {"補正前": (480, 560), "補正額": (600, 700), "計": (720, 830)}
SCAN_KAN_X1 = (55, 100)    # 款の番号の右端
SCAN_KOU_X1 = (230, 255)   # 項の番号の右端


def parse_gian_scan(pdf: str, prev_sk: dict, fails: list[str]):
    """画像の議案の文字層（発行元が付けた OCR 層）から第1表を読む。名前の字は崩れているので使わない（款・項の名前は総括・当初予算から）。
    金額は列ごとに語をつなぐ（「10,818,」「528」に割れる・カンマを「.」と読む）。款の番号が読めない行は、前の回の総括で
    「計」が補正前の額と一致する款に決める（R8 9月第3号の国庫支出金の行は番号が「，」）。"""
    import pdfplumber
    from collections import defaultdict

    out = {"追加額": None, "総額": None, "歳入": [], "歳出": [], "合計": {}, "source": "scan"}
    side = None
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages:
            ws = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            text = flat("".join(w["text"] for w in ws))
            if out["追加額"] is None:
                # 第1条はテキストの議案と同じ文で、文字層でも崩れずに読める（R8 9月第3号）。総額も取り、表の合計と照合する
                out["追加額"], out["総額"] = article1(text)
            rows = defaultdict(list)
            for w in ws:
                rows[round(w["top"] / 6)].append(w)
            for k in sorted(rows):
                r = sorted(rows[k], key=lambda w: w["x0"])
                f = flat("".join(w["text"] for w in r))
                if f in ("歳入", "歳出"):
                    side = f
                    continue
                vals = {}
                for c, (lo, hi) in SCAN_COLS.items():
                    s = "".join(w["text"] for w in r if lo <= w["x1"] <= hi).replace(".", ",")
                    # 減額は数字の左に離れて △ が印字される（語の右端が列の範囲より左に来る）。列の左 80pt までの △ を符号にする
                    neg = s[:1] in "△▲" or any(w["text"].strip() in ("△", "▲") and lo - 80 <= w["x1"] < lo for w in r)
                    s = s.lstrip("△▲")
                    if re.fullmatch(r"[\d,]+", s or "-"):
                        vals[c] = -to_int(s) if neg else to_int(s)
                if len(vals) != 3 or side is None:
                    continue
                if f.startswith(f"{side}合計"):
                    out["合計"][side] = vals
                    if side == "歳出":
                        return out  # 第1表の終わり（この後は債務負担行為・地方債・繰越明許費の表）
                    continue
                kan_no = next((int(w["text"]) for w in r if w["text"].isdigit() and SCAN_KAN_X1[0] <= w["x1"] <= SCAN_KAN_X1[1]), None)
                kou_no = next((int(w["text"]) for w in r if w["text"].isdigit() and SCAN_KOU_X1[0] <= w["x1"] <= SCAN_KOU_X1[1]), None)
                if kou_no is not None:
                    if not out[side]:
                        fails.append(f"議案（画像） {side}: 款より前に項がある")
                        continue
                    out[side][-1]["項"].append({"no": kou_no, "name": None, **vals})
                    continue
                if kan_no is None:
                    cands = [x["no"] for x in prev_sk[side] if x["計"] == vals["補正前"]]
                    if len(cands) != 1:
                        fails.append(f"議案（画像） {side}: 番号の読めない款の行（補正前 {vals['補正前']:,}）の款が {len(cands)} 通り")
                        continue
                    kan_no = cands[0]
                out[side].append({"no": kan_no, "name": None, **vals, "項": []})
    return out


def derive_soukatsu(prev_sk: dict, gian: dict) -> dict:
    """総括が画像で読めない回の総括を、前の回の総括の「計」と議案の款の補正額から作る（議案に載らない款は補正額 0）。
    歳出の財源内訳は議案にないので持たない。議案の款の補正前 = 前の回の計 は verify_chain で確かめる。"""
    out = {"歳入": [], "歳出": [], "合計": {}, "derived": True}
    for side in ("歳入", "歳出"):
        changed = {k["no"]: k for k in gian[side]}
        for p in prev_sk[side]:
            add = changed[p["no"]]["補正額"] if p["no"] in changed else 0
            out[side].append({"no": p["no"], "name": p["name"], "補正前": p["計"], "補正額": add, "計": p["計"] + add})
        out["合計"][side] = {c: sum(k[c] for k in out[side]) for c in ("補正前", "補正額", "計")}
    return out


def verify(gian, sk, fails: list[str]):
    def row_ok(where, r):
        if r["補正前"] + r["補正額"] != r["計"]:
            fails.append(f"{where}: 補正前 {r['補正前']:,} + 補正額 {r['補正額']:,} ≠ 計 {r['計']:,}")

    for side in ("歳入", "歳出"):
        for k in sk[side]:
            row_ok(f"総括 {side} {k['no']}款 {k['name']}", k)
            if "財源" in k and sum(k["財源"].values()) != k["補正額"]:
                fails.append(f"総括 {side} {k['no']}款: 財源内訳の合計 {sum(k['財源'].values()):,} ≠ 補正額 {k['補正額']:,}")
        tot = sk["合計"].get(side)
        if tot is None:
            fails.append(f"総括 {side}: 合計の行がない")
            continue
        row_ok(f"総括 {side} 合計", tot)
        for c in ("補正前", "補正額", "計"):
            s = sum(k[c] for k in sk[side])
            if s != tot[c]:
                fails.append(f"総括 {side} {c}: 款の合計 {s:,} ≠ 合計の行 {tot[c]:,}")
    if sk["合計"].get("歳入") and sk["合計"].get("歳出") and sk["合計"]["歳入"] != sk["合計"]["歳出"]:
        fails.append("総括: 歳入の合計 ≠ 歳出の合計")
    if gian is None:
        return
    for side in ("歳入", "歳出"):
        for k in gian[side]:
            row_ok(f"議案 {side} {k['no']}款", k)
            for kou in k["項"]:
                row_ok(f"議案 {side} {k['no']}款{kou['no']}項", kou)
            s = sum(x["補正額"] for x in k["項"])
            if s != k["補正額"]:
                fails.append(f"議案 {side} {k['no']}款: 項の補正額の合計 {s:,} ≠ 款の補正額 {k['補正額']:,}")
            ref = next((x for x in sk[side] if x["no"] == k["no"]), None)
            if ref is None or any(ref[c] != k[c] for c in ("補正前", "補正額", "計")):
                fails.append(f"議案 {side} {k['no']}款: 総括と合わない")
        tot = gian["合計"].get(side)
        if tot is None:
            fails.append(f"議案 {side}: 合計の行がない")
            continue
        if sum(k["補正額"] for k in gian[side]) != tot["補正額"]:
            fails.append(f"議案 {side}: 款の補正額の合計 ≠ 合計の行")
        if gian["追加額"] is not None and tot["補正額"] != gian["追加額"]:
            fails.append(f"議案 {side}: 合計の補正額 {tot['補正額']:,} ≠ 第1条の追加額 {gian['追加額']:,}")
        if gian["総額"] is not None and tot["計"] != gian["総額"]:
            fails.append(f"議案 {side}: 合計の計 {tot['計']:,} ≠ 第1条の総額 {gian['総額']:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="回の id（例 R8-06-1）")
    ap.add_argument("--kind", required=True, choices=["定例", "追加提案", "専決"])
    ap.add_argument("--gian", help="議案の PDF（専決は議案がない）")
    ap.add_argument("--setsumeisho", help="補正予算に関する説明書の PDF（テキスト）")
    ap.add_argument("--gian-scan", help="画像の議案の PDF（文字層を読む。総括は前の回から作る。--prev が要る）")
    ap.add_argument("--prev", help="前の回の出力（JSON）。画像の議案の款の番号の補いと総括の組み立てに使う")
    a = ap.parse_args()
    fails: list[str] = []
    if a.gian_scan:
        if not a.prev:
            sys.exit("--gian-scan には --prev が要る")
        with open(a.prev, encoding="utf-8") as f:
            prev_sk = json.load(f)["総括"]
        gian = parse_gian_scan(a.gian_scan, prev_sk, fails)
        sk = derive_soukatsu(prev_sk, gian)
        if gian["追加額"] is None:
            fails.append("議案（画像）: 第1条の追加額・総額が読めない")
    else:
        if not a.setsumeisho:
            sys.exit("--setsumeisho が要る")
        gian = parse_gian(text_of(a.gian), fails) if a.gian else None
        sk = parse_soukatsu(text_of(a.setsumeisho), fails)
    verify(gian, sk, fails)
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    tot = sk["合計"].get("歳出") or {}
    print(f"{a.id}: 総括の款 歳入 {len(sk['歳入'])}・歳出 {len(sk['歳出'])}、補正額 {tot.get('補正額', 0):,} 千円、"
          f"補正後 {tot.get('計', 0):,} 千円" + (f"、議案の款 歳入 {len(gian['歳入'])}・歳出 {len(gian['歳出'])}" if gian else "（議案なし）"),
          file=sys.stderr)
    print(f"FAIL={len(fails)}", file=sys.stderr)
    json.dump({"id": a.id, "kind": a.kind, "gian": gian, "総括": sk}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
