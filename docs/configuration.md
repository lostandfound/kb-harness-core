# 設定リファレンス

ハーネスは導入先リポジトリの 3 つのファイルを読んで動作する。いずれもドメイン固有の情報はここに書き、ハーネス側にはハードコードしない。

| ファイル | 置き場所 | 読む側 |
|---|---|---|
| `kb-domain.yml` | リポジトリルート | 全スクリプト・スキル・エージェント |
| `vocabulary.yml` | `<content_root>/` | `kb validate` / `kb entity create` / `kb graph build` ほか |
| `references.yml` | `<content_root>/` | `kb validate` / `kb reference *`, `find-book` / `find-paper` スキル |
| `evals/rag-eval.yml` | リポジトリルート（任意） | `kb validate` / `kb eval *`, `rag-tester` |

## kb-domain.yml

```yaml
domain:
  name: 沖縄空手史
  kb_title: 沖縄空手 OKF 知識ベース
  description: 沖縄空手の流派・型・人物・用語・史実を扱う知識ベース
  content_root: okinawa-karate
  lineage_example: 上地流系・劉衛流系など流派・系統単位

# 任意。explore_diff.py がカテゴリ引数省略時に読む
exploration:
  wikipedia_categories:
    - 沖縄空手

# 任意。kb sync / kb index build がルート index.md にタグ別一覧を生成する
index:
  by_tag: true
  tag_labels:
    cooking: 料理
    science: 科学
```

| フィールド | 必須 | 内容 |
|---|---|---|
| `domain.name` | 要 | ドメインの名称。エージェントが「専門家として」振る舞う対象を特定する。 |
| `domain.kb_title` | 要 | KB 自体の呼称。エージェントの説明文中で使う。 |
| `domain.description` | 要 | KB が扱う範囲の一文説明。 |
| `domain.content_root` | 要 | エンティティ Markdown を置くディレクトリ名。scripts の `--root` 既定値はここから解決する。 |
| `domain.lineage_example` | 任意 | 系統・分類の具体例。エージェントのプロンプトが参照する補助情報。 |
| `exploration.wikipedia_categories` | 任意 | `explore_diff.py` が既定で走査する Wikipedia カテゴリ名の一覧。 |
| `index.by_tag` | 任意 | `true` のとき `kb sync` / `kb index build` が `<content_root>/index.md` の `<!-- tag-index:start -->` 〜 `<!-- tag-index:end -->` 区間にタグ別一覧を生成する。区間がなければ末尾に追記し、区間外の本文は保持する。並び順は `vocabulary.yml` の `tags` 順、該当エンティティのないタグは省く。`kb sync --check` が陳腐化を検出する。既定は無効。 |
| `index.tag_labels` | 任意 | タグ ID から見出し表示名への対応。未登録のタグは ID をそのまま見出しにする。 |

上記以外のキーはハーネスは読まない。導入先が独自の設定を同じファイルに置いても支障はない。

## vocabulary.yml

エンティティの型・relations・タグの語彙。`kb validate` の検査ルールはすべてこのファイルに由来する。

```yaml
types:
  <型名>:
    directory: <対応ディレクトリ名>     # 必須。frontmatter の type とディレクトリの対応検査に使う
    extra_fields: [born, died]           # 任意。この型で追加必須になる frontmatter フィールド
    graph: false                         # 任意（既定 true）。false の型は relations を持てない
    sources_required: false              # 任意（既定 true）。false の型は sources を省略できる
predicates:
  <述語名>:
    description: <説明>
    domain: [<型名>, ...]                # この述語の始点になれる型
    range: [<型名>, ...]                  # この述語の終点になれる型
properties:                              # 任意。値 Claim を使う場合のみ
  <プロパティ名>:
    description: <説明>
    domain: [<型名>, ...]
    value_type: <型>                     # 例: year-expression
tags:
  - <タグ1>
  - <タグ2>
```

- `types.<型>.extra_fields` に `born` または `died` を含めると、値は「西暦4桁（`?` 付き可）」「西暦4桁+頃」「不詳」のいずれかの形式に限定される。それ以外のフィールド名は非空文字列であることのみ検査する。
- `types.<型>.graph: false` を指定した型のエンティティは `relations` を持てない。索引・付録的なエンティティ型に使う。
- `predicates.<述語>.domain` / `range` は、frontmatter の `relations` に書かれた `predicate` と `target` エンティティの型が一致するかを検査する型制約である。
- `tags` は frontmatter の `tags` に使える語の全量である。一覧にない語は validate エラーになる。

## references.yml

文献レジストリ。エンティティの `sources` と本文インラインの `（出典: ref-id）` は、ここに定義された ID を参照する。

各エントリは任意キー `pending`（非空文字列の待ち理由）を持てる。付与すると未参照 WARNING が個別に出ず件数集計の INFO 1 行にまとまり、参照済みなのに `pending` が残っていると WARNING で警告される。

登録用 YAML は `ndl_search.py` / `cinii_search.py` が出力する。

## エンティティ spec

`kb entity create --from entity.yml` の入力。

```yaml
type: Person
slug: example-person
title: 例の人物
description: 一文の説明
tags: [history]
sources: [ref-id]
sections:                       # 見出し → 非空本文
  概要: 本文
  経歴: 本文
aliases: []                     # 任意
relations:                      # 任意
  - predicate: taught
    target: /people/other.md
fields:                         # 任意。型の extra_fields に対応
  born: "1900"
timestamp: 2026-01-01T00:00:00Z # 任意。省略時は SOURCE_DATE_EPOCH → clock
```

`type` / `slug` / `title` / `description` / `tags` / `sections` が必須。`sources` は型の `sources_required` が `false` でない限り必須。型ごとの章構成と `extra_fields` は `vocabulary.yml` を正本とする。

## Claim 型（任意）

`Claim` という型を `vocabulary.yml` に定義すると、確定した relation と区別して、出典と評価を伴う関係主張を記録できる。

Claim のドメイン検証とグラフ用シリアライズは [`kb-ontology-core`](https://github.com/lostandfound/kb-ontology-core) が正本である。ハーネスは `kb_harness.ontology` を介してそれを呼ぶだけで、ルール自体は持たない。

```yaml
types:
  Claim:
    directory: claims
    graph: false
    extra_fields: [subject, status, confidence]
```

Claim frontmatter の契約:

| フィールド | 内容 |
|---|---|
| `subject` | 存在するエンティティへのルート相対パス |
| `status` | `proposed` / `accepted` / `disputed` / `rejected` |
| `confidence` | `A` / `B` / `C` / `D` |
| `sources` | 1 件以上。通常エンティティと同じ出典検証を適用する |
| `predicate` + `object` | 関係 Claim。`predicate` は `vocabulary.yml` の述語で、domain/range 制約を適用する。`object` はエンティティのルート相対パス |
| `property` + `value` | 値 Claim。`property` は `vocabulary.yml` の `properties` に定義済みで、`value` は `value_type` で検証する |

- 関係形式と値形式はどちらか一方を完全に指定する。混在は禁止。
- 通常 relation と同じ subject / predicate / object の三つ組を重複登録するとエラーになる。
- `status` の遷移は `kb claim transition` で明示的に行う。
- `kb graph build` は Claim を `nodes` / `edges` に混ぜず、独立した `claims` 配列へ出力する。
- 期間付き主張は現時点の共通契約に含まれない。

## evals/rag-eval.yml（任意）

RAG 評価データセット。リポジトリルート直下の `evals/` に置く。ファイルが無ければ関連する検査はスキップされる。

```yaml
- id: q-001
  query: 想定クエリ
  expected: 期待する回答の要旨
  evidence:
    - /people/example.md          # 根拠となるエンティティのルート相対パス
  history:                        # rag-tester が追記する
    - date: 2026-01-01
      verdict: OK
```

- `id` / `query` / `expected` / `evidence` は必須。`evidence` の各パスは実在するエンティティでなければならない（`kb validate` が検査）。
- `kb eval smoke` は `query` に対する字面検索の上位 `--limit` 件に `evidence` が入るかを検査する。
- `kb eval summary` は `history` を集計し、過去 OK → 最新非 OK の退行を検出する。
