"""説明欄の事項の金額を、説明書とは別に作られた資料の金額で裏付ける。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/confirm_external.py <採用した結果.json> <shisaku.json> <行政評価 items.json> \
        > confirm-external.json

照合先:
- 施策別資料（編成概要、テキスト PDF）: 事項ごとに科目（款 項 目）と予算額。同じ科目（欠けた科目は前方一致）の目の中で金額が一致
- 行政評価（事務事業評価、構造化済み。mirai-gikai-fukuoka-pref の docs/data/jimu-jigyo/r7/items.json）:
  事業ごとに「R8当初」の歳出。科目がないので、金額が一致し、かつ名前が似ている（近さ 0.5 以上）事項
どちらも説明書とは別の担当・別の様式で作られた数字なので、一致すれば OCR・文字層とは独立した裏付けになる。
名前がよく似ている（近さ 0.8 以上）のに金額が違うものは「要確認」として出す
（読み取りの誤りか、資料ごとの範囲の違い。行政評価の事業は説明書の事項の一部や複数の事項の合計のことがある）。
"""
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict


def key_name(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s○〇・･、，,.。()（）「」\-－―ー]|[\d,]+人$", "", s)


def sim(a, b):
    return difflib.SequenceMatcher(None, key_name(a), key_name(b)).ratio()


def main():
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    ms = [m for m in (d["目"] if isinstance(d, dict) else d) if m["kind"] == "目" and m["side"] == "歳出"
          and m.get("会計", "一般会計") == "一般会計"]
    shisaku = json.load(open(sys.argv[2], encoding="utf-8"))["items"]
    hyoka = json.load(open(sys.argv[3], encoding="utf-8"))
    by_kamoku = defaultdict(list)
    for it in shisaku:
        for k in it["科目"]:
            nums = tuple(int(x) for x in re.findall(r"\d+", unicodedata.normalize("NFKC", k)))
            if 1 <= len(nums) <= 3:
                by_kamoku[nums].append(it)
    hy = []
    for it in hyoka:
        r8 = (((it.get("事業費") or {}).get("年度別") or {}).get("R8当初") or {}).get("歳出")
        if isinstance(r8, int):
            hy.append((it["事業名"], r8, it.get("課室")))
    stat = Counter()
    out = {"裏付けあり": [], "要確認": []}
    for m in ms:
        k = (m["款"], m["項"][0], m["目番号"])
        pool = by_kamoku.get(k, []) + by_kamoku.get(k[:2], []) + by_kamoku.get(k[:1], [])
        for e in m["説明"]:
            if e.get("内訳") or e.get("金額の記載なし"):
                continue
            stat["事項"] += 1
            src = []
            if any(it["予算額"] == e["amount"] for it in pool):
                src.append("施策別資料")
            if any(a == e["amount"] and sim(n, e["name"]) >= 0.5 for n, a, _ in hy):
                src.append("行政評価")
            if src:
                stat["裏付けあり"] += 1
                for s in src:
                    stat[f"裏付け {s}"] += 1
                out["裏付けあり"].append({"科目": k, "事項": e["name"], "金額": e["amount"], "出典": src})
            for n, a, ka in hy:
                if a != e["amount"] and sim(n, e["name"]) >= 0.8:
                    stat["要確認"] += 1
                    out["要確認"].append({"科目": k, "事項": e["name"], "説明書": e["amount"], "行政評価": a,
                                        "行政評価の事業名": n, "課室": ka, "pages": m["pages"]})
    for k in ("事項", "裏付けあり", "裏付け 施策別資料", "裏付け 行政評価", "要確認"):
        print(f"{k}: {stat[k]}", file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
