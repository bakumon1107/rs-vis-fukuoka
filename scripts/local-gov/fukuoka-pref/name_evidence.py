"""名前の裏付けを探す（名前の補正の設計 docs/local-gov/tasks/20261106_1241_名前の補正の設計.md の 3章）。

金額には検算があるが、名前にはない。同じ箇所の名前の「候補」（独立した読み取り＝説明書の OCR・発行元の文字層・旧 OCR・
予算書の本体の文字層・表の見出しの OCR）を集め、それぞれに裏付けがあるかを調べて、いちばん強い裏付けのある候補を採る。

裏付けの強さ（強い順）:
    reference … 別年度のテキスト資料（R6 決算の款項目別明細表）の同じ款の中の名前と、崩れとして説明がつく（照合の規則は呼び出し側）
    search    … 手元のテキスト資料（本物のテキスト PDF）の全文に、その名前が1つの語として出てくる（4文字以上）
    readings  … 独立した読み取りの2つ以上が同じ名前
    ocr       … 裏付けなし（候補の先頭をそのまま使う）

全文検索で分かるのは「その名前が実在する」ことだけで、「この箇所の名前である」ことではない。
そのため候補は必ず同じ箇所の読み取りから作り、近いだけの別の名前を資料から拾ってくることはしない。
また、読み取りが文字を落とした名前（「子育て応援基金繰入金」→「子育て応援」）も、資料のどこかに語として出てくることがある
（R8 の名前の頭・末尾を1〜2文字落とした 5,059 通りのうち 73 通りが資料に出てきた。2026-11-06 の計測）。
同じ箇所の別の読み取りがその名前を含む長い名前なら、短い方を採らない（食い違いとして画像での確認に回す）。
"""
import re
import subprocess
import unicodedata

# OCR で起きる字形の取り違え（説明書の OCR・文字層で実例のあるもの）。候補を増やすのに使う（元の候補も残す）
GLYPH_FIXES = str.maketrans({"壳": "売", "讓": "譲", "產": "産", "齡": "齢", "徵": "徴", "·": "・", "•": "・",
                             "费": "費", "务": "務", "厅": "庁", "县": "県", "龄": "齢", "收": "収", "贷": "貸",
                             "换": "換", "减": "減", "债": "債", "资": "資", "补": "補", "设": "設", "业": "業",
                             "农": "農", "经": "経", "济": "済", "总": "総", "审": "審", "议": "議", "报": "報",
                             "电": "電", "气": "気", "车": "車", "园": "園", "试": "試", "验": "験", "图": "図",
                             "书": "書", "馆": "館", "疗": "療", "护": "護", "儿": "児"})
# 「人」→「入」は「繰人金」「収人」で実例があるが、「法人」「個人」を壊すので、語の形で直す
WORD_FIXES = [("繰人", "繰入"), ("収人", "収入"), ("受人", "受入")]

MIN_SEARCH_LEN = 4  # これより短い名前（「使用料」「雑入」）は資料のどこにでも出るので、全文検索の裏付けにしない
# 語の続きとみなす文字（ひらがな・カタカナ・漢字）。見つかった名前の前後がこれなら、もっと長い語の一部。
# 濁点・半濁点だけの字（U+3099〜309C）は除く（文字層で名前の前に「゚」が付く。「゚証紙収入」）
WORD_CHAR = re.compile(r"[ぁ-ゖゝ-ゟ゠-ヿ々一-鿿]")


def normalize(s: str) -> str:
    """比較用: 全角半角をそろえ、空白・括弧の線・○を除く。横棒1本の「一」が落ちた「般会計」を直す。
    括弧の線・罫線は、名前の先頭・字の間に「L」「I」「l」「J」「|」「,」「.」「a」として読まれる（文字層で「l自動車税」
    「人材活躍l労働総務費」、OCR で「a恩給及び退職年金費」「J利子及び配当金」）。先頭の英字は、次が漢字のときだけ除く
    （実例はどれも次が漢字。「DX・」「IoT」「JR」「Jアラート」のような本当の英字の名前を残す）。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"\s", "", s)
    s = re.sub(r"^(?:[○〇|｜,.、・゙-゜]|[LIlaJ](?=[一-鿿]))+", "", s)
    s = re.sub(r"(?<=[^\x00-\x7f])[lI|｜](?=[^\x00-\x7f])", "", s)
    s = re.sub(r"^般会計", "一般会計", s)
    return s


def variants(name: str) -> list[str]:
    """候補の名前と、字形の取り違えを直した形（重複なし・元の形が先）。"""
    base = normalize(name)
    if not base:
        return []
    fixed = base.translate(GLYPH_FIXES)
    for a, b in WORD_FIXES:
        fixed = fixed.replace(a, b)
    return [base] if fixed == base else [base, fixed]


class Corpus:
    """手元のテキスト資料の全文。空白・改行を除いてつなぎ、名前が1つの語として出てくるか（前後が語の続きでないか）を調べる。
    改行を除くのは、表の名前が折り返し・字間の空白で割れるため（「総 務 管 理 費」）。"""

    def __init__(self, texts: dict[str, str]):
        self.texts = {k: re.sub(r"\s", "", unicodedata.normalize("NFKC", v)) for k, v in texts.items()}
        self._cache = {}

    @classmethod
    def from_pdfs(cls, paths: dict[str, str]):
        """資料の id → PDF のパス。pdftotext（段組みを保たない既定の読み順）で全文を取る。
        -layout は字間の広い見出しで語の切れ目を誤る（2026-11-06 の計測で、落とした名前を誤って見つける数が増えた）。"""
        return cls({k: subprocess.run(["pdftotext", "-enc", "UTF-8", p, "-"], capture_output=True, text=True,
                                      check=True).stdout for k, p in paths.items()})

    def find(self, name: str) -> list[str]:
        """名前が1つの語として出てくる資料の id（なければ空）。"""
        if len(name) < MIN_SEARCH_LEN:
            return []
        if name not in self._cache:
            out = []
            for k, t in self.texts.items():
                i = t.find(name)
                while i >= 0:
                    j = i + len(name)
                    if not (i > 0 and WORD_CHAR.match(t[i - 1])) and not (j < len(t) and WORD_CHAR.match(t[j])):
                        out.append(k)
                        break
                    i = t.find(name, i + 1)
            self._cache[name] = out
        return self._cache[name]


RANK = {"reference": 3, "search": 2, "readings": 1}


def is_subsequence(short: str, long: str) -> bool:
    """short の字が、順番どおりに long に全部含まれる（long は short に字を足したもの）。"""
    it = iter(long)
    return all(ch in it for ch in short)


def contradicts(name: str, other: str) -> bool:
    """同じ箇所の別の読み取り other が、name を採ることに疑いをかける形か。
    - other が name に字を足した形（name は字を落とした読み取りかもしれない。OCR と旧 OCR は同じ切り抜きを読むので、
      同じ字を一緒に落とす: 2つとも「人材育成活推進費」、文字層は「人材育成活躍推進費」。281298 p220）
    - other が name と同じ字の並べ替え（2行の名前の字の順が混ざった。OCR「人労総材活務躍働費」、文字層「人材活躍労働総務費」）"""
    if other == name:
        return False
    if len(other) > len(name) and is_subsequence(name, other):
        # 足した字が記号・英字だけ（「ゴルフ場利,用税交付金」の「,」）なら、読み取りのごみで疑いにしない
        extra = list(other)
        for ch in name:
            extra.remove(ch)
        return any(WORD_CHAR.match(ch) for ch in extra)
    return len(other) == len(name) and sorted(other) == sorted(name)


def char_vote(cands: list[tuple[str, str]]):
    """1字ずつの多数決: 読み取りのうち、どの字も「別の系統」の読み取りの1つ以上が同じ位置（順番を保った対応）で
    同じ字を読んでいるもの。作った名前ではなく、実際の読み取りの1つをそのまま返す（ちょうど1つに決まるときだけ）。
    cands: [(名前, 系統)]。同じ系統の読み取りは支えに数えない（OCR と旧 OCR は字を一緒に落とし、字の順を一緒に混ぜる）。
    例: OCR「ゴルフ場利用税交付金」・文字層「ゴルフ場利,用税交付金」→ OCR の読み取り（どの字も文字層が読んでいる）。
    例: OCR「県土整備事務所使用料」・文字層「県士整備事務所使用料」→ 決まらない（「土」を読んだのは同じ系統の旧 OCR だけ）。"""
    import difflib
    ok = set()
    for i, (h, g) in enumerate(cands):
        sup = [0] * len(h)
        for j, (r, rg) in enumerate(cands):
            if j == i or rg == g:
                continue
            for blk in difflib.SequenceMatcher(None, h, r, autojunk=False).get_matching_blocks():
                for p in range(blk.a, blk.a + blk.size):
                    sup[p] = 1
        if h and min(sup) >= 1:
            ok.add(h)
    return ok.pop() if len(ok) == 1 else None


def resolve(candidates, corpus: Corpus, reference=None):
    """同じ箇所の名前の候補から名前を選ぶ。
    candidates: [(名前, 系統)]（または名前だけ。そのときは候補ごとに別の系統）。先頭がいちばん信頼できる読み取り。
      系統: 独立でない読み取りをまとめる名札。OCR（PP-OCRv6）と旧 OCR は同じ画像の同じ切り抜きを同じ規則でつなぐので、
      同じ字を一緒に落とし、2行の名前の字の順を一緒に混ぜる（2つとも「人材育成活推進費」「選委員会費挙管理」）。
      一致を数えるのは系統の数（同じ系統どうしの一致は1つと数える）。
    reference: 名前 → 照合できた参照の名前（なければ None）を返す関数（R6 決算との照合。規則は呼び出し側）。
    返り値: (名前, 出典, 根拠)。出典は reference / search / readings / ocr。
    根拠: search は見つかった資料の id、readings は一致した系統の数（1字ずつの多数決は "chars"）、
    ocr で食い違いがあれば {"conflict": [...]}。

    いちばん強い裏付けの名前が1つに決まらない（同じ強さで別の名前が並び、一致した系統の数も同じ）とき、
    また別の系統の読み取りが採る名前に疑いをかける形（contradicts: 字を足した形・字の並べ替え）のときは、決めずに ocr とする。
    並べ替えの疑いは readings で採る名前にだけかける（資料・参照で見つかった名前は、字の順が資料で確かめられている）。"""
    pairs = [(c, str(i)) if isinstance(c, str) else c for i, c in enumerate(candidates)]
    cands = [(vs, g) for vs, g in ((variants(c), g) for c, g in pairs) if vs]
    if not cands:
        return "", "ocr", None
    groups = {}  # 名前 → それを読んだ系統
    for vs, g in cands:
        for v in vs:
            groups.setdefault(v, set()).add(g)
    best = {}  # 採る名前 → (強さ, 一致した系統の数, 出典, 根拠)
    for vs, _ in cands:
        for v in vs:
            agree = len(groups[v])
            ref = reference(v) if reference is not None else None
            if ref:
                got = (RANK["reference"], agree, "reference", None, ref)
            elif corpus is not None and corpus.find(v):
                got = (RANK["search"], agree, "search", corpus.find(v)[:3], v)
            elif agree >= 2:
                got = (RANK["readings"], agree, "readings", agree, v)
            else:
                continue
            name = got[4]
            if name not in best or got[:2] > best[name][:2]:
                best[name] = got[:4]
    first = cands[0][0][0]
    if not best:
        voted = char_vote([(vs[-1], g) for vs, g in cands])  # 字形の取り違えを直した形で多数決
        if not voted:
            return first, "ocr", None
        best[voted] = (RANK["readings"], 1, "readings", "chars")
    top = max(b[:2] for b in best.values())
    winners = [n for n, b in best.items() if b[:2] == top]
    if len(winners) > 1:
        # 同じ強さで並んだ名前の一方が他方に字を足した形なら、長い方（短い方は字を落とした読み取り）
        longest = [n for n in winners if not any(contradicts(n, o) for o in winners)]
        if len(longest) != 1:
            return first, "ocr", {"conflict": sorted(winners)}
        winners = longest
    name = winners[0]
    rank, n_agree, src, ev = best[name]
    # 疑い: 採る名前を読んでいない系統の読み取りが、採る名前に字を足した形・字の並べ替えになっている
    support = groups.get(name, set())
    doubt = sorted({v for vs, g in cands if g not in support for v in vs
                    if contradicts(name, v) and (src == "readings" or len(v) > len(name))})
    if doubt:
        return first, "ocr", {"conflict": [name] + doubt}
    return name, src, ev
