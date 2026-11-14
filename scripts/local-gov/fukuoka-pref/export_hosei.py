"""R8 補正予算を回ごとの共通 JSON 形式（budget-2026-supplementary-<回>.json）に組み立てる。

設計: docs/local-gov/tasks/20261114_1317_R8補正予算の抽出の設計.md（8章: 回ごとにファイルを分ける）、共通 JSON 形式の設計（basis supplementary）
入力（作業ディレクトリ）: 回ごとに
- hosei-<回>.json … extract_hosei.py の出力（議案・総括）
- setsumeisho-hosei-<回>.json … parse_setsumeisho.py --hosei の出力（目の明細）
と、当初予算の公開データ（目の ID・款項の名前をそろえる）。

行は補正のある目だけ（差分）。amount = 補正額、before = 補正前の額、after = 計。目の ID は当初と同じ（補正で新しく設けた目は新しい番号）。
款・項の名前は当初の名前（出典も当初のまま）。目の名前は、当初にある目は当初の名前、補正で新しく設けた目は説明書の名前。
検算: 目ごとの検算（parse_setsumeisho の A〜D）と、目の補正額の合計 = 総括の款の補正額（歳入・歳出の全部の款）。
"""
import difflib
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kessan_common import SETSU_NAMES  # noqa: E402

YEAR, YEAR_LABEL = 2026, "令和8年度"
# 回の一覧（古い順）。id は extract_hosei.py の --id、src は説明書の資料 id（sources.json）、text は説明書がテキストか
ROUNDS = [
    {"id": "R8-06-1", "round": "6月補正（第1号）", "kind": "定例", "bill_no": "第120号議案", "src": "r8-hosei-06-setsumeisho", "text": True},
    {"id": "R8-08-2", "round": "8月専決補正（第2号）", "kind": "専決", "bill_no": None, "src": "r8-hosei-08-setsumeisho", "text": True},
    {"id": "R8-09-3", "round": "9月補正（第3号）", "kind": "定例", "bill_no": "第122号議案", "src": "r8-hosei-09-3-setsumeisho", "text": False},
    {"id": "R8-09-4", "round": "9月補正（第4号・追加提案）", "kind": "追加提案", "bill_no": "第158号議案", "src": "r8-hosei-09-4-setsumeisho", "text": True},
]
SIDE = {"歳入": "revenue", "歳出": "expense"}
FUND = {"国庫支出金": "national", "地方債": "bond", "その他": "other", "一般財源": "general"}
# 画像の回の名前の修正表（画像で確かめた名前。形式は表の「説明」）
NAME_CORRECTIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr", "corrections", "r8-hosei-names.json")


def apply_name_corrections(rid: str, rows: list[dict], fixes: list[dict], fails: list[str]) -> None:
    """その回の修正を当てる。1件に当たらない・今の名前が was と違うものは FAIL（黙って当てずに済ませない）"""
    by_id = {x["id"]: x for x in rows}
    for fx in fixes:
        if fx["round"] != rid:
            continue
        r = by_id.get(fx["id"])
        amt = fx["amount"] * 1000
        if r is None:
            hits = []
        elif fx["level"] == "item":
            hits = [i for i in r.get("items", []) if i["amount"]["v"] == amt]
        elif fx["level"] == "setsu":
            hits = [s for s in r.get("setsu", []) if s["amount"]["v"] == amt]
        elif fx["level"] == "sub":
            hits = [x for s in r.get("setsu", []) if s["no"] == fx["no"] for x in s.get("sub", []) if x["amount"]["v"] == amt]
        else:
            fails.append(f"{rid} 名前の修正表: 知らない level {fx['level']}")
            continue
        if len(hits) != 1 or hits[0]["name"] != fx["was"]:
            fails.append(f"{rid} 名前の修正表: {fx['id']} {fx['level']} {fx['amount']:,}「{fx['was']}」に当たるものが "
                         f"{len(hits)} 件（今の名前 {[h['name'] for h in hits]}）")
            continue
        hits[0]["name"], hits[0]["name_src"] = fx["name"], "correction"


def yen(v):
    return None if v is None else int(v) * 1000


def val(v, src):
    return {"v": yen(v), "src": src}


def norm_name(s: str) -> str:
    """名前の比較用（全角半角・小書きの「ょ」と並字の「よ」をそろえる。「橋りよう」と「橋りょう」）"""
    return unicodedata.normalize("NFKC", s).replace("よ", "ょ").replace("ゃ", "や").replace("舖", "舗")


def clean(s: str) -> str:
    # 減額の事項は金額の左に △ が印字され、OCR は名前の末尾に読み込むことがある（R8 9月第3号「堰堤改良費補助金△」）。
    # 金額の符号は文字層の △ で付けてある（mark_negatives.py）ので、名前からは除く
    return re.sub(r"[△▲]+$", "", re.sub(r"^○", "", (s or "").strip())).strip()


def build_round(r: dict, gian_sk: dict, parsed: list[dict], initial: dict, fails: list[str]):
    src = "text" if r["text"] else "ocr"
    init_rows = {x["id"]: x for x in initial["rows"]}
    kan_name = {(x["side"], x["kan"]["no"]): x["kan"] for x in initial["rows"] if x["account"] == "general"}
    kou_name = {(x["side"], x["kan"]["no"], x["kou"]["no"]): x["kou"] for x in initial["rows"] if x["account"] == "general"}
    rows, all_ok = [], 0
    for m in parsed:
        if m.get("kind") != "目":
            continue
        if m.get("会計") != "一般会計":
            # 特別会計の補正は、まだ書き出しの対象にしていない（R8 の4回は一般会計だけ）。黙って捨てず止める
            fails.append(f"{r['id']}: 特別会計の目がある（{m.get('会計')} {m.get('目名')}）。特別会計の補正の書き出しは未対応")
            continue
        side = SIDE[m["side"]]
        kou_no = (m["項"] or [None])[0]
        rid = f"general/{side}/{m['款']}-{kou_no}-{m['目番号']}"
        if m["目番号"] is None or kou_no is None:
            fails.append(f"{r['id']}: 目・項の番号が読めない目 {m['目名']}")
            continue
        base = init_rows.get(rid)
        new_moku = m["前年度"] == 0 and m.get("空欄を0とみなした") == "前年度"
        if base is not None and new_moku:
            # 補正で新しく設けた目（補正前が空欄）なのに、当初に同じ ID の目がある＝番号の読み違いか ID の取り違え。
            # 足すと別の目の補正後の額になるので止める（前年度のみの目の ID を p<n> にする前は、R8 8月専決で起きた）
            fails.append(f"{r['id']} {rid}: 補正で新設の目「{clean(m['目名'])}」が当初の目「{base['moku']['name']}」と ID がぶつかる")
            continue
        if base is not None and clean(m["目名"]):
            # 名前で当初の目と同じかを確かめる（ID は読んだ目番号から作るので、番号の読み違いで別の目に足さないため）。
            # 字形の違い（りよう／りょう、OCR の崩れ）は許し、似ていなければ止める
            a, b = norm_name(clean(m["目名"])), norm_name(base["moku"]["name"])
            if a != b:
                ratio = difflib.SequenceMatcher(None, a, b).ratio()
                if ratio < 0.6:
                    fails.append(f"{r['id']} {rid}: 目の名前が当初と違う（当初「{base['moku']['name']}」/ 補正「{clean(m['目名'])}」）")
                    continue
                print(f"WARN {r['id']} {rid}: 目の名前 当初「{base['moku']['name']}」/ 補正の説明書「{clean(m['目名'])}」"
                      f"（似ている {ratio:.2f}。当初の名前を使う）", file=sys.stderr)
        kan = kan_name.get((side, m["款"]))
        kou = kou_name.get((side, m["款"], kou_no))
        if kan is None or kou is None:
            fails.append(f"{r['id']} {rid}: 当初にない款・項")
            continue
        moku = dict(base["moku"]) if base is not None else {"no": m["目番号"], "name": clean(m["目名"]), "name_src": src}
        row = {"id": rid, "account": "general", "side": side, "kan": kan, "kou": kou, "moku": moku,
               "amount": val(m["本年度"], src), "before": val(m["前年度"], "blank-as-zero" if m.get("空欄を0とみなした") == "前年度" else src),
               "after": val(m["比較"], src)}
        if side == "expense":
            row["funding"] = {FUND[k]: val(v, src) for k, v in m["財源"].items()}
        items = [{"name": clean(e["name"]), "name_src": src, "amount": val(e["amount"], src),
                  **({"no_amount_printed": True} if e.get("金額の記載なし") else {})} for e in m.get("説明", []) if e.get("amount") is not None]
        # 歳入の説明欄は、金額の印字されない事項（節ごとに1事項）があり、事項の合計が目の額にならないことがある
        # （R8 9月第3号の県土整備債: 金額のない「堰堤改良事業債」「海岸高潮対策事業債」）。合わない目は事項を載せない（推計で埋めない）
        if items and side == "revenue" and sum(i["amount"]["v"] for i in items) != row["amount"]["v"]:
            print(f"WARN {r['id']} {rid}: 歳入の説明欄の事項の合計が目の額と合わないので、事項を載せない", file=sys.stderr)
            items = []
        if items:
            row["items"] = items
        setsu = []
        for s in m.get("節", []):
            if s.get("top", s.get("no") is not None):
                name = SETSU_NAMES.get(s["no"]) if side == "expense" and s.get("no") in SETSU_NAMES else clean(s["label"])
                nsrc = "reference" if side == "expense" and s.get("no") in SETSU_NAMES else src
                setsu.append({"no": s.get("no"), **({"no_src": src} if s.get("no") is not None else {}),
                              "name": name, "name_src": nsrc, "amount": val(s["amount"], src)})
            elif setsu:
                setsu[-1].setdefault("sub", []).append({"name": clean(s["label"]), "name_src": src, "amount": val(s["amount"], src)})
        if setsu:
            row["setsu"] = setsu
        if m.get("注記"):
            row["notes"] = m["注記"]
        row["pages"] = [{"source": r["src"], "page": p} for p in dict.fromkeys(m["pages"])]
        if all(m.get("checks", {}).values()):
            all_ok += 1
        else:
            fails.append(f"{r['id']} {rid}: 目の検算 {m.get('checks')}")
        rows.append(row)
    apply_name_corrections(r["id"], rows, json.load(open(NAME_CORRECTIONS, encoding="utf-8"))["修正"], fails)
    # 補正後は事項・細節を名前の完全一致で当初に足し込む（supplement.ts）。字形だけ違う名前（橋りよう／橋りょう）は
    # 別の事項として並んでしまうので止める（画像を見て名前の修正表で直す）
    for x in rows:
        base = init_rows.get(x["id"])
        if base is None:
            continue
        pairs = [([i["name"] for i in base.get("items", [])], [i["name"] for i in x.get("items", [])], "事項")]
        for s in x.get("setsu", []):
            bs = next((b for b in base.get("setsu", []) if b.get("no") == s.get("no")), None)
            if bs:
                pairs.append(([y["name"] for y in bs.get("sub", [])], [y["name"] for y in s.get("sub", [])], f"{s.get('no')}節の細節"))
        for base_names, names, what in pairs:
            near = {norm_name(b): b for b in base_names}
            for nm in names:
                if nm not in base_names and norm_name(nm) in near:
                    fails.append(f"{r['id']} {x['id']}: {what}「{nm}」が当初の「{near[norm_name(nm)]}」と字形だけ違う（名前の修正表で直す）")
    # 目の補正額の合計 = 総括の款の補正額（補正のない款は 0）
    got = Counter()
    for x in rows:
        got[(x["side"], x["kan"]["no"])] += x["amount"]["v"]
    for s_ja, s in SIDE.items():
        for k in gian_sk["総括"][s_ja]:
            if got[(s, k["no"])] != yen(k["補正額"]):
                fails.append(f"{r['id']} {s_ja} {k['no']}款: 目の補正額の合計 {got[(s, k['no'])]:,} ≠ 総括 {yen(k['補正額']):,}")
    accounts = [a for a in initial["accounts"] if a["id"] == "general"]
    out = {"schema_version": initial["schema_version"], "gov_id": initial["gov_id"], "year": YEAR, "year_label": YEAR_LABEL,
           "basis": "supplementary",
           "supplementary": {"round": r["round"], "kind": r["kind"], **({"bill_no": r["bill_no"]} if r["bill_no"] else {})},
           "unit_source": "千円", "accounts": accounts, "rows": rows,
           "checks": {"rows": len(rows), "all_ok": all_ok, "rules": {}, "external": {
               "総括_目の合計": f"{sum(1 for s in SIDE for k in gian_sk['総括'][s])} 款で照合"}}}
    return out


def build(work: str, initial: dict, rounds=ROUNDS):
    """返り値: [(ファイル名, データ, 検算が通ったか, 要約の行)]"""
    out = []
    for r in rounds:
        fails: list[str] = []
        gp, sp = os.path.join(work, f"hosei-{r['id']}.json"), os.path.join(work, f"setsumeisho-hosei-{r['id']}.json")
        if not (os.path.exists(gp) and os.path.exists(sp)):
            print(f"WARN 補正 {r['id']}: 入力がない（{os.path.basename(gp)}・{os.path.basename(sp)}）。この回は書き出さない", file=sys.stderr)
            continue
        data = build_round(r, json.load(open(gp, encoding="utf-8")), json.load(open(sp, encoding="utf-8")), initial, fails)
        n = int(r["id"].rsplit("-", 1)[1])
        lines = [f"FAIL 補正 {f}" for f in fails] + [
            f"補正 {r['id']}: 目 {len(data['rows'])} 件（全検算一致 {data['checks']['all_ok']}）、補正額 歳出 "
            f"{sum(x['amount']['v'] for x in data['rows'] if x['side'] == 'expense'):,} 円"]
        out.append((f"budget-{YEAR}-supplementary-{n}.json", data, not fails, lines))
    return out


if __name__ == "__main__":
    work, initial_path, outdir = sys.argv[1:4]
    initial = json.load(open(initial_path, encoding="utf-8"))
    ok_all = True
    for name, data, ok, lines in build(work, initial):
        for ln in lines:
            print(ln, file=sys.stderr)
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        ok_all = ok_all and ok
    sys.exit(0 if ok_all else 1)
