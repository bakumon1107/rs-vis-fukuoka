"""公営企業会計（予算実施計画）を、当初予算のファイル（budget-<年度>-initial.json）の accounts・rows に組み立てる。

設計: docs/local-gov/tasks/20261121_0100_公開前のサンキー図の足しと公営企業会計の設計.md 4.3
export_fukuoka_pref.py の main から呼ぶ。入力は作業ディレクトリの kigyo-named.json（kigyo_names.py。名前を決めた実施計画）と
yosansho.json（予算書の本体。第3条・第4条の款・項の額と、第4条の補填財源の文言）。

- 会計: enterprise:<slug>（kind enterprise）。資本的収入が資本的支出に足りないときは、その補填財源の内訳を
  enterprise.capital_shortfall に持つ（予算書の本体の第4条。内訳の合計 = 不足額 = 支出 − 収入 は抽出で確かめた）
- 行: 目ごと。ID は enterprise:<slug>/<side>/<条>-<款>-<項>-<目>（款の番号が条ごとに振り直されるので、条を ID に入れる）。
  enterprise_section は 収益的（第3条）・資本的（第4条）。額は千円 × 1000 の円で、出典は text（発行元の文字層。予算書の本体と照合済み）
- 確かめ: 会計・条・収入支出ごとの目の合計 = 予算書の本体の款の合計。名前の決め方の失敗（kigyo-named.json の fails）があれば止める
"""
import json
import os

# 会計の名前 → slug（ID に使う）
SLUGS = {
    "病院事業会計": "byoin",
    "流域下水道事業会計": "ryuiki-gesuido",
    "電気事業会計": "denki",
    "工業用水道事業会計": "kogyo-yosui",
    "工業用地造成事業会計": "kogyo-yochi",
}
SECTIONS = {"収益的収入及び支出": (3, "収益的"), "資本的収入及び支出": (4, "資本的")}
SIDES = {"収入": "revenue", "支出": "expense"}
SRC_PLAN = "r8-setsumeisho-toku"  # 実施計画（特別会計・公営企業会計の説明書）
SRC_BILL = "r8-gian"  # 予算書の本体（議案）


def _named(node: dict) -> dict:
    return {"no": node["no"], "name": node["name"], "name_src": node["name_src"]}


def build(work: str) -> tuple[list[dict], list[dict], list[str], list[str]]:
    """返り値: (会計, 行, 要約の行, 失敗)。kigyo-named.json がなければ失敗（公開データから公営企業会計が黙って消えないよう）"""
    path = os.path.join(work, "kigyo-named.json")
    if not os.path.exists(path):
        return [], [], [], ["公営企業会計: kigyo-named.json がない（公営企業の名前のステップを飛ばした作業ディレクトリ）"]
    named = json.load(open(path, encoding="utf-8"))
    if named.get("fails"):
        return [], [], [], [f"公営企業会計の名前: {f}" for f in named["fails"]]
    yo = {k["会計"]: k for k in json.load(open(os.path.join(work, "yosansho.json"), encoding="utf-8"))["会計"]}
    accounts, rows, fails = [], [], []
    totals = {3: 0, 4: 0}
    for a in named["会計"]:
        acc_name = a["会計"]
        if acc_name not in SLUGS:
            fails.append(f"公営企業会計: {acc_name} の slug がない（SLUGS に足す）")
            continue
        acc_id = f"enterprise:{SLUGS[acc_name]}"
        acc = {"id": acc_id, "kind": "enterprise", "name": acc_name}
        hf = yo.get(acc_name, {}).get("補填")
        if hf:
            acc["enterprise"] = {"capital_shortfall": {
                "amount": hf["不足額"] * 1000,
                "items": [{"name": x["name"], "amount": x["金額"] * 1000} for x in hf["内訳"]],
                "source": {"source": SRC_BILL, "page": hf["pdf_page"]}}}
        accounts.append(acc)
        arts = yo.get(acc_name, {}).get("条", {})
        for sec, (art, section) in SECTIONS.items():
            for side_ja, side in SIDES.items():
                got = 0
                for kan in a.get(sec, {}).get(side_ja, []):
                    for kou in kan.get("項", []):
                        for m in kou.get("目", []):
                            amount = m["金額"] * 1000
                            got += amount
                            rows.append({
                                "id": f"{acc_id}/{side}/{art}-{kan['no']}-{kou['no']}-{m['no']}",
                                "account": acc_id, "side": side, "enterprise_section": section,
                                "kan": _named(kan), "kou": _named(kou), "moku": _named(m),
                                "amount": {"v": amount, "src": "text"},
                                "pages": [{"source": SRC_PLAN, "page": m["pdf_page"]}],
                            })
                want = sum(k["金額"] for k in (arts.get(str(art)) or arts.get(art) or {}).get(side_ja, [])) * 1000
                if got != want:
                    fails.append(f"公営企業会計 {acc_name} 第{art}条 {side_ja}: 目の合計 {got:,} 円 ≠ 予算書の本体 {want:,} 円")
                if side == "expense":
                    totals[art] += got
    lines =[f"公営企業会計 {len(accounts)} 会計・目 {len(rows)} 件（支出 第3条 {totals[3]:,} 円・第4条 {totals[4]:,} 円）。"
             f"補填財源のある会計 {sum(1 for a in accounts if 'enterprise' in a)}"]
    return accounts, rows, lines, fails
