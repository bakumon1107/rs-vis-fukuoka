# ワークスペースルール

## ファイル操作の制約

- **`docs/プロンプトログ.ignore.md`**: ユーザーの作業ログ。Agentは直接修正・編集・変更しないこと。内容の参照（読み取り）は可。
- **回答の出力先**: 設計・調査・分析などの回答を出力する場合は `docs/tasks/YYYYMMDD_HHMM_{タイトル}.md` に保存すること（日時は `TZ=Asia/Tokyo date +%Y%m%d_%H%M` で取得）。
  - **地方版（local-gov）の作業**は `docs/local-gov/tasks/` に置く（自治体固有の調査は `docs/local-gov/<自治体>/`）。方針・ブランチ運用は `docs/local-gov/README.md` を参照。
  - **調査・作業で得たノウハウは必ず書き残す**: 自治体共通は `docs/local-gov/knowhow/`、自治体固有は `docs/local-gov/<自治体>/README.md`。新しい調査を始める前にまずこれらを読む。

## 地方版のブランチ運用

- `main` は本家（upstream = team-mirai-volunteer/rs-vis）のミラー。直接変更・コミットしない。
- 地方版の本流は `local-main`。作業ブランチは `local-main` から切り、PR で `local-main` にマージする。
- 本家（upstream）への push・PR は行わない。`local-main` への PR もユーザーの指示があってから作る。
- **作業は必ず worktree で行う**（メインのディレクトリ `rs-vis-fukuoka` では変更しない。mirai-gikai-fukuoka-city と同じ運用）:
  ```bash
  git worktree add ../rs-vis-fukuoka-<短い名前> -b <種類>/<名前> local-main
  # .claude/settings.local.json・.env があればコピーする（2026-11-06 時点ではどちらもない）
  # 画面・ビルドの作業なら依存を入れる: cd ../rs-vis-fukuoka-<短い名前> && npm ci
  # 開発サーバーで国版の画面も開くなら、国版のデータを展開する（.gz → .json。.gitignore 済み）: bash scripts/decompress-data.sh
  #   展開しないと国版の画面が /data/*.json を 404 にする（ビルドでは prebuild が自動で展開する）
  # ブランチを載せ直した（rebase）後に開発サーバーが地方版のページを 404 にしたら、開発サーバーを再起動する
  ```
- **原本（PDF）・OCR の結果・作業ファイルは `/tmp` に置かない**（セッションが替わると消える。2026-11-13 に消えて、OCR を約2時間かけて取り直した）。
  置き場所はリポジトリの外の決まった場所（ホームの `data/rs-vis-fukuoka/`。環境変数 `FUKUOKA_DATA`）。中身と作り方は `docs/local-gov/fukuoka/データの作り方.md`
  未マージの作業ブランチの文書に依存するときは、そのブランチの上に重ねて切り、マージの順番を PR の説明に書く。
- **作業の前に設計書を書いて確認を取る**（`docs/local-gov/tasks/`）。調査は設計の材料として先に行ってよい。
