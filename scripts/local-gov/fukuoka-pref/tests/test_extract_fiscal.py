"""三基金の推移と財政の指標の抽出（extract_fiscal.py）の単体テスト。
基金積立状況の行の形は R7（834889_63010204 p.2。一般会計分の下に通常分・交付税精算分等）・H29（834889_63010171 p.2。一般会計分だけ）・
R3（173546 p.2。財政調整基金に内訳がない）を小さく再現したもの。額は千円"""
import pytest

from conftest import load

fx = load("extract_fiscal.py", "extract_fiscal")

R7 = """                                        令和７年度基金の状況
財政調整基金                                                                         総務部
                  年度間の財源調整を図り、財政の健全な運営に資する。
減債基金                                                                           総務部
\f２ 積立状況
財政調整基金                67,473,636    18,496,953          0     509,869         0           0    17,987,084    14,301,934     71,668,655
   （通常分）              38,722,356     5,348,345          0     509,869         0           0     4,838,476     3,578,075     40,492,626
   （交付税精算分等）          28,751,280    13,148,608          0           0         0           0    13,148,608    10,723,859     31,176,029
減債基金                 777,468,806   129,394,300          0    5,716,439        0           0 123,677,861     146,990,592    759,872,514
 一般会計分                34,357,297     5,262,640          0     284,057         0           0   4,978,583       8,526,210     31,093,727
   （通常分）              21,357,444       284,057          0     284,057         0           0             0             0     21,641,501
   （交付税精算分等）          12,999,853     4,978,583          0           0         0           0     4,978,583     8,526,210      9,452,226
 公債管理特別会計分           743,111,509   124,131,660          0    5,432,382        0           0 118,699,278     138,464,382    728,778,787
公共施設整備基金              13,121,376       96,459           0      96,459         0           0            0             0      13,217,835
         合   計       956,430,184   171,140,822   4,151,582   6,878,435   108,552   6,721,713 153,280,540    186,884,994    940,686,012
３ 令和７年度の活用状況
財政調整基金             14,301,934    14,301,934          0
"""

H29 = """                          平成２９年度基金の状況
\f
財政調整基金           11,759,128   1,695,116                  11,702                       1,683,414    2,300,000    11,154,244
減債基金            368,925,924 100,382,909                2,818,440                     97,564,469   73,622,353 395,686,480
 一般会計分           21,323,728      21,087                   21,087                                              21,344,815
 公債管理特別会計分      347,602,196 100,361,822                2,797,353                     97,564,469   73,622,353 374,341,665
公共施設整備基金          8,760,120       7,988                   7,988                                            0     8,768,108
         合   計       1 2 3 4
"""


def test_parse_kikin_reads_rows_before_the_first_total():
    p = fx.parse_kikin(R7)
    assert p["year"] == 2025 and p["page"] == 2
    assert p["rows"]["財政調整基金"] == (67473636, 71668655)
    assert p["rows"]["減債基金/通常分"] == (21357444, 21641501)
    assert p["rows"]["減債基金/一般会計分"] == (34357297, 31093727)
    # 活用状況の表の「財政調整基金」（数が3つ）は読まない
    assert p["rows"]["財政調整基金/通常分"] == (38722356, 40492626)


def test_reserve_parts_r7_uses_the_normal_rows_and_checks_every_tier():
    parts, fails = fx.reserve_parts(fx.parse_kikin(R7))
    assert fails == []
    assert [e for _, e in parts] == [40492626, 21641501, 13217835]


def test_reserve_parts_h29_derives_normal_from_the_general_account_row():
    # H29 は通常分の行がない（交付税精算分等は R3 から）。減債基金の通常分 = 一般会計分
    parts, fails = fx.reserve_parts(fx.parse_kikin(H29))
    assert fails == []
    assert [e for _, e in parts] == [11154244, 21344815, 8768108]


def test_reserve_parts_fails_when_a_tier_does_not_add_up():
    bad = R7.replace("21,357,444       284,057", "21,357,445       284,057")
    _, fails = fx.reserve_parts(fx.parse_kikin(bad))
    assert any("減債基金" in f and "前年度末" in f for f in fails)


def test_reserve_parts_fails_when_a_required_row_is_missing():
    # R4〜 の財政調整基金には通常分・交付税精算分等の行があるはず。読み落としを 0 として基金の全額を通常分にしない
    lines = [ln for ln in R7.splitlines() if "38,722,356" not in ln and "28,751,280" not in ln]
    _, fails = fx.reserve_parts(fx.parse_kikin("\n".join(lines)))
    assert any("財政調整基金" in f and "読めない" in f for f in fails)


def test_reserve_history_checks_the_chain_between_years():
    r6 = R7.replace("令和７年度", "令和６年度")
    hist, fails, n = fx.reserve_history([("R6", r6, "r6-kikin"), ("R7", R7, "r7-kikin")])
    # R6 の年度末（R7 の資料の値をそのまま使った偽物）と R7 の前年度末は一致しない
    assert n["links"] == 1 and any("前年度末" in f for f in fails)
    assert hist[-1]["total"] == (40492626 + 21641501 + 13217835) * 1000


def test_reserve_history_reports_a_missing_year_and_a_wrong_label():
    r5 = R7.replace("令和７年度", "令和５年度")
    _, fails, _ = fx.reserve_history([("R5", r5, "r5-kikin"), ("R6", R7, "r7-kikin")])
    assert any("見出しの年度" in f for f in fails)


def test_parse_gaiyou_reads_target_and_outlook_in_oku_yen():
    line = "                 〇 令和8年度末の財政調整基金等三基金残高を400億円～500億円確保                714億円"
    g = fx.parse_gaiyou("財政調整基金等三基金残高\n" + line)
    assert g == {"year": 2026, "min": 40_000_000_000, "max": 50_000_000_000, "outlook": 71_400_000_000}
    with pytest.raises(ValueError):
        fx.parse_gaiyou("三基金残高 714億円")


def _table(rows):
    hdr = [None, "都道府県名", "財政力指数", "経常収支比率", "実質公債費比率", "将来負担比率", "ラスパイレス指数"]
    return {"全都道府県の主要財政指標": [["全都道府県の主要財政指標"], hdr] + [[None, *r] for r in rows]}


def test_parse_shihyo_finds_the_header_anywhere_and_marks_dashes():
    t = fx.parse_shihyo(_table([["北海道", 0.46, 99.8, 20.0, 307.0, 99.0], ["東京都", 1.1, 80.0, -1.0, "－", 100.0],
                                ["大阪府", 0.8, 90.0, 1.0, "?", 100.0]]))
    assert t["北海道"]["fiscal_capacity"] == 0.46
    assert t["東京都"]["future_burden"] == fx.DASH
    assert t["大阪府"]["future_burden"] is None


def test_indicator_series_median_rank_and_cross_check():
    names = [f"県{i:02d}県" for i in range(46)] + ["福岡県"]
    table = {n: {"fiscal_capacity": 0.3 + i * 0.01, "current_balance": 90.0 + i * 0.1, "debt_service": 10.0,
                 "future_burden": fx.DASH if i == 0 else 100.0 + i} for i, n in enumerate(names)}
    jokyo = [("R6", (2024, {"fiscal_capacity": (0.76, 0.5), "current_balance": (94.6, 1.0),
                            "debt_service": (10.0, 1.0), "future_burden": (146.0, 1.0)}))]
    series, fails, n = fx.indicator_series([("R6", table, "r6-shihyo")], jokyo)
    fc = next(s for s in series if s["key"] == "fiscal_capacity")["values"][0]
    # 財政力指数は高い方が良い: 福岡県（最大）が1位。中央値は 47 件の真ん中
    assert fc["rank"] == 1 and fc["of"] == 47 and fc["median"] == pytest.approx(0.53)
    cb = next(s for s in series if s["key"] == "current_balance")["values"][0]
    assert cb["rank"] == 47
    # 将来負担比率の「－」（負担がない）の団体は良い方に数え、中央値では 0 として数える（0・101〜145・146 の 47 件の真ん中は 123）。同じ値は同じ順位
    fb = next(s for s in series if s["key"] == "future_burden")["values"][0]
    assert fb["of"] == 47 and fb["rank"] == 47 and fb["median"] == pytest.approx(123.0)
    ds = next(s for s in series if s["key"] == "debt_service")["values"][0]
    assert ds["rank"] == 1
    # 総括表との突き合わせ: 前年度（R5）は主要財政指標一覧がないので数えない。本年度の4つは一致
    assert n["checked"] == 4 and fails == []


def test_indicator_series_fails_on_a_dash_outside_future_burden():
    names = [f"県{i:02d}県" for i in range(46)] + ["福岡県"]
    table = {n: {"fiscal_capacity": 0.5, "current_balance": fx.DASH if i == 0 else 90.0, "debt_service": 10.0,
                 "future_burden": 100.0} for i, n in enumerate(names)}
    _, fails, _ = fx.indicator_series([("R6", table, "r6-shihyo")], [])
    assert any("current_balance" in f or "経常収支比率" in f for f in fails)


def test_indicator_series_fails_on_mismatch_and_missing_prefectures():
    table = {"福岡県": {"fiscal_capacity": 0.6, "current_balance": 95.0, "debt_service": 11.0, "future_burden": 245.0}}
    jokyo = [("R6", (2024, {"fiscal_capacity": (0.61, 0), "current_balance": (95.0, 0), "debt_service": (11.0, 0),
                            "future_burden": (245.0, 0)}))]
    _, fails, _ = fx.indicator_series([("R6", table, "r6-shihyo")], jokyo)
    assert any("47 件" in f for f in fails)
    assert any("fiscal_capacity" in f and "総括表" in f for f in fails)


def test_parse_jokyo_reads_year_and_current_previous_values():
    rows = [
        ["都道府県名", "福岡県", "職員の状況", "区分", "令和6年度(千円)", "令和5年度(千円)", "区分", "令和6年度(千円･％)", "令和5年度(千円･％)"],
        ["歳出総額", 1.0, 2.0, "経常収支比率", 95.6, 97.3],
        ["教育長", 1.0, 8800.0, "実質収支", 1.0, 2.0, "財政力指数", 0.63618, 0.61396],
        ["うち日本人(人)", 1.0, "実質単年度収支", 1.0, -3.0, "　実質公債費比率", 11.9, 11.3],
        ["令06.01.01(人)", 1.0, "一般職員", 1.0, 2.0, 3.0, "基準財政収入額", 5.0, 6.0, "　将来負担比率", 245.3, 248.4],
    ]
    year, vals = fx.parse_jokyo({"総括表": rows})
    assert year == 2024
    assert vals == {"current_balance": (95.6, 97.3), "fiscal_capacity": (0.63618, 0.61396),
                    "debt_service": (11.9, 11.3), "future_burden": (245.3, 248.4)}


def test_era_year():
    assert fx.era_year("R7") == 2025 and fx.era_year("令和元年度") == 2019 and fx.era_year("平成２９年度") == 2017
