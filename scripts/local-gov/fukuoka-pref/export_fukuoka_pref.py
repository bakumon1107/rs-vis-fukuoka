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
名前の出典（name_src。款・項・目・事項・節・細節。決め方は name_evidence.py）:
    text: テキスト PDF の資料（計上額調の款名） / reference: R6 決算（テキスト）の同じ款の中の名前と照合
    （歳出の節は、節番号で決まる施行規則の節名と区分の文字が一致） / search: 手元のテキスト資料（sources.json の corpus）に
    同じ名前がある（name_evidence に資料の id） / readings: 独立した読み取りの2つ以上が一致 /
    correction: 名前の修正表（ocr/corrections/r8-names.json。画像で確認） / ocr: 裏付けなし
節番号の出典（no_src）: ocr: 説明書の OCR / textlayer: OCR で読めず、同じ金額の節の番号を文字層から /
    correction: 名前の修正表の set_no（画像で確認）
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
sys.path.insert(0, HERE)
import name_evidence  # noqa: E402

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


def external_checks(rows, yosansho, keijou, total_rows):
    """書き出す行（円）を外部の資料と突き合わせる。返り値: (要約 {名前: "一般会計 n/n・特別会計 n/n"}, NG の一覧)。
    - 項_予算書: 項ごとの目の合計 = 予算書の本体（議案）の項の額（予算書にない項に目が入っていれば NG）
    - 款_計上額調: 一般会計の款ごとの目の合計 = 当初予算計上額調の款の当年度
    - 会計_計上額調: 特別会計ごとの歳入・歳出の目の合計 = 計上額調の会計の当年度
    - 計の行: 項ごとの目の合計 = 説明書の「計」の行（OCR）
    固定の値を書かず、突き合わせ（cross_check.py）の後の値で毎回数える。"""
    acc_of = {"一般会計": "general", **{f"{n}特別会計": f"special:{s}" for n, s in SPECIAL_SLUGS.items()}}
    side_of = {"歳入": "revenue", "歳出": "expense"}
    got_kou, got_kan, got_acc = Counter(), Counter(), Counter()
    for r in rows:
        v = r["amount"]["v"] or 0
        got_kou[(r["account"], r["side"], r["kan"]["no"], r["kou"]["no"])] += v
        got_kan[(r["account"], r["side"], r["kan"]["no"])] += v
        got_acc[(r["account"], r["side"])] += v
    ng = []
    tally = {k: Counter() for k in ("項_予算書", "款_計上額調", "会計_計上額調", "計の行")}

    def count(name, acc, ok, msg):
        part = "一般会計" if acc == "general" else "特別会計"
        tally[name][(part, "n")] += 1
        tally[name][(part, "ok")] += int(ok)
        if not ok:
            ng.append(f"{name}: {msg}")

    bill_kou = set()
    for a in yosansho["会計"]:
        acc = acc_of.get(a["会計"])
        if acc is None:
            continue  # 公営企業会計（まだ書き出さない）
        for jp, side in side_of.items():
            for kan in a.get(jp, []):
                for kou in kan.get("項", []):
                    key = (acc, side, kan["no"], kou["no"])
                    bill_kou.add(key)
                    count("項_予算書", acc, got_kou[key] == yen(kou["金額"]),
                          f"{key} 目の合計 {got_kou[key]:,} / 予算書 {yen(kou['金額']):,}")
    for key in sorted(set(got_kou) - bill_kou):
        count("項_予算書", key[0], False, f"{key} 予算書にない項に目が入っている")
    for jp, side in (("一般会計歳入", "revenue"), ("一般会計歳出", "expense")):
        for kan in keijou[jp]["款"]:
            key = ("general", side, kan["no"])
            count("款_計上額調", "general", got_kan[key] == yen(kan["当年度"]),
                  f"{key} 目の合計 {got_kan[key]:,} / 計上額調 {yen(kan['当年度']):,}")
    for a in keijou["特別会計"]["会計"]:
        acc = f"special:{SPECIAL_SLUGS[a['会計名']]}"
        for side in ("revenue", "expense"):
            count("会計_計上額調", acc, got_acc[(acc, side)] == yen(a["当年度"]),
                  f"{acc} {side} 目の合計 {got_acc[(acc, side)]:,} / 計上額調 {yen(a['当年度']):,}")
    for t in total_rows:
        acc = "general" if t.get("会計") in (None, "一般会計") else f"special:{SPECIAL_SLUGS[t['会計']]}"
        key = (acc, side_of[t["side"]], t["款"], (t["項"] or (None,))[0])
        count("計の行", acc, got_kou[key] == yen(t["本年度"]), f"{key} 目の合計 {got_kou[key]:,} / 計の行 {yen(t['本年度'])}")

    def text(name):
        parts = [f"{p} {tally[name][(p, 'ok')]}/{tally[name][(p, 'n')]}" for p in ("一般会計", "特別会計") if tally[name][(p, "n")]]
        return "・".join(parts)
    return {name: text(name) for name in tally}, ng


def setsu_in_print_order(m):
    """目の節・細節を、説明書に印字された順（ページ → 高さ）に並べる。細節は「直前の節」に付けるので、順が崩れていると
    別の節に付く。突き合わせ（cross_check.py）で節を組み直した目は「節を全部 → 細節を全部」の順になっていた
    （R8 6款5項5目 森林環境費: 勤勉手当・普通旅費などの細節がすべて最後の節「積立金」に付いた）。
    位置（page・y）のない節（修正表で足した節）がある目は、並べ替えずにそのままの順を使う。"""
    ss = m["節"]
    if not ss or any(s.get("page") is None or s.get("y") is None for s in ss):
        return ss
    order = {p: i for i, p in enumerate(dict.fromkeys(m["pages"]))}
    return sorted(ss, key=lambda s: (order.get(s["page"], len(order)), s["y"]))


def split_headcount(name: str):
    """事項名の末尾の人数（「職員費 10人」）を分ける。(名前, 人数 or None)"""
    mh = re.search(r"([\d,]+)人$", name)
    if not mh:
        return name, None
    return name[:mh.start()].strip(), int(mh.group(1).replace(",", ""))


def setsu_label_matches(label: str, no: int) -> bool:
    """歳出の節の区分の文字（OCR）が、節番号で決まる節名と合うか（崩れとして説明がつくか）。
    is_ocr_variant に加えて、2行の区分の字の順が混ざった形（「負及び交付担金補助金」＝「負担金、補助及び交付金」の字の並べ替え）と、
    それに余分な字が1字だけ混じった形（「扶助力費」）、6字以上の節名で1字だけ欠けた形（「負及担交金補付助金」）を合うとみなす。
    節名は27通りしかなく、使う字の組み合わせがそれぞれ違うので、字の集まりで比べても取り違えない
    （どの2つの節名もこの規則で合わないことを単体テストで確かめる）。「補填」は「補塡」の異体字として同じに扱う。"""
    official = SETSU_NAMES.get(no)
    if not official or not label:
        return False
    lab = re.sub(r"^\d+", "", label).replace("填", "塡")
    if lab == official or is_ocr_variant(lab, official):
        return True
    want, got = Counter(re.sub(r"[、・]", "", official)), Counter(re.sub(r"[、・]", "", lab))
    missing, extra = sum((want - got).values()), sum((got - want).values())
    return missing <= (1 if sum(want.values()) >= 6 else 0) and extra <= 1


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
    def __init__(self, work, kmk, keijou, yosansho, vote, corpus=None):
        self.vote = vote
        self.kmk = kmk
        self.keijou = keijou
        self.yo = yosansho
        self.corpus = corpus
        self.r6_names = {}  # (side, 款) → {"kou": [...], "moku": [...]}
        for side, key in (("歳入", "revenue"), ("歳出", "expense")):
            for kan in kmk[key]:
                d = self.r6_names.setdefault((side, kan["no"]), {"kou": [], "moku": []})
                for kou in kan["children"]:
                    d["kou"].append(kou["name"])
                    d["moku"].extend(mo["name"] for mo in kou["children"])
        self.replaced = []  # (項/目, OCR の名前, 置き換えた名前)。書き出しの後に一覧を出して目で確かめる
        self.unresolved = []  # 裏付けのない名前（画像で確かめる一覧。款・項・目・歳入の節）
        self.raw = []  # 読み取りごとの 目の行（key → 目）。[0] が採用した読み取り（cross）と同じ OCR

    def readings(self, paths):
        """paths は（OCR・旧 OCR・文字層）の順。金額の多数決用の値と、名前の候補用の目の行を持つ。"""
        loaded = [self.vote.load(p) for p in paths]
        self.raw = [{self.vote.key(m): m for m in ms} for ms in loaded]
        # 修正表で直した値は「読み取りの一致」に数えない（画像での確認は値の出典 correction として別に示す）
        return [{self.vote.key(m): self.vote.reading_values(m) for m in ms} for ms in loaded]

    def reference(self, side, kan, level):
        """一般会計の項・目名: R6 決算（テキスト）の同じ款の中に、名前が「崩れ」として説明のつく名前
        （is_ocr_variant）がちょうど1つあればそれ。同じ名前が R6 にあればそのまま。"""
        cands = self.r6_names.get((side, kan), {}).get(level, [])

        def look(name):
            if name in cands:
                return name
            hits = sorted({c for c in cands if is_ocr_variant(name, c)})
            return hits[0] if len(hits) == 1 else None
        return look

    def name(self, level, cands, where, reference=None, report=True):
        """同じ箇所の名前の候補 [(名前, 系統)]（先頭が採用する読み取り）から、裏付けのいちばん強い名前を選ぶ
        （name_evidence.resolve）。系統: bill＝予算書の本体（議案）の文字層、ocr＝説明書の OCR と旧 OCR（同じ切り抜きを読む
        ので1つの系統）、textlayer＝説明書の文字層。"""
        cands = [(clean_name(c), g) for c, g in cands if c and c.strip()]
        name, src, ev = name_evidence.resolve(cands, self.corpus, reference)
        name = clean_name(name)
        first = cands[0][0] if cands else ""
        if src == "reference" and name != first:
            self.replaced.append((level, first, name))
        if src == "ocr" and report:
            self.unresolved.append((level, where, name, [c for c, _ in cands], ev))
        return name, src, (ev if src == "search" else None)

    def others(self, m):
        """同じ目の、採用した読み取り以外の読み取り [(読み取りの種類, 目の行)]。文字層・旧 OCR の順
        （裏付けがないとき、先の方の名前を使う）。self.raw は（OCR・旧 OCR・文字層）の順。"""
        key = self.vote.key(m)
        return [(kind, r[key]) for kind, r in zip(("textlayer", "v4"), (self.raw[2], self.raw[1])) if key in r]

    @staticmethod
    def by_amount(entries):
        """目の中の (金額, 何番目) → 事項・節。読み取りの間で事項・節を金額で対応させる（vote.values と同じ考え方。
        番号・順番で対応させると、節番号の読み違い・件数の違いで外れる）。"""
        seen = Counter()
        out = {}
        for e in entries:
            seen[e["amount"]] += 1
            out[(e["amount"], seen[e["amount"]])] = e
        return out

    def row(self, m, account_id, kan_name, kan_name_src, readings, special, kan_bill=None):
        side = "revenue" if m["side"] == "歳入" else "expense"
        kou_no, kou_bill = m["項"]
        # 裏付けのない名前の一覧（画像での確認用）に載せる場所: 目の行・ページ・目の欄の位置（節は行の高さ y を足す）
        where = {"id": f"{account_id}/{side}/{m['款']}-{kou_no}-{m['目番号']}",
                 "row": f"{m.get('会計') or '一般会計'} {m['side']} {m['款']}-{kou_no}-{m['目番号']}",
                 "source": "r8-setsumeisho-toku" if special else "r8-setsumeisho-ippan", "cell": m.get("cell")}
        others = self.others(m)  # [(textlayer|v4, 目の行)]
        group = {"textlayer": "textlayer", "v4": "ocr"}
        # 項・款: 予算書の本体（議案）の名前（choose_kou が予算書の項の一覧から選んだ名前）と、OCR・旧 OCR の表の見出しの名前。
        # 文字層の読み取りの見出しは OCR の見出しを借りている（textlayer_pages.py）ので候補に入れない
        heads = [m] + [x for kind, x in others if kind == "v4"]
        kou_cands = [(kou_bill, "bill")] + [(x.get("項_見出し"), "ocr") for x in heads]
        moku_cands = [(m["目名"], "ocr")] + [(x["目名"], group[kind]) for kind, x in others]
        kou_ref = moku_ref = None
        if not special:
            kou_ref = self.reference(m["side"], m["款"], "kou")
            moku_ref = self.reference(m["side"], m["款"], "moku")
        kou_n, kou_src, kou_ev = self.name("kou", kou_cands, where, kou_ref)
        moku_n, moku_src, moku_ev = self.name("moku", moku_cands, where, moku_ref)
        if special:
            kan_name, kan_name_src, kan_ev = self.name("kan", [(kan_bill, "bill")] + [(x.get("款_見出し"), "ocr") for x in heads],
                                                       where)
        else:
            kan_ev = None
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

        def named(no, name, src, ev):
            d = {"no": no, "name": name, "name_src": src}
            if ev:
                d["name_evidence"] = ev
            return d

        s, n = scalar_src("本年度")
        out = {
            "id": f"{account_id}/{side}/{m['款']}-{kou_no}-{m['目番号']}",
            "account": account_id, "side": side,
            "kan": named(m["款"], kan_name, kan_name_src, kan_ev),
            "kou": named(kou_no, kou_n, kou_src, kou_ev),
            "moku": named(m["目番号"], moku_n, moku_src, moku_ev),
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
            other_items = [(group[kind], self.by_amount([e for e in x["説明"] if not e.get("金額の記載なし")]))
                           for kind, x in others]
            for e in m["説明"]:
                name, headcount = split_headcount(clean_name(e["name"]))
                it = {}
                if e.get("人数") is not None:
                    it["headcount"] = e["人数"]
                elif headcount is not None:
                    it["headcount"] = headcount
                src = "textlayer" if ("説明欄の金額" in rescued or e.get("名前は文字層_要補正")) else "ocr"
                if e.get("金額の記載なし"):
                    src = scalar_src("本年度")[0]  # 目の額を当てた事項は、目の本年度と同じ出典
                seen[e["amount"]] += 1
                ag = agree(f"説明 {e['amount']}#{seen[e['amount']]}")
                cands = [(name, "ocr")]
                if not e.get("金額の記載なし"):
                    k = (e["amount"], seen[e["amount"]])
                    cands += [(split_headcount(clean_name(o[k]["name"]))[0], g) for g, o in other_items if k in o]
                name, nsrc, nev = self.name("item", cands, where, report=False)
                it = {"name": name, "name_src": nsrc, **({"name_evidence": nev} if nev else {}),
                      "amount": val(e["amount"], src, ag), **it}
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
        seen_sub = Counter()
        is_top = lambda st: st.get("top", st.get("no") is not None)  # noqa: E731
        other_top = [(kind, self.by_amount([s for s in x["節"] if is_top(s)])) for kind, x in others]
        other_sub = [(group[kind], self.by_amount([s for s in x["節"] if not is_top(s)])) for kind, x in others]
        expense = m["side"] == "歳出"
        for st in setsu_in_print_order(m):
            top = is_top(st)
            if ("節", st.get("no")) in fixes and top:
                src, note = "correction", fixes[("節", st.get("no"))]
            elif st.get("出典") == "文字層" or "節" in rescued:
                src, note = "textlayer", None
            else:
                src, note = "ocr", None
            label = clean_name(st["label"])
            if top:
                seen[st["amount"]] += 1
                k = (st["amount"], seen[st["amount"]])
                no, no_src = st.get("no") or None, "ocr"
                # 同じ金額の節の、各読み取りの区分の文字と番号（OCR・文字層・旧 OCR の順）
                labels = [(label, "ocr")] + [(clean_name(o[k]["label"]), group[kind]) for kind, o in other_top if k in o]
                nos = [(no, "ocr")] + [(o[k].get("no"), kind if kind == "textlayer" else "ocr")
                                       for kind, o in other_top if k in o]
                # 歳出の節名は節番号で決まる（地方自治法施行規則）。番号と区分の文字が合う読み取りの番号を使う
                # （区分の文字が合うことで番号の読みを確かめる）。OCR が「11」「19」「24」を「1」と読み、区分の文字
                # 「役務費」「扶助費」「積立金」と食い違った実例がある（文字層・旧 OCR の番号は正しかった）
                hit = next(((n, s) for n, s in nos if expense and n in SETSU_NAMES
                            and any(setsu_label_matches(lab, n) for lab, _ in labels)), None)
                if hit:
                    no, no_src = hit
                    name, nsrc, nev = SETSU_NAMES[no], "reference", None
                elif expense and no in SETSU_NAMES:
                    # 番号の節名と区分の文字が合わない。番号で決まる名前を使い、裏付けなし（番号の読み違いかもしれない）として一覧に出す
                    name, nsrc, nev = SETSU_NAMES[no], "ocr", None
                    self.unresolved.append(("setsu", {**where, "page": st.get("page"), "y": st.get("y"),
                                                      "amount": st["amount"]}, name,
                                            [lab for lab, _ in labels], {"no": no}))
                else:
                    if no is None:
                        # OCR で番号が読めなかった歳入の節: 文字層の同じ金額の節に番号があれば使う。なければ null
                        # （並び順の番号をこしらえない）。歳出は上で区分の文字と合う番号だけを使う
                        tl_no = next((n for n, s in nos[1:] if s == "textlayer" and n), None)
                        if tl_no and not expense:
                            no, no_src = tl_no, "textlayer"
                    name, nsrc, nev = self.name("setsu", labels, {**where, "page": st.get("page"), "y": st.get("y"),
                                                                  "amount": st["amount"]})
                d = {"no": no, "name": name, "name_src": nsrc, **({"name_evidence": nev} if nev else {})}
                if no is not None:
                    d["no_src"] = no_src
                d["amount"] = val(st["amount"], src, agree(f"節 {st['amount']}#{seen[st['amount']]}"), note)
                setsu.append(d)
            elif setsu:
                seen_sub[st["amount"]] += 1
                k = (st["amount"], seen_sub[st["amount"]])
                cands = [(label, "ocr")] + [(clean_name(o[k]["label"]), g) for g, o in other_sub if k in o]
                name, nsrc, nev = self.name("sub", cands, where, report=False)
                setsu[-1].setdefault("sub", []).append({"name": name, "name_src": nsrc,
                                                        **({"name_evidence": nev} if nev else {}),
                                                        "amount": val(st["amount"], src)})
        if setsu:
            out["setsu"] = setsu
        if m.get("注記"):
            out["notes"] = m["注記"]
        src_id = "r8-setsumeisho-toku" if special else "r8-setsumeisho-ippan"
        out["pages"] = [{"source": src_id, "page": p} for p in dict.fromkeys(m["pages"])]
        return out


# 名前の修正表は年度ごと（令和の年 = 西暦 − 2018。2026 → r8-names.json）。年度を変えたら別の修正表を読む
NAME_CORRECTIONS = os.path.join(HERE, "ocr", "corrections", f"r{YEAR - 2018}-names.json")


def apply_name_corrections(rows, fixes, unresolved):
    """名前の修正表（画像で確かめた名前）を書き出した行に当てる。出典は correction。
    款は id「<会計>/<歳入出>/<款>」、項は「…/<款>-<項>」でその款・項のすべての目の行に、目・節・事項は目の行の id に当てる。
    節・事項（item）は目の中の金額（千円）で特定する。当たる先が無い・節が1つに絞れない修正は、修正表が古い（データが変わった）
    ので止める。当てた名前は裏付けのない名前の一覧（unresolved）から除く。返り値: 当てた件数。"""
    n = 0
    for fx in fixes:
        lv, fid, name = fx["level"], fx["id"], clean_name(fx["name"])
        if lv in ("kan", "kou"):
            hits = [r for r in rows if r["id"].startswith(fid + "-") and
                    (lv == "kan" or r["id"].count("-") == fid.count("-") + 1)]
            targets = [r[lv] for r in hits]
        elif lv == "moku":
            targets = [r["moku"] for r in rows if r["id"] == fid]
        elif lv == "setsu":
            # 同じ金額の節が目の中に2つあるときは、画像の節番号（"no"）も合わせて特定する（14款7項2目の 30,000 千円）
            targets = [s for r in rows if r["id"] == fid for s in r.get("setsu", [])
                       if s["amount"]["v"] == yen(fx["amount"]) and ("no" not in fx or s["no"] == fx["no"])]
        elif lv == "item":
            # 説明欄の事項は目の中の金額（千円）で特定する。同じ金額の事項が目の中に2つあるとき（内訳の事項が親と同じ金額のときも）は、
            # 今の名前（"was"。書き出したデータの name を写したもの）も合わせる。全角・半角の違いは clean_name でそろえて比べる
            targets = [it for r in rows if r["id"] == fid for it in r.get("items", [])
                       if it["amount"]["v"] == yen(fx["amount"])
                       and ("was" not in fx or it["name"] == clean_name(fx["was"]))]
        else:
            sys.exit(f"名前の修正表: level が不正（{lv}）")
        if not targets or (lv in ("moku", "setsu", "item") and len(targets) != 1):
            sys.exit(f"名前の修正表: {fid} の {lv}「{fx['name']}」に当たる先が {len(targets)} 件（1件に絞れない・修正表が古い）")
        for t in targets:
            t["name"], t["name_src"] = name, "correction"
            t.pop("name_evidence", None)
            if lv == "setsu" and "set_no" in fx:
                # 画像で確かめた節番号（OCR が番号を読めず、名前の中の数字などを番号にしていたとき）
                t["no"], t["no_src"] = fx["set_no"], "correction"
        n += 1
        unresolved[:] = [u for u in unresolved if not (
            u[0] == lv and (u[1]["id"] == fid or (lv in ("kan", "kou") and u[1]["id"].startswith(fid + "-")))
            and (lv != "setsu" or u[1].get("amount") == fx["amount"]))]
    return n


def name_source_counts(rows):
    """名前の出典ごとの件数（款・項・目は目の行ごと、事項・節・細節は1件ずつ）。"""
    c = Counter()
    for r in rows:
        for lv in ("kan", "kou", "moku"):
            c[f"{lv} {r[lv]['name_src']}"] += 1
        for it in r.get("items", []):
            c[f"item {it['name_src']}"] += 1
        for s in r.get("setsu", []):
            c[f"setsu {s['name_src']}"] += 1
            for sb in s.get("sub", []):
                c[f"sub {sb['name_src']}"] += 1
    return dict(sorted(c.items()))


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
    source_list = json.load(open(SOURCES_FILE, encoding="utf-8"))["sources"]
    for s in source_list:
        p = os.path.join(a.pdf_dir, f"{s['file']}.pdf")
        got = sha256(p)
        if got != s["sha256"]:
            # 手元の原本が一覧と違う（県が資料を差し替えた・取り違えた）。そのまま書き出すと出典の記録と中身が食い違う
            sys.exit(f"原本の SHA256 が sources.json と違う: {s['file']}.pdf（一覧 {s['sha256'][:12]}… / 手元 {got[:12]}…）。"
                     f"資料が差し替わっていないか確かめ、sources.json を更新してから書き出す")
    # 名前の全文検索に使うテキスト資料（説明書・議案は読み取りの側なので入れない。入れると自分自身を見つける）
    corpus = name_evidence.Corpus.from_pdfs({s["id"]: os.path.join(a.pdf_dir, f"{s['file']}.pdf")
                                             for s in source_list if s.get("corpus")})
    ex = Exporter(a.work, json.load(open(w("kessan-kmk.json"))), json.load(open(w("keijougaku.json"))),
                  json.load(open(w("yosansho.json"))), vote, corpus)

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
                # 特別会計の款名は、予算書の本体（議案）の款名と表の見出しの款名から選ぶ（row の中）
                acc = f"special:{SPECIAL_SLUGS[m['会計']]}"
                kan_bill, kan_name, kan_src = yo_kan.get((m["会計"], m["side"], m["款"]), ""), None, None
            else:
                acc = "general"
                kan_bill, kan_name, kan_src = None, kan_names[(m["side"], m["款"])], "text"
            r = ex.row(m, acc, kan_name, kan_src, readings, special, kan_bill)
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

    n_name_fix = apply_name_corrections(rows, json.load(open(NAME_CORRECTIONS, encoding="utf-8"))["修正"], ex.unresolved)

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
    # 外部の資料との突き合わせ（予算書の項・計上額調の款と会計・説明書の計の行）。書き出す行の値で数える
    total_rows = []
    for f in ("setsumeisho-ocr.json", "setsumeisho-toku.json"):
        d = json.load(open(w(f), encoding="utf-8"))
        total_rows += [m for m in (d["目"] if isinstance(d, dict) else d) if m["kind"] == "計"]
    external, external_ng = external_checks(rows, ex.yo, ex.keijou, total_rows)
    for line in external_ng:
        print(f"NG  外部の検算 {line}", file=sys.stderr)
    budget = {
        "schema_version": 1, "gov_id": GOV_ID, "year": YEAR, "year_label": YEAR_LABEL, "basis": "initial",
        "unit_source": "千円", "accounts": accounts, "rows": rows,
        "checks": {
            "rows": len(rows), "all_ok": stats["ok"],
            "rules": {"A_説明欄": rule_counts["A"], "B_財源": rule_counts["B"], "C_比較": rule_counts["C"], "D_節": rule_counts["D"]},
            "external": external,
            "readings": {"agree_2plus": round(vals["2plus"] / vals["n"], 4) if vals["n"] else 0,
                         "confirmed_by_image": vals["image"]},
            "corrections": n_fix,
        },
    }
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"budget-{YEAR}-initial.json"), "w", encoding="utf-8") as f:
        json.dump(budget, f, ensure_ascii=False, indent=1)
        f.write("\n")

    sources = [{k: s[k] for k in ("id", "title", "url", "sha256", "retrieved")} for s in source_list]
    index = {
        "schema_version": 1,
        "gov": {"id": GOV_ID, "name": "福岡県", "kind": "prefecture"},
        "datasets": [{"year": YEAR, "label": YEAR_LABEL, "basis": "initial", "file": f"budget-{YEAR}-initial.json",
                      # verified は、目の全検算と外部の資料との突き合わせがすべて一致したときだけ
                      "status": "verified" if stats["ng"] == 0 and not external_ng else "partial"}],
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
    print(f"名前の出典: {name_source_counts(rows)}（名前の修正表 {n_name_fix} 件）", file=sys.stderr)
    for level, o, n in ex.replaced:
        print(f"名前の置き換え（{level}）: {o} → {n}", file=sys.stderr)
    # 裏付けのない名前の一覧（款・項・目・節。画像で確かめて修正表に記録する）。作業ディレクトリに置く（リポジトリに入れない）
    with open(os.path.join(a.work, "names-unresolved.json"), "w", encoding="utf-8") as f:
        json.dump([{"level": lv, "where": wh, "name": n, "candidates": c, "evidence": ev}
                   for lv, wh, n, c, ev in ex.unresolved], f, ensure_ascii=False, indent=1)
    print(f"裏付けのない名前（款・項・目・節）: {Counter(u[0] for u in ex.unresolved)}", file=sys.stderr)


if __name__ == "__main__":
    main()
