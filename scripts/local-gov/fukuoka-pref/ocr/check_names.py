"""予算説明書の OCR 結果（parse_setsumeisho.py の出力）の名称を、テキスト PDF 由来の資料と突き合わせる。

金額は検算で正しさを確かめられるが、名称（款名・目名・事項名）は確かめられない。そこで別の資料と照合する。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/check_names.py <setsumeisho.json> <keijougaku.json> <kessan-kmk.json> \
        <shisaku.json> > names-report.json

照合の方法:
- 款名: 計上額調（同じ年度・テキスト）の款名と、款番号で照合する。完全一致を期待する
- 目名: 決算の款項目別明細表（前々年度・テキスト）の同じ款の目の中で、最も近い名前を探す。
  目番号は年度で変わる（R6 の 2款1項3目「広報費」が R8 では「文書費」）ので番号では引かない。
  目の新設・廃止があるので「近い名前がない」こと自体は誤りとは限らない
- 説明欄の事項名: 施策別資料（同じ年度・テキスト）の事項は「科目（款 項 目）」と予算額を持つ。
  同じ科目で金額の一致する事項があれば、その事項名を正しい名称とみなす。
  同じ金額の事項が同じ目に複数あるときは名前の近さで選ぶ
  施策別資料の事項が OCR 側のどの目にも見つからない場合は、OCR の目番号・項番号の付け方の誤りを疑う
結果: 各項目に「参照名」と一致の種類を付けて出力し、stderr に集計を出す。
"""
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict


def key_name(s: str) -> str:
    """比較用の正規化: 全角半角・空白・○などの記号を除く。"""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s○〇・･、，,.。()（）「」\-－―ー]", "", s)


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, key_name(a), key_name(b)).ratio()


def main():
    setsu = json.load(open(sys.argv[1], encoding="utf-8"))
    keijou = json.load(open(sys.argv[2], encoding="utf-8"))
    kmk = json.load(open(sys.argv[3], encoding="utf-8"))
    shisaku = json.load(open(sys.argv[4], encoding="utf-8"))["items"]
    stat = Counter()
    report = {"款": [], "目": [], "事項": [], "施策別資料で見つからない事項": []}

    # 款名
    kan_names = {("歳入", k["no"]): k["款名"] for k in keijou["一般会計歳入"]["款"]}
    kan_names.update({("歳出", k["no"]): k["款名"] for k in keijou["一般会計歳出"]["款"]})

    # 目名の参照（R6 決算。款ごと）
    r6 = defaultdict(list)
    for side, key in (("歳入", "revenue"), ("歳出", "expense")):
        for kan in kmk[key]:
            for kou in kan["children"]:
                for mo in kou["children"]:
                    r6[(side, kan["no"])].append(mo["name"])

    moku = [m for m in setsu if m["kind"] == "目" and m.get("会計", "一般会計") == "一般会計"]
    for m in moku:
        side, kan = m["side"], m["款"]
        cands = r6.get((side, kan), [])
        best = max(cands, key=lambda n: sim(n, m["目名"]), default=None)
        s = sim(best, m["目名"]) if best else 0.0
        kind = "一致" if best and key_name(best) == key_name(m["目名"]) else ("近い" if s >= 0.6 else "なし")
        stat[f"目名 {kind}"] += 1
        report["目"].append({"款": kan, "項": m["項"], "目番号": m["目番号"], "目名": m["目名"], "参照名": best,
                            "近さ": round(s, 2), "種類": kind, "pages": m["pages"]})

    # 事項名（歳出のみ。施策別資料は歳出の事項）
    by_kamoku = defaultdict(list)
    for it in shisaku:
        for k in it["科目"]:
            nums = tuple(int(x) for x in re.findall(r"\d+", unicodedata.normalize("NFKC", k)))
            # 施策別資料の科目は「2」だけのように欠けていることがある（同じ科目が続く行で省略される・抽出の限界）。
            # 欠けたものは前方一致で引く
            if 1 <= len(nums) <= 3:
                by_kamoku[nums].append(it)
    used = set()
    for m in moku:
        if m["side"] != "歳出" or m["目番号"] is None or not m["項"]:
            continue
        k = (m["款"], m["項"][0], m["目番号"])
        pool = by_kamoku.get(k, []) + by_kamoku.get(k[:2], []) + by_kamoku.get(k[:1], [])
        for e in m["説明"]:
            same = [it for it in pool if it["予算額"] == e["amount"] and id(it) not in used]
            if not same:
                continue
            it = max(same, key=lambda it: sim(it["事項名"], e["name"]))
            used.add(id(it))
            exact = key_name(it["事項名"]) == key_name(e["name"])
            stat["事項 金額一致・名前一致" if exact else "事項 金額一致・名前違い"] += 1
            if not exact:
                report["事項"].append({"科目": k, "OCR": e["name"], "参照名": it["事項名"], "金額": e["amount"],
                                       "近さ": round(sim(it["事項名"], e["name"]), 2), "pages": m["pages"]})
    # 施策別資料の事項のうち、OCR 側の同じ科目の目に同じ金額がなかったもの
    ocr_amounts = defaultdict(set)
    for m in moku:
        if m["side"] == "歳出" and m["目番号"] is not None and m["項"]:
            ocr_amounts[(m["款"], m["項"][0], m["目番号"])].update(e["amount"] for e in m["説明"])
    for k, items in by_kamoku.items():
        for it in items:
            if id(it) in used:
                continue
            # 施策別資料の事項は説明書の事項の一部（内訳）であることも多い。金額が見つからないだけでは誤りではない
            stat["施策別資料の事項 未対応"] += 1
            report["施策別資料で見つからない事項"].append({"科目": k, "事項名": it["事項名"], "予算額": it["予算額"],
                                                     "OCR の目がある": any(x[:len(k)] == k for x in ocr_amounts)})
    stat["施策別資料の事項 未対応（OCR に同じ科目の目がない）"] = sum(
        1 for r in report["施策別資料で見つからない事項"] if not r["OCR の目がある"])

    # 款名（説明書の見出しの款名は parse の出力にないので、目の款番号の範囲だけ確認する）
    for (side, no), name in sorted(kan_names.items()):
        n = sum(1 for m in moku if m["side"] == side and m["款"] == no)
        report["款"].append({"side": side, "款": no, "款名": name, "目の数": n})
        if n == 0:
            stat["款 目が1つもない"] += 1

    for k, v in sorted(stat.items()):
        print(f"{k}: {v}", file=sys.stderr)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
