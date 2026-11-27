# 予算ビュー＠福岡県

福岡県の予算・決算を、会計・款・項・目のサンキー図と基金の推移でたどる**非公式**のビューアです。

**サイト: https://bakumon1107.github.io/yosan-view-fukuoka-pref/**

> このサービスは政党チームみらいが運営しているものではありません。
> 数字は福岡県が公開している予算書・決算書等をもとにこのサイトで加工したものです。正確な数字は原資料をご確認ください。

## 見られるもの

| 画面 | 内容 |
|---|---|
| サンキー図 | 当初予算（令和8年度）・補正後予算・決算（令和6年度）を切り替えて、お金の流れをたどる |
| 　一般会計 | 財源 → 款 → 項 → 目 → 説明欄の事項。「一般財源」の中身、選んだ範囲の人件費の割合 |
| 　全会計 | 歳入の款 → 会計 → 款 → 項 → 目。全会計の純計（会計間の繰入れを除いた額） |
| 　公営企業会計 | 収入 → 会計・条（収益的・資本的） → 支出の項 → 目。資本的収支の不足を埋める補填財源 |
| 基金 | 基金ごとの残高の推移 |
| データについて | 数字の作り方・検算の方法と結果・使った資料の一覧 |

## 数字の作り方

- 福岡県の「予算に関する説明書」（スキャン画像の PDF）を文字認識（OCR）で読み取り、目ごとの本年度・前年度・財源内訳・節・説明欄の事項を取り出しています。決算はテキスト PDF から取り出しています
- 金額は資料に印字された数字（千円単位）を円に直したもので、**推計や按分はしていません**
- 読み取った数字は、目ごとの合計・財源内訳・節の合計と、予算書の本体・当初予算計上額調の額との突き合わせで検算しています。結果はサイトの「データについて」に載せています
- 名前の読み誤りは、複数の読み取りの突き合わせと、原本の画像での確認で直しています

## 開発

本家「[政府予算ビュー](https://github.com/team-mirai-volunteer/rs-vis)」（国の予算の可視化）のフォークです。
地方版のページだけを静的サイトとして書き出し、GitHub Pages に置いています（国版のページ・API は含めません）。

```bash
npm ci
npm run dev                         # 開発サーバー（http://localhost:3000/local/fukuoka-pref）
npm run lint && npm run typecheck && npm test
# 福岡県版の静的書き出し
NEXT_PUBLIC_SITE_EDITION=local NEXT_PUBLIC_LOCAL_GOV_ID=fukuoka-pref NEXT_PUBLIC_BASE_PATH=/yosan-view-fukuoka-pref npx next build
node scripts/local-gov/assemble-pages.mjs   # 公開物を out/ に組み立てる
```

- 地方版の方針・ブランチ運用・版の切り替え: [docs/local-gov/README.md](../docs/local-gov/README.md)
- 福岡県の資料の癖とデータの作り方: [docs/local-gov/fukuoka/](../docs/local-gov/fukuoka/)
- データの取り出し（PDF・OCR・検算）: `scripts/local-gov/fukuoka-pref/`
- 公開: `local-main` へのマージで `.github/workflows/pages-local.yml` がデプロイします

ブランチは `local-main` が本流です（`main` は本家のミラー）。直下の `README.md` は本家のものです。

## ライセンス・運営

- ライセンス: [AGPL-3.0](../LICENSE)（本家と同じ）
- 運営: バクモン（連絡先: [X @bakumon0907](https://x.com/bakumon0907)）
- 利用規約・プライバシーポリシーはサイトのフッターから
