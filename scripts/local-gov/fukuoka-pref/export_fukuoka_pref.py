"""福岡県の抽出・検算の結果を、地方版の共通 JSON 形式（正規化データ）に書き出す。

設計: docs/local-gov/tasks/20261106_0841_共通JSON形式の設計.md（4章 正規化データ・6章 パイプラインとの境目）
型: types/local-gov.ts（LocalBudgetFile・LocalGovIndex）。検証: app/lib/local-gov/validate.ts（npm test で実データも検証）

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/export_fukuoka_pref.py --work <作業ディレクトリ> --pdf-dir <原本の置き場所> \
        --out public/data/local-gov/fukuoka-pref

<作業ディレクトリ> は回帰テストの出力（tests/regression.py --keep <dir>）。リポジトリには入れない。使うもの:
    cross.json・cross-toku.json … 一般会計・特別会計の cross_check.py の出力（OCR＋修正表＋文字層との突き合わせ）
    setsumeisho-{ocr,v4,tl}.json・setsumeisho-toku{,-v4,-tl}.json … 多数決に使う3つの読み取り
    yosansho.json・keijougaku.json・kessan-kmk.json（R6 決算。名前の照合に使う）
回帰テストの最後のステップとしても流れる（書き出しの要約が変わったら気づける）。

書き出すもの:
    budget-2026-initial.json … R8 当初予算（一般会計・特別会計14会計）。金額は円（千円 ×1000）
    index.json               … 自治体の情報・データの一覧・資料の一覧（URL・SHA256）
公営企業会計は名前の文字層が崩れているので、名前を直してから足す（未対応）。

値の出典（Value.src）:
    ocr: OCR（PP-OCRv6 とセルの読み直し） / correction: 修正表（画像で確認） / textlayer: 文字層との突き合わせで採用 /
    blank-as-zero: 空欄を 0 とみなした / text: テキスト PDF
名前の出典（name_src）:
    text: テキスト PDF の資料（計上額調の款名） / reference: R6 決算（テキスト）の同じ款の中で十分に近い名前 / ocr: OCR
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

GOV_ID = "fukuoka-pref"
YEAR, YEAR_LABEL = 2026, "令和8年度"

# 特別会計の ID（slug）。計上額調の会計名 → slug
SPECIAL_SLUGS = {
    "財政調整基金": "zaisei-chosei-kikin", "公債管理": "kosai-kanri", "市町村振興基金": "shichoson-shinko-kikin",
    "国民健康保険": "kokumin-kenko-hoken", "母子父子寡婦福祉資金貸付事業": "boshi-fushi-kafu-fukushi-shikin",
    "災害救助基金": "saigai-kyujo-kikin", "就農支援資金貸付事業": "shuno-shien-shikin", "県営林造成事業": "kenei-rin-zosei",
    "林業改善資金助成事業": "ringyo-kaizen-shikin", "沿岸漁業改善資金助成事業": "engan-gyogyo-kaizen-shikin",
    "小規模企業者等設備導入資金貸付事業": "shokibo-kigyosha-setsubi-shikin", "公共用地先行取得事業": "kokyo-yochi-senko-shutoku",
    "県営埠頭施設整備運営事業": "kenei-futo-shisetsu", "住宅管理": "jutaku-kanri",
}

# 節の名前（地方自治法施行規則の歳出の節。番号で決まる）
SETSU_NAMES = {1: "報酬", 2: "給料", 3: "職員手当等", 4: "共済費", 5: "災害補償費", 6: "恩給及び退職年金", 7: "報償費", 8: "旅費",
               9: "交際費", 10: "需用費", 11: "役務費", 12: "委託料", 13: "使用料及び賃借料", 14: "工事請負費", 15: "原材料費",
               16: "公有財産購入費", 17: "備品購入費", 18: "負担金、補助及び交付金", 19: "扶助費", 20: "貸付金",
               21: "補償、補塡及び賠償金", 22: "償還金、利子及び割引料", 23: "投資及び出資金", 24: "積立金", 25: "寄附金",
               26: "公課費", 27: "繰出金"}

# 原本の一覧（URL・SHA256・取得日）。取得日はファイルの更新日時ではなく、この一覧に書いた日を使う
# （ファイルをコピー・取り直すと更新日時が変わり、本当の取得日でなくなるため）
SOURCES_FILE = os.path.join(HERE, "sources.json")


def load_vote():
    spec = importlib.util.spec_from_file_location("vote", os.path.join(HERE, "ocr", "vote.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").strip()
    s = s.replace("•", "・").replace("·", "・")
    # 横棒1本の「一」は OCR で落ちやすい（「般会計繰入金」。説明書の OCR・議案の文字層とも）
    s = re.sub(r"^般会計", "一般会計", s)
    s = re.sub(r"^○", "", s)
    return s


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


# OCR で起きる字形の取り違え（説明書の OCR で実例のあるもの）。参照の名前との照合の前に直す
GLYPH_FIXES = str.maketrans({"壳": "売", "讓": "譲", "產": "産", "齡": "齢", "徵": "徴", "人": "入", "·": "・", "よ": "ょ",
                             "费": "費", "务": "務", "厅": "庁", "县": "県", "龄": "齢", "收": "収", "贷": "貸"})


def is_ocr_variant(ocr: str, ref: str) -> bool:
    """OCR の名前が、参照の名前（別年度のテキスト資料）の「崩れ」として説明がつくか。
    近さだけで置き換えると、正しい OCR の名前を別の目の名前に変えてしまう
    （「参議院議員通常選挙臨時啓発費」→ R6 の「衆議院議員総選挙臨時啓発費」、「地域振興総務費」→「地域振興費」の実例）。
    説明がつくのは次のどれか:
      - 字形の取り違え（GLYPH_FIXES）を直すと一致する
      - 2行の名前の前後が入れ替わった（使っている文字が同じ。「海洋技術水産センター費」→「水産海洋技術センター費」）
      - OCR が文字を落とした（OCR の文字が参照に順に全部含まれ、落ちたのは3文字以内。「廃対策費」→「廃棄物対策費」）
      - 上のどれかに加えて、違う文字が1文字だけ（「ゴ児フ場利用税」→「ゴルフ場利用税」）
    参照の方が短い・2文字以上違う場合は崩れではなく別の名前とみなす。"""
    o = re.sub(r"[I|l]", "", ocr.translate(GLYPH_FIXES))
    if o == ref:
        return True
    if len(o) == len(ref) and sorted(o) == sorted(ref):
        return True
    if len(ref) < len(o):
        return False
    # 参照から OCR への最小の操作: 参照にしかない文字（落ちた文字）と、置き換わった文字を数える
    ops = difflib.SequenceMatcher(None, o, ref, autojunk=False).get_opcodes()
    dropped = sum(j2 - j1 for tag, i1, i2, j1, j2 in ops if tag == "insert")
    replaced = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag == "replace")
    deleted = sum(i2 - i1 for tag, i1, i2, j1, j2 in ops if tag == "delete")
    return deleted == 0 and dropped <= 3 and replaced <= 1


def yen(v):
    return None if v is None else int(v) * 1000


def val(v, src, agree=None, note=None):
    out = {"v": yen(v), "src": src}
    if agree is not None:
        out["agree"] = agree
    if note:
        out["note"] = note
    return out


class Exporter:
    def __init__(self, work, kmk, keijou, yosansho, vote):
        self.vote = vote
        self.kmk = kmk
        self.keijou = keijou
        self.yo = yosansho
        self.r6_names = {}  # (side, 款) → {"kou": [...], "moku": [...]}
        for side, key in (("歳入", "revenue"), ("歳出", "expense")):
            for kan in kmk[key]:
                d = self.r6_names.setdefault((side, kan["no"]), {"kou": [], "moku": []})
                for kou in kan["children"]:
                    d["kou"].append(kou["name"])
                    d["moku"].extend(mo["name"] for mo in kou["children"])
        self.name_stats = Counter()
        self.replaced = []  # (項/目, OCR の名前, 置き換えた名前)。書き出しの後に一覧を出して目で確かめる
        self.alt_names = {}

    def readings(self, paths):
        loaded = [self.vote.load(p) for p in paths]
        # 名前が空のとき（OCR が目名を読めなかった）に使う、ほかの読み取りの名前。
        # paths は（OCR・旧 OCR・文字層）の順。後に入れたものが優先なので、文字層 > 旧 OCR
        for ms in loaded[1:]:
            for m in ms:
                if m["目名"]:
                    self.alt_names[self.vote.key(m)] = m["目名"]
        return [{self.vote.key(m): self.vote.values(m) for m in ms} for ms in loaded]

    def pick_name(self, ocr_name, side, kan, level):
        """一般会計の項・目名: R6 決算（テキスト）の同じ款の中に、OCR の名前が「崩れ」として説明のつく名前
        （is_ocr_variant）がちょうど1つあればそれ、なければ OCR のまま。
        同じ名前が R6 にあれば崩れていないので OCR のまま（ただし出典は reference: 別資料で同じ名前を確認できた）。"""
        name = clean_name(ocr_name)
        cands = self.r6_names.get((side, kan), {}).get(level, [])
        if name in cands:
            self.name_stats[f"{level} reference"] += 1
            return name, "reference"
        hits = sorted({c for c in cands if is_ocr_variant(name, c)})
        if len(hits) == 1:
            self.name_stats[f"{level} reference"] += 1
            self.replaced.append((level, name, hits[0]))
            return hits[0], "reference"
        self.name_stats[f"{level} ocr"] += 1
        return name, "ocr"

    def row(self, m, account_id, kan_name, kan_name_src, readings, special):
        side = "revenue" if m["side"] == "歳入" else "expense"
        kou_no, kou_name = m["項"]
        if not m["目名"].strip():
            # OCR が目名を読めなかった（R8 3款2項3目 難病等対策費）。ほかの読み取りの名前を使い、下の照合を通す
            m = dict(m, 目名=self.alt_names.get(self.vote.key(m), ""))
            print(f"名前の補い（目）: {self.vote.key(m)} 空 → {m['目名']}", file=sys.stderr)
        if special:
            kou_n, kou_src = clean_name(kou_name), "ocr"
            moku_n, moku_src = clean_name(m["目名"]), "ocr"
        else:
            kou_n, kou_src = self.pick_name(kou_name, m["side"], m["款"], "kou")
            moku_n, moku_src = self.pick_name(m["目名"], m["side"], m["款"], "moku")
        key = self.vote.key(m)
        votes = [r.get(key, {}) for r in readings]
        vals = self.vote.values(m)

        def agree(field):
            if field not in vals or vals[field] is None:
                return None
            return sum(1 for r in votes if r.get(field) == vals[field])

        fixes = {}
        for fx in m.get("修正", []):
            k = (fx["列"], fx.get("区分") or fx.get("節番号") or fx.get("事項"))
            fixes[k] = fx["根拠"]
        rescued = m.get("出典", {})
        blank = m.get("空欄を0とみなした")

        def scalar_src(field):
            if (field, None) in fixes:
                return "correction", fixes[(field, None)]
            if blank == field:
                return "blank-as-zero", None
            if "本年度・前年度・比較" in rescued:
                return "textlayer", None
            return "ocr", None

        s, n = scalar_src("本年度")
        out = {
            "id": f"{account_id}/{side}/{m['款']}-{kou_no}-{m['目番号']}",
            "account": account_id, "side": side,
            "kan": {"no": m["款"], "name": kan_name, "name_src": kan_name_src},
            "kou": {"no": kou_no, "name": kou_n, "name_src": kou_src},
            "moku": {"no": m["目番号"], "name": moku_n, "name_src": moku_src},
            "amount": val(m["本年度"], s, agree("本年度"), n),
        }
        s, n = scalar_src("前年度")
        out["previous"] = val(m["前年度"], s, agree("前年度"), n)
        if m["side"] == "歳出":
            f_notes = " ".join(m.get("財源の突き合わせ") or [])
            f = {}
            for jp, en in (("国庫支出金", "national"), ("地方債", "bond"), ("その他", "other"), ("一般財源", "general")):
                if ("財源", jp) in fixes:
                    src, note = "correction", fixes[("財源", jp)]
                elif "財源を1件ずつ" in rescued and jp in f_notes:
                    src, note = "textlayer", None
                else:
                    src, note = "ocr", None
                f[en] = val(m["財源"][jp], src, agree(f"財源 {jp}"), note)
            out["funding"] = f
            items = []
            last_top = None
            seen = Counter()
            for e in m["説明"]:
                name = clean_name(e["name"])
                it = {}
                mh = re.search(r"([\d,]+)人$", name)
                if mh and e.get("人数") is None:
                    it["headcount"] = int(mh.group(1).replace(",", ""))
                    name = name[:mh.start()].strip()
                elif e.get("人数") is not None:
                    it["headcount"] = e["人数"]
                src = "textlayer" if ("説明欄の金額" in rescued or e.get("名前は文字層_要補正")) else "ocr"
                if e.get("金額の記載なし"):
                    src = scalar_src("本年度")[0]  # 目の額を当てた事項は、目の本年度と同じ出典
                seen[e["amount"]] += 1
                ag = agree(f"説明 {e['amount']}#{seen[e['amount']]}")
                it = {"name": name, "amount": val(e["amount"], src, ag), **it}
                if e.get("金額の記載なし"):
                    it["no_amount_printed"] = True
                if e.get("内訳") and last_top is not None:
                    it["parent"] = last_top
                else:
                    last_top = len(items)
                items.append(it)
            if items:
                out["items"] = items
        setsu = []
        seen = Counter()
        for st in m["節"]:
            top = st.get("top", st.get("no") is not None)
            if ("節", st.get("no")) in fixes and top:
                src, note = "correction", fixes[("節", st.get("no"))]
            elif st.get("出典") == "文字層" or "節" in rescued:
                src, note = "textlayer", None
            else:
                src, note = "ocr", None
            if top:
                seen[st["amount"]] += 1
                name = (SETSU_NAMES.get(st["no"]) if m["side"] == "歳出" and st.get("no") else None) or clean_name(st["label"])
                # 番号が読めなかった節は null（並び順の番号をこしらえない）
                setsu.append({"no": st.get("no") or None, "name": name,
                              "amount": val(st["amount"], src, agree(f"節 {st['amount']}#{seen[st['amount']]}"), note)})
            elif setsu:
                setsu[-1].setdefault("sub", []).append({"name": clean_name(st["label"]), "amount": val(st["amount"], src)})
        if setsu:
            out["setsu"] = setsu
        if m.get("注記"):
            out["notes"] = m["注記"]
        src_id = "r8-setsumeisho-toku" if special else "r8-setsumeisho-ippan"
        out["pages"] = [{"source": src_id, "page": p} for p in dict.fromkeys(m["pages"])]
        return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    w = lambda name: os.path.join(a.work, name)  # noqa: E731
    vote = load_vote()
    ex = Exporter(a.work, json.load(open(w("kessan-kmk.json"))), json.load(open(w("keijougaku.json"))),
                  json.load(open(w("yosansho.json"))), vote)

    kan_names = {("歳入", k["no"]): k["款名"] for k in ex.keijou["一般会計歳入"]["款"]}
    kan_names.update({("歳出", k["no"]): k["款名"] for k in ex.keijou["一般会計歳出"]["款"]})
    yo_kan = {}
    for k in ex.yo["会計"]:
        name = re.sub(r"特別会計$", "", k["会計"])
        for side in ("歳入", "歳出"):
            for kan in k.get(side, []):
                yo_kan[(name, side, kan["no"])] = clean_name(kan["name"])

    accounts = [{"id": "general", "kind": "general", "name": "一般会計"}]
    accounts += [{"id": f"special:{slug}", "kind": "special", "name": f"{name}特別会計"} for name, slug in SPECIAL_SLUGS.items()]
    rows = []
    stats = Counter()
    read_files = {"ippan": ("setsumeisho-ocr.json", "setsumeisho-v4.json", "setsumeisho-tl.json"),
                  "toku": ("setsumeisho-toku.json", "setsumeisho-toku-v4.json", "setsumeisho-toku-tl.json")}
    for kind, cross in (("ippan", "cross.json"), ("toku", "cross-toku.json")):
        readings = ex.readings([w(x) for x in read_files[kind]])
        ms = [m for m in json.load(open(w(cross)))["目"] if m["kind"] == "目"]
        for m in ms:
            special = kind == "toku"
            if special:
                acc = f"special:{SPECIAL_SLUGS[m['会計']]}"
                kan_name, kan_src = yo_kan.get((m["会計"], m["side"], m["款"]), ""), "ocr"
            else:
                acc = "general"
                kan_name, kan_src = kan_names[(m["side"], m["款"])], "text"
            r = ex.row(m, acc, kan_name, kan_src, readings, special)
            # 会計間の繰入れの印（純計のため）。特別会計の「一般会計繰入金」、一般会計の「○○特別会計繰入金」
            if r["side"] == "revenue":
                if special and r["moku"]["name"].startswith("一般会計繰入金"):
                    r["transfer"] = {"from_account": "general"}
                elif not special:
                    for name, slug in SPECIAL_SLUGS.items():
                        if r["moku"]["name"].startswith(f"{name}特別会計繰入金"):
                            r["transfer"] = {"from_account": f"special:{slug}"}
            stats["ok" if all(m["checks"].values()) else "ng"] += 1
            rows.append(r)

    ippan_cross = json.load(open(w("cross.json")))
    toku_cross = json.load(open(w("cross-toku.json")))
    n_fix = sum(len(m.get("修正", [])) for c in (ippan_cross, toku_cross) for m in c["目"])
    vals = Counter()
    for r in rows:
        for v in [r["amount"], r.get("previous")] + list((r.get("funding") or {}).values()) + \
                 [i["amount"] for i in r.get("items", [])] + [s["amount"] for s in r.get("setsu", [])]:
            if v and v.get("agree") is not None:
                vals["n"] += 1
                vals["2plus"] += int(v["agree"] >= 2)
                vals["image"] += int(v["agree"] < 2 and v["src"] == "correction")
    rule_counts = Counter()
    for c in (ippan_cross, toku_cross):
        for m in c["目"]:
            for k, ok in m["checks"].items():
                rule_counts[k] += int(ok)
    budget = {
        "schema_version": 1, "gov_id": GOV_ID, "year": YEAR, "year_label": YEAR_LABEL, "basis": "initial",
        "unit_source": "千円", "accounts": accounts, "rows": rows,
        "checks": {
            "rows": len(rows), "all_ok": stats["ok"],
            "rules": {"A_説明欄": rule_counts["A"], "B_財源": rule_counts["B"], "C_比較": rule_counts["C"], "D_節": rule_counts["D"]},
            "external": {"項_予算書": "一般会計 106/106・特別会計 83/83", "款_計上額調": "一般会計 29/29",
                         "会計_計上額調": "特別会計 28/28（14会計の歳入・歳出）", "計の行": "一般会計 74/74・特別会計 23/23"},
            "readings": {"agree_2plus": round(vals["2plus"] / vals["n"], 4) if vals["n"] else 0,
                         "confirmed_by_image": vals["image"]},
            "corrections": n_fix,
        },
    }
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"budget-{YEAR}-initial.json"), "w", encoding="utf-8") as f:
        json.dump(budget, f, ensure_ascii=False, indent=1)
        f.write("\n")

    sources = []
    for s in json.load(open(SOURCES_FILE, encoding="utf-8"))["sources"]:
        p = os.path.join(a.pdf_dir, f"{s['file']}.pdf")
        got = sha256(p)
        if got != s["sha256"]:
            # 手元の原本が一覧と違う（県が資料を差し替えた・取り違えた）。そのまま書き出すと出典の記録と中身が食い違う
            sys.exit(f"原本の SHA256 が sources.json と違う: {s['file']}.pdf（一覧 {s['sha256'][:12]}… / 手元 {got[:12]}…）。"
                     f"資料が差し替わっていないか確かめ、sources.json を更新してから書き出す")
        sources.append({k: s[k] for k in ("id", "title", "url", "sha256", "retrieved")})
    index = {
        "schema_version": 1,
        "gov": {"id": GOV_ID, "name": "福岡県", "kind": "prefecture"},
        "datasets": [{"year": YEAR, "label": YEAR_LABEL, "basis": "initial", "file": f"budget-{YEAR}-initial.json",
                      "status": "verified" if stats["ng"] == 0 else "partial"}],
        "sources": sources,
    }
    with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write("\n")
    total = Counter()
    for r in rows:
        total[(r["account"] == "general", r["side"])] += r["amount"]["v"] or 0
    print(f"目 {len(rows)} 件（全検算一致 {stats['ok']}・不一致 {stats['ng']}）。修正表 {n_fix} 件。"
          f"2通り以上の読み取りで一致 {budget['checks']['readings']['agree_2plus']:.2%}・"
          f"1通り以下で画像で確認 {vals['image']} 件・1通り以下で未確認 {vals['n'] - vals['2plus'] - vals['image']} 件",
          file=sys.stderr)
    print(f"一般会計 歳入 {total[(True, 'revenue')]:,} 円・歳出 {total[(True, 'expense')]:,} 円", file=sys.stderr)
    print(f"名前の出典: {dict(ex.name_stats)}", file=sys.stderr)
    for level, o, n in ex.replaced:
        print(f"名前の置き換え（{'項' if level == 'kou' else '目'}）: {o} → {n}", file=sys.stderr)


if __name__ == "__main__":
    main()
