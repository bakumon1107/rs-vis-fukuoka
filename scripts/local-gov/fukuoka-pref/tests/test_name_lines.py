"""行に分かれた名前のつなぎ方（name_lines.NameJoiner）の単体テスト。実例の並び方を再現する。"""
from conftest import load

nl = load("name_lines.py", "name_lines")


def feed(joiner, lines):
    """lines: ("name", 断片) か ("entry", 行の名前)。作った記録の名前の一覧を返す。"""
    out = []
    for kind, text in lines:
        if kind == "name":
            joiner.name_only(text)
        else:
            e = {"name": joiner.entry_name(text)}
            out.append(e)
            joiner.opened(e)
    return [e["name"] for e in out]


def test_three_line_name_in_bill():
    # 予算書の本体「県営埠頭施設整備／1 8,044,889／運営事業費」（款と項で同じ名前が続く）
    j = nl.NameJoiner(prepend_to_named=False)
    got = feed(j, [("name", "県営埠頭施設整備"), ("entry", ""), ("name", "運営事業費"),
                   ("name", "県営埠頭施設整備"), ("entry", ""), ("name", "運営事業費"),
                   ("entry", "公債費")])
    assert got == ["県営埠頭施設整備運営事業費", "県営埠頭施設整備運営事業費", "公債費"]


def test_bill_does_not_prepend_to_named_entry():
    # 予算書の本体では、上の行のかけらを名前のある行の前に付けない（ページ番号「-3-」が前に付いた実例）
    j = nl.NameJoiner(prepend_to_named=False)
    assert feed(j, [("name", "かけら"), ("entry", "宿泊税")]) == ["宿泊税"]


def test_enterprise_prepends_to_named_entry():
    # 公営企業の予算実施計画「流域下水道／1 管理費負担金」
    j = nl.NameJoiner(prepend_to_named=True)
    assert feed(j, [("name", "流域下水道"), ("entry", "管理費負担金")]) == ["流域下水道管理費負担金"]


def test_enterprise_upper_and_lower_lines():
    # 病院事業「支払利息及び／1 29,777／企業債取扱諸費」の次に「2 消費税」
    j = nl.NameJoiner(prepend_to_named=True)
    got = feed(j, [("name", "支払利息及び"), ("entry", ""), ("name", "企業債取扱諸費"), ("entry", "消費税")])
    assert got == ["支払利息及び企業債取扱諸費", "消費税"]


def test_two_upper_and_two_lower_lines():
    # 名前が4行（上2行・番号と金額の行・下2行）。番号は縦の真ん中なので、上と下は同じ数。
    # 以前は上の1行目を2行目で上書きし、下は1行しか足さなかった
    j = nl.NameJoiner(prepend_to_named=False)
    got = feed(j, [("name", "あ"), ("name", "い"), ("entry", ""), ("name", "う"), ("name", "え"),
                   ("name", "次の上の行"), ("entry", ""), ("name", "次の下の行")])
    assert got == ["あいうえ", "次の上の行次の下の行"]


def test_reset_drops_fragment_from_previous_page():
    # 前のページの末尾のかけらを、次のページの最初の「名前が空の行」に付けない
    j = nl.NameJoiner(prepend_to_named=False)
    j.name_only("前のページのかけら")
    j.reset()
    assert feed(j, [("entry", ""), ("name", "予備費")]) == ["予備費"]


def test_lower_line_only():
    # 番号と金額の行に名前がなく、下の行にだけ名前がある
    j = nl.NameJoiner(prepend_to_named=False)
    assert feed(j, [("entry", ""), ("name", "予備費")]) == ["予備費"]
