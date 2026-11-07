"""名前の裏付け（name_evidence.py）と、書き出しの節名の照合（export_fukuoka_pref.setsu_label_matches）の単体テスト。

どのテストも、R8 の説明書で実際に起きた読み取りの崩れ方（コメントに出典）を小さな入力で再現している。
とくに「採ってはいけない名前」（字を落とした名前・字の順が混ざった名前）を採らないことを確かめる。
"""
from conftest import load

ne = load("name_evidence.py", "name_evidence")
ex = load("export_fukuoka_pref.py", "export_fukuoka_pref")

CORPUS = ne.Corpus({
    "r6": "款項目別明細表\n1 共 同 事 業 拠 出 金 12,345\n総務管理費 1,000\n子育て応援基金繰入金について\n",
})


class TestNormalize:
    def test_bracket_lines(self):
        # 文字層・OCR で括弧の線が英字・記号として名前に入る（「l自動車税」「人材活躍l労働総務費」「a恩給…」「J利子…」）
        assert ne.normalize("l自動車税") == "自動車税"
        assert ne.normalize("人材活躍l労働総務費") == "人材活躍労働総務費"
        assert ne.normalize("a恩給及び退職年金費") == "恩給及び退職年金費"
        assert ne.normalize("J利子及び配当金") == "利子及び配当金"
        assert ne.normalize("般会計繰入金") == "一般会計繰入金"

    def test_keeps_real_latin_prefixes(self):
        assert ne.normalize("DX・生産性向上支援資金") == "DX・生産性向上支援資金"
        assert ne.normalize("IoT推進費") == "IoT推進費"
        assert ne.normalize("Ｊアラート訓練費") == "Jアラート訓練費"   # 次がカタカナなら本当の英字

    def test_real_latin_name_found_in_corpus(self):
        corpus = ne.Corpus({"r8": "1 Jアラート訓練費 1,000"})
        assert ne.resolve([("Ｊアラート訓練費", "ocr")], corpus) == ("Jアラート訓練費", "search", ["r8"])


class TestCorpus:
    def test_found_across_spaces_and_lines(self):
        # 表の名前は字間の空白・折り返しで割れる
        assert CORPUS.find("共同事業拠出金") == ["r6"]

    def test_part_of_a_longer_word_is_not_found(self):
        # 頭や末尾の字を落とした名前は、資料の長い語の一部としては見つけない
        assert CORPUS.find("務管理費") == []
        assert CORPUS.find("子育て応援") == []

    def test_short_names_are_not_searched(self):
        assert CORPUS.find("事業費") == []


class TestResolve:
    def test_search_beats_garbled_ocr(self):
        # 特別会計の款名: 議案の文字層「北‘同事業拠出金」・OCR の見出し「共同事業拠出金」（281299）
        assert ne.resolve([("北‘同事業拠出金", "bill"), ("共同事業拠出金", "ocr")], CORPUS) == \
            ("共同事業拠出金", "search", ["r6"])

    def test_readings_need_two_independent_groups(self):
        # OCR と旧 OCR は同じ切り抜きを読むので、2つの一致は1つと数える（281298 p220 の「人材育成活推進費」）
        name, src, ev = ne.resolve([("人材育成活推進費", "ocr"), ("人材育成活躍推進費", "textlayer"),
                                    ("人材育成活推進費", "ocr")], CORPUS)
        assert src == "ocr" and ev == {"conflict": ["人材育成活推進費", "人材育成活躍推進費"]}

    def test_readings_from_two_groups(self):
        assert ne.resolve([("商業費", "bill"), ("商業費", "ocr"), ("商業美費", "ocr")], CORPUS) == ("商業費", "readings", 2)

    def test_scrambled_order_is_doubted(self):
        # OCR と旧 OCR が2行の名前の字の順を一緒に混ぜ、文字層は正しい順（「選委員会費挙管理」）。
        # 同じ系統の2つの一致では採らず、どちらの順も裏付けがないので決めない（画像で確かめる一覧に回る）
        assert ne.resolve([("選委員会費挙管理", "ocr"), ("選挙管理委員会費", "textlayer"),
                           ("選委員会費挙管理", "ocr")], CORPUS) == ("選委員会費挙管理", "ocr", None)

    def test_scrambled_order_doubts_readings(self):
        # 2つの系統が一致しても、3つ目の系統が字の並べ替えを読んでいれば決めない
        name, src, ev = ne.resolve([("公費債", "bill"), ("公費債", "ocr"), ("公債費", "textlayer")], CORPUS)
        assert src == "ocr" and ev == {"conflict": ["公費債", "公債費"]}

    def test_reference_explains_scrambled_reading(self):
        # R6 決算の目名との照合（並べ替えとして説明がつく）。並べ替えの読み取りは疑いにしない
        ref = {"選委員会費挙管理": "選挙管理委員会費", "選挙管理委員会費": "選挙管理委員会費"}.get
        assert ne.resolve([("選委員会費挙管理", "ocr"), ("選挙管理委員会費", "textlayer")], CORPUS, ref) == \
            ("選挙管理委員会費", "reference", None)

    def test_reference_doubted_by_longer_reading(self):
        # R6 にある短い名前（「地域振興費」）に、別の読み取りが字を足した R8 の名前（「地域振興総務費」）を読んでいる
        ref = {"地域振興費": "地域振興費"}.get
        name, src, ev = ne.resolve([("地域振興費", "ocr"), ("地域振興総務費", "textlayer")], CORPUS, ref)
        assert src == "ocr"

    def test_junk_characters_are_not_doubt(self):
        name, src, _ = ne.resolve([("ゴルフ場利用税交付金", "ocr"), ("ゴルフ場利,用税交付金", "textlayer")], CORPUS)
        assert (name, src) == ("ゴルフ場利用税交付金", "readings")

    def test_glyph_fix_variants_agree(self):
        assert ne.resolve([("不動産壳払収入", "ocr"), ("不動産売払収入", "textlayer")], CORPUS)[:2] == \
            ("不動産売払収入", "readings")

    def test_no_evidence_keeps_first(self):
        assert ne.resolve([("積\\'金", "bill"), ("積立金", "ocr")], CORPUS) == ("積\\'金", "ocr", None)

    def test_empty(self):
        assert ne.resolve([], CORPUS) == ("", "ocr", None)


class TestCharVote:
    def test_every_char_supported_by_other_group(self):
        assert ne.char_vote([("県土整備事務所使用料", "ocr"), ("県土整備事務所使用料x", "textlayer")]) == "県土整備事務所使用料"

    def test_same_group_does_not_support(self):
        # 「土」を読んだのは同じ系統の旧 OCR だけ
        assert ne.char_vote([("県土整備事務所使用料", "ocr"), ("県士整備事務所使用料", "textlayer"),
                             ("鼎土整備事務所使用料", "ocr")]) is None


class TestSetsuLabel:
    def test_scrambled_two_line_label(self):
        # 2行の区分の字の順が混ざる（「負担金補助／及び交付金」→「負及び交付担金補助金」）
        assert ex.setsu_label_matches("負及び交付担金補助金", 18)
        assert ex.setsu_label_matches("負及担交金補付助金", 18)      # 1字欠け
        assert ex.setsu_label_matches("扶助力費", 19)                # 余分な字が1字
        assert ex.setsu_label_matches("補及償び賠償補填金", 21)      # 「填」は「塡」の異体字

    def test_mismatch(self):
        # OCR が「11」を「1」と読んだ（区分の文字は「役務費」）
        assert not ex.setsu_label_matches("役務費", 1)
        assert not ex.setsu_label_matches("担金補助", 18)            # 半分しか読めていない

    def test_no_two_official_names_match_each_other(self):
        names = ex.SETSU_NAMES
        assert [(a, b) for a in names for b in names if a != b and ex.setsu_label_matches(names[b], a)] == []
