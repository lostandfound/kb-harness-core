# `kb` CLI リファレンス

`python3 -m pip install <このパッケージ>` で `kb` コマンドが入る。導入先 KB リポジトリ内で実行し、`kb-domain.yml` を起点にプロジェクトを解決する。

## 共通仕様

| 項目 | 内容 |
|---|---|
| `--start DIR` | プロジェクト探索の起点。省略時はカレントディレクトリから上へ `kb-domain.yml` を探す。`kb okf validate` の `PATH` 相対解決にも使う |
| `--format text\|json` | 出力形式。`json` は `ok` / `changed` / `diagnostics` を基本フィールドとし、CI やエージェントから機械的に扱える。成功・失敗によらず常に stdout に出るので、消費側は 1 本のストリームだけ読めばよい |
| `--dry-run` | 書き込み系コマンドで、変更を適用せず統一 diff のみを返す。text 出力では対象パスを `would update: <path>` と表示し、実際に書き込んだ `updated: <path>` とは書き分ける |

終了コード:

| コード | 意味 |
|---|---|
| `0` | 成功・同期済み |
| `1` | 検証不合格・差分あり |
| `2` | 引数または設定の不備 |
| `3` | 予期しない内部エラー |

書き込み系（`entity create` / `reference create` など）の spec エラーは、コマンドの起動そのものが不正（spec が読めない・必須項目が欠けている・出力先が不正）なら `2`、spec は読めたが内容が検証を通らない（重複 ID、書式不正など）なら `1` を返す。両コマンドで揃えてある。

## 読み取り・検証

### `kb project show`

`kb-domain.yml` の解決結果（ドメイン名、content_root など）を表示する。

### `kb validate [--check-urls [--for ENTITY]... [--ref ID]...]`

KB 全体を検証する。frontmatter・リンク・relations の型制約・タグ語彙・出典参照・Claim・`evals/rag-eval.yml`・述語の階層（`vocabulary.yml` の `broader` / `maps_to`、[設定リファレンス](configuration.md#述語の階層と標準対応)）を対象とする。ERROR にならない指摘は `warnings` に入れる。text では `<SEVERITY> <message>` の形で stderr に、json では `diagnostics` と同じ構造の `{severity, code, message}` の配列で返す（`severity` は `warning` か `info`、`message` は text と同じ文字列）。コードは `validation.description.same_as_title` / `validation.description.long` / `validation.reference.unreferenced` / `validation.reference.pending_referenced` / `validation.reference.pending_unreferenced`（info）/ `validation.relation.refinable` / `validation.relation.unclassified`（info）/ `validation.link.root_relative` / `concern.legacy_ledger` / `validation.url.doi_registry_unreachable`（`--check-urls` のときだけ）。本文リンクはリンク元ファイルからの相対パスで解決し、存在しないリンク先を ERROR にする（[設定リファレンス](configuration.md#本文リンク)）。旧形式のルート相対リンク（`/people/example.md`）は解決するが、件数をまとめて `validation.link.root_relative` の WARNING で示す。`related-to` のエッジは未分類として件数を INFO で報告し、始点と終点の型が層 1 のちょうど 1 つの述語に収まるものは精緻化の余地として WARNING を出す。`kb-domain.yml` に `views.root` があればビュー定義も、`concerns.root` があれば懸念の定義も検査する（[設定リファレンス](configuration.md#ビュー任意)、[懸念台帳](configuration.md#懸念台帳任意)）。`concerns.root` があるのに旧来の `docs/CONCERNS.md` が残っていれば `concern.legacy_ledger` の WARNING を出す。`kb-domain.yml` に `validate.extra_checks` があれば本体の検証後に順に実行し、失敗を ERROR として集約する（[設定リファレンス](configuration.md#kb-domainyml)）。 `--check-urls` を付けると、エンティティの `sources` と `references.yml` の出典に到達できるかも確認する。ネットワークに依存するため既定では行わない。確かめ方は出典の種類で分かれる。

- DOI（`references.yml` の `doi`、および `doi.org` / `www.doi.org` / `dx.doi.org` の URL）は出版社のページへ辿らず、DOI レジストリ（`https://doi.org/api/handles/<doi>`）で登録の有無だけを確かめる。出版社のボット遮断で登録済みの DOI が失敗扱いになるのを避けるためである。レジストリが未登録と答えたものは `DOI unregistered` の ERROR にする。レジストリに届かなかったもの（ネットワーク障害・タイムアウト・429 や 5xx）は登録の有無が分からないため ERROR にせず、`validation.url.doi_registry_unreachable` の WARNING にする。
- `references.yml` のエントリが `doi` と `url` の両方を持つときは `doi` だけを確かめ、`url` には HTTP でアクセスしない。
- それ以外の URL は HTTP で確かめる。HEAD を送り、405・ボット対策の 403・HEAD にだけ返す 404 には GET でもう一度試す。届かなければ `unreachable URL` の ERROR にする。出版社の URL に DOI が含まれていても（`https://link.springer.com/article/10.xxxx/...` など）DOI とはみなさず、この HTTP の確認になる。ボット遮断で失敗する出版社の論文は、`doi` か `doi.org` の URL で登録するとレジストリでの確認に切り替わる。

確認は並列に行い、同じホストへの同時接続は 2 本までに抑える。1 回の実行の中で同じ URL・同じ DOI は 1 回だけ確かめる。ERROR と WARNING の並びは並列化の影響を受けず、エンティティ、`references.yml` の順の走査順になる。

`--for ENTITY` と `--ref ID` は確かめる対象を絞る。どちらも繰り返し指定でき、`--check-urls` と一緒に使う（単独で渡すと `validation.arguments` で exit 2）。検証本体は指定にかかわらず KB 全体に行う。

- `--for ENTITY` は、そのエンティティの `sources` に直接書かれた URL と、`sources` の `ref:` と本文の「（出典: id）」が引く出典を確かめる。出典の集め方は `kb reference show --for` と同じである。相対パスは現在のディレクトリから解決する。
- `--ref ID` は、`references.yml` の指定した出典を確かめる。
- 見つからないエンティティは `entity not found`、見つからない出典 ID は `reference id not found` の ERROR にする。

出典を足した直後は、足したエンティティや出典に絞って確かめる（`kb validate --check-urls --for knowledge/people/example.md`）。KB 全体の確認は定期的な点検で行う。判断の経緯は [考察メモ](notes/url-kakunin-memo.md) にある。

### `kb doctor`

設定、`kb-ontology-core` のインストール状態（無ければ `doctor.ontology.not_installed` の WARNING。Claim を使わない限り不要）と宣言タグとの一致、生成物の同期状態、`validate.extra_checks` のコマンド存在、述語が標準述語の体系に沿っているか（`related-to` でも[標準述語](configuration.md#標準述語)でもなく `broader` も持たない述語を `doctor.predicate.nonstandard` の WARNING で示す）を診断する。導入直後や依存更新後の確認に使う。`severity: warning` の診断だけなら終了コードは 0。生成物の同期状態の確認（`plan_sync`）が壊れたビュー YAML などで失敗した場合も、内部エラーで落ちずに `doctor.sync_failed`（ERROR）として報告する。

### `kb serve`

グラフの閲覧画面をローカルで起動する。`graph.json` を読むので、事前に `kb sync` で同期させておくこと。待ち受けは `127.0.0.1` に限定される。型の色は `vocabulary.yml` の型の定義順に固定のパレットから割り当てる。画面の資産はすべて同梱しており、ネットワークのない環境でも表示できる。`graph.json` / `vocabulary.yml` が壊れているなどリクエスト処理中に例外が起きた場合は、接続を切らず 500 を返す（詳細はサーバの標準エラーに出す）。

| オプション | 内容 |
|---|---|
| `--port PORT` | 待ち受けポート番号。デフォルト `8000` |
| `--open` | ブラウザを自動的に開く（OS サポート時） |

### `kb flashcards`

設定中の KB から学習カードを生成し、ローカルで起動する。`kb-domain.yml` の `content_root` からエンティティ・タグ・関係を読み、概要と Markdown 本文をカードに表示する。タグがない KB でも型ごとに出題できる。ユーザーの回答は保存しない。待ち受けは `127.0.0.1` に限定される。

```bash
kb flashcards
kb flashcards --port 8123 --open
```

出題数は10問が初期値。ジャンルと出題数を開始前に選択できる。UI は英語を既定とし、ブラウザーの優先言語が日本語の場合は日本語で表示する。KB 本文そのものの言語は変換しない。

## 生成物の同期

### `kb index build` / `kb index check`

各型ディレクトリの `index.md` を生成する（`build`）、または同期済みか確認する（`check`）。`build` は `--dry-run` に対応する。`kb-domain.yml` で `index.by_tag: true` のときは、ルート `index.md` の `<!-- tag-index:start -->` 〜 `<!-- tag-index:end -->` 区間にタグ別一覧も生成する（[設定リファレンス](configuration.md#kb-domainyml)）。

### `kb graph build` / `kb graph check`

ルートの `graph.json`（`nodes` / `edges` / `claims`）を生成・同期確認する。`build` は `--dry-run` に対応する。`views.root` が設定されていれば、`kb sync` と同じく解決済みメンバーを持つ `views` 配列も出力する（未設定の KB の `graph.json` は変わらない）。

### `kb sync` / `kb sync --check`

index と graph をまとめて生成・同期確認する。`--dry-run` に対応する。`index.by_tag` が有効ならタグ別一覧の陳腐化も `--check` で検出する。`views.root` が設定されていればビュー一覧（`views.index`）も生成し、陳腐化を `views.stale` として検出する。`concerns.root` が設定されていれば懸念一覧（`concerns.index`）も生成し、陳腐化を `concerns.stale` として検出する。ビュー・懸念の定義の形式不備は内部エラーにせず、`view.*` / `concern.*` の診断として終了コード 1 で返す。

## 移行

### `kb link migrate` / `kb link migrate --check`

`content_root` 配下の Markdown にある旧形式のルート相対リンク（`[名前](/people/example.md)`）を、リンク元ファイルからの相対リンク（`[名前](../people/example.md)`）に書き換える。見出しへのフラグメント（`#見出し`）は保つ。相対リンク・URL・frontmatter の識別子（relations の `target` など）は変えない。`--check` は書き換えの残るファイルを `link.root_relative` として報告し、残りがあれば終了コード 1 を返す。`--dry-run` に対応する。

## 書き込み（原子的）

書き込み系コマンドは spec ファイルから変更を計画し、一時 KB で全体検証を通してから反映する。検証に失敗した場合は何も書き込まない。

### `kb entity create --from entity.yml`

spec からエンティティ本体と index / graph を原子的に作成する。

| オプション | 内容 |
|---|---|
| `--from PATH` | エンティティ spec（[設定リファレンス](configuration.md#エンティティ-spec)） |
| `--timestamp` | frontmatter の `timestamp` を明示する |
| `--dry-run` | 統一 diff のみを返す |

`timestamp` は CLI 引数 → spec → 環境変数 `SOURCE_DATE_EPOCH` → 注入 clock の順で解決する。

### `kb claim create --from claim.yml`

spec から Claim ファイルを作成する。`--dry-run` に対応する。

### `kb claim inspect PATH` / `kb claim list [--status STATUS]` / `kb claim validate PATH`

Claim の照会・一覧・単体検証。

### `kb claim transition PATH --to STATUS`

Claim の `status` を明示的に遷移させる。許容される遷移は `kb-ontology-core` の `plan_transition` が定義する。`--dry-run` に対応する。

### `kb view list` / `kb view resolve VIEW_ID` / `kb view validate`

エンティティ本文の外に置いたビュー（[設定リファレンス](configuration.md#ビュー任意)）の一覧・解決・検証。`list` は各ビューの `kind` / `basis` と解決後のメンバー数を、`resolve` は指定したビュー（ファイル名の stem）のメンバーを `path` / `title` / `note` で返す。`query` ビューの `where.relation.predicate` に親の述語を書くと、`broader` で吊るした子孫の述語のエッジも一致とみなす。`views.root` が未設定なら `view.disabled` で終了コード 2。ビューの作成は YAML を手で書く（雛形生成コマンドは持たない）。

### `kb concern list [--for TARGET] [--status STATUS] [--actionable]` / `kb concern summary` / `kb concern validate`

懸念台帳（[設定リファレンス](configuration.md#懸念台帳任意)）の一覧・集計・検証。`list` は懸念を ID 順に `id` / `status` / `kind` / `targets` / `summary` で返し、条件は AND で絞る。`--for` はエンティティ（`/dir/file.md` か、`content_root` 内のファイルパス）または `ref: <id>` を受け、それを対象に含む懸念だけを返す。`content_root` の外を指すと `concern.arguments` で終了コード 1。`--actionable` は着手できる懸念（`open` / `investigating`）だけを返す。`summary` は状態別・種別の件数と着手可能な件数を返す。`validate` は `kb validate` のうち懸念の検査だけを行う。`concerns.root` が未設定なら `concern.disabled` で終了コード 2。懸念の作成は YAML を手で書く（雛形生成コマンドは持たない）。

### `kb reference health`

`references.yml` の構造を検査する。エントリごとの規則は `kb validate` / `kb reference create` と共通（[設定リファレンス](configuration.md#referencesyml)）。

### `kb reference show ID...` / `kb reference show --for ENTITY`

`references.yml` から指定 ID のエントリだけを取り出す。`--for` にエンティティファイルを渡すと、その `sources` と本文の `（出典: id）` に現れる ID を初出順に集めて書誌ごと返す（`ids` に ID 一覧、`entries` に書誌）。text は各エントリを YAML ブロックで、json は `{ok, entries, missing, diagnostics}` を返す。見つからない ID は `missing` と `reference.id.missing` の診断に載り終了コード 1。エージェントはレジストリ全体を文脈に読み込まず、このコマンドで必要な書誌だけを引く。

### `kb reference search TERM... [--field FIELD] [--url URL] [--doi DOI] [--limit N] [--full]`

`references.yml` を語句で探す。語句は大小無視の部分一致で、複数与えると AND。既定の対象フィールドは `id` / `title` / `author` / `publisher` / `journal` / `url` / `doi` / `note` / `lineage` で、`--field` で絞る（複数指定可）。`--field lineage <ラベル>` で同じ由来の資料群（[設定リファレンス](configuration.md#referencesyml)）を引ける。`--url` / `--doi` は正規化（scheme・`www.`・末尾スラッシュ・fragment、`doi.org/` 接頭辞の除去、小文字化）後の完全一致で、登録前の重複確認に使う。語句・`--url`・`--doi` は組み合わせると全条件の AND。結果はレジストリの記載順。text は 1 件 1 行（`id`・`type`・`title`・`author`・`year`・`url` をタブ区切り）で件数を stderr に出し、`--full` で YAML ブロック表示。json は `{ok, entries, count, shown}`。索引は持たず毎回レジストリを読む。

### `kb reference spec --from search-result.json --output reference.yml`

`ndl_search.py` / `cinii_search.py` の検索結果（JSON / YAML）を登録用 spec に変換する。`--dry-run` / `--force`（出力先の上書き）に対応する。

### `kb reference create --from reference.yml`

spec を `references.yml` に原子的に追加する。既存レジストリのコメント・引用符・順序・空行・改行コードは再シリアライズせず保持し、末尾に新規エントリのみを canonical YAML で追記する。空 mapping（`{}`）の場合は新規エントリ全体に置換する。`--dry-run` に対応する。spec は `kb validate` / `kb reference health` と同じ規則（[設定リファレンス](configuration.md#referencesyml)）で検査するため、ここを通った spec が直後の `kb validate` で弾かれることはない。

## 評価

評価データセットはリポジトリルートの `evals/rag-eval.yml` に固定（トップレベルはエントリの list か `entries` キーを持つ mapping）。無ければ `eval.assets.missing` で exit 1。`id` / `query` / `expected` / `evidence` の必須と `evidence` の実在は `kb validate` が検査する。`kind` の必須、`history` の日付・verdict 形式、`gap` の語彙は `scripts/eval_summary.py` だけが検査する（[設定リファレンス](configuration.md#evalsrag-evalyml任意)）。実装は `kb_harness.evaluation` にあり、`scripts/rag_smoke.py` / `scripts/eval_summary.py` も同じ関数を呼ぶ。

### `kb eval summary`

`evals/rag-eval.yml` の評価履歴を集計し、退行（過去 OK → 最新非 OK）を検出する。json は `summary`（`evaluated` / `total` / `by_verdict` / `by_kind`）・`regressions`・`open_gaps`（最新が非 OK で `gap: by-design` でないもの）を返す。退行があれば `eval.regression` の診断を出して exit 1。

### `kb eval smoke [--limit N]`

各クエリの期待根拠（`evidence`）が字面検索の上位 `--limit` 件（既定 5）に入るかを検査する。回答品質ではなく検索可能性の回帰を検出する。`history` が空のエントリは計画のみとみなして対象外。外れがあれば `eval.smoke.miss` の診断と `failures`（`id` / `evidence` / `retrieved`）を返して exit 1。

## OKF

### `kb export okf --output PATH`

内部プロファイルを strict OKF v0.2 bundle に決定論的に変換する。出力パスは output root 配下に限定され、ref ID は小文字 kebab-case、入力 Markdown の symlink は拒否し（symlink ディレクトリは走査対象外）、任意階層の `log.md` は予約ファイルとして扱う。`--dry-run` に対応する。出力する bundle の中で解決できない本文リンク（`content_root` の外を指すリンクなど）は `okf.link.broken` の警告として `warnings` に入れ、書き出しは止めない。

内部プロファイルから OKF への変換方針（どの型・述語をどう対応付けるか）は導入先 KB が文書化する。

### `kb okf validate PATH [--strict]`

既存の OKF bundle の適合性を検証する。`PATH` が相対パスなら `--start`（省略時はカレントディレクトリ）を起点に解決する。適合性の違反は `diagnostics`、推奨事項の逸脱は `warnings` に入る。本文リンクは相対リンクなら文書の位置から、ルート相対リンクなら bundle ルートから解決し、bundle 内に無いものを `okf.link.broken` の警告にする。`--strict` を付けると警告も失敗扱いにする。

## Python API

`kb_harness` パッケージは CLI と同じ計画・適用 API を公開する。主なモジュール:

| モジュール | 役割 |
|---|---|
| `kb_harness.project` | `kb-domain.yml` の探索と `Project` の解決 |
| `kb_harness.diagnostics` | 安定した `code` / `field` / `context` を持つ構造化診断 |
| `kb_harness.markdown` | frontmatter 付き Markdown の解析・シリアライズ |
| `kb_harness.entity` / `kb_harness.actions.entity` | エンティティ spec の検証と作成計画 |
| `kb_harness.claim` | Claim の作成・照会・遷移 |
| `kb_harness.evaluation` | `evals/rag-eval.yml` の集計・退行検出と字面検索スモーク |
| `kb_harness.references` | `references.yml` の点検・追記・照会（show / search） |
| `kb_harness.index` / `kb_harness.graph` / `kb_harness.sync` | 生成物の計画と適用 |
| `kb_harness.okf` | OKF v0.2 の export と検証 |
| `kb_harness.ontology` | `kb-ontology-core` の `Diagnostic` を構造化診断へ翻訳する。従来の `validate_claim`（文字列リスト）も互換入口として残る |
| `kb_harness.predicates` | 述語の階層（`broader`）と標準対応（`maps_to`）の読み込み・検査・汎化。標準述語の定義もここに置く |
| `kb_harness.doctor` | 環境診断 |
