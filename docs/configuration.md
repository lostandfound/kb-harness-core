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

# 任意。kb validate が本体の検証後にリポジトリルートで順に実行する導入先固有チェック
validate:
  extra_checks:
    - python3 tools/check_something.py --check
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
| `views.root` | 任意 | ビュー定義 YAML を置くディレクトリ（`repo_root` 相対）。指定するとビュー機能が有効になり、`kb validate` が定義を検査し、`kb sync` / `kb graph build` がビュー一覧と `graph.json` の `views` 配列を生成する。リポジトリの内側かつ `content_root` の外でなければならず、外れる設定は読み込み時にエラーになる。契約は[ビュー](#ビュー任意)を参照。既定は無効。 |
| `views.index` | 任意 | `kb sync` が生成するビュー一覧の出力先（`repo_root` 相対、`.md`）。既定は `<views.root>/index.md`。リポジトリの内側かつ `content_root` の外で、`graph.json` / `kb-domain.yml` / `views.root` 自身と衝突してはならない。 |
| `validate.extra_checks` | 任意 | シェルコマンド文字列の一覧。`kb validate` が本体の検証後にリポジトリルートを作業ディレクトリとして順に実行し、非ゼロ終了を `validation.extra_check.failed`（ERROR）として集約する。`--format json` では `extra_checks` にコマンドごとの `returncode` / `ok` / `stderr` が出る。`kb doctor` は先頭語が PATH 上に見つからないコマンドを `doctor.extra_check.unavailable`（WARNING）として報告する。YAML で `true` などは真偽値になるので引用符で囲む。 |

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

`predicates.<述語>` の `domain` / `range` は省略できる。省略した側は無制約になる。ハーネスが読む述語のキーは `description` / `domain` / `range` と、下記の `broader` / `maps_to` である。

### 標準述語

ハーネスはドメイン語彙を持たないが、述語の**名前・向き・意味**については次の 5 つを標準として定める。導入先は使う族だけを `vocabulary.yml` に写し、自分の型で `domain` / `range` を束縛する。型への束縛は導入先が決め、ハーネスは決めない。

| 述語 | 族 | 向き | 主な対応標準 |
|---|---|---|---|
| `part-of` | 部分・所属・分類 | 部分 → 全体 | `dcterms:isPartOf`、Wikidata P361 |
| `derived-from` | 起源・派生・系譜 | 派生物 → 起源 | `prov:wasDerivedFrom`、Wikidata P144 |
| `created-by` | 主体・行為 | 対象 → 主体 | `prov:wasAttributedTo`、`dcterms:creator` |
| `located-in` | 空間 | 対象 → 場所 | `schema:containedInPlace`、Wikidata P276 |
| `follows` | 順序・継起 | 後続 → 先行 | OBO RO `preceded_by`、Wikidata P155、EDM `isNextInSequence` |

- 向きは全述語で「**依存する側から、依存される側へ**」に統一する。逆向きの述語（`has-part` など）は定義しない。
- `related-to` は標準述語の上に置く**未分類**の印であり、方向も意味も持たず、階層に属さない（`broader` を書けず、親にもなれない）。`domain` / `range` は書いてもよく、書けば他の述語と同じく型制約として検査するが、それはグラフに載せてよい型の粗い制限であって、層 1 の資格（方向と意味）ではない。関係の意味は本文の関連項目に一文で書く。`related-to` のエッジは、意味が定まった時点で標準述語か導入先の述語へ精緻化する候補である。
- 時間の族（`during` など）は標準に含めない。時期はフィールド（`born` / `died` など）か Claim で表す。時代がエンティティになる導入先は自前の述語として足してよい。順序（`follows`）は時間ではなく二者の前後を言う関係であり、フィールドでは分岐・並行・合流を表せないため標準に含める。
- 分類（kind-of）と部分（part-of）は標準では分けない。区別が問い合わせに効く導入先だけが、`part-of` の下に `kind-of` などを足す。
- 標準述語より細かい述語（`borrowed-from` / `student-of` / `child-of` / `succeeds` など）は導入先が任意で足す。追加の目安は「検証器に弾かせたい型制約があるか」「その述語で絞る問い合わせが実際にあるか」のいずれかを満たすこと。relation の詳細度は出典なしで断言できる深さまでとし、それより細かい主張は Claim にする。

#### 族の選び方（運用規約）

- **複数の族に読める関係は、より多くを含意する族に置く。** 親子は「後先」も含意するが本体は「起源」なので `derived-from` の下（`child-of`）に置き、`follows` には置かない。時間順序は `born` / `died` のフィールドから出る。
- **所属と順序、血縁と継承は別のエッジで書く。** 工程のステップは工程へ `part-of`、前のステップへ `follows`。家督を継いだ子は父へ `child-of` と `succeeds`（`follows` の層 2）。一本にまとめない。
- **対称な関係（兄弟・婚姻・同盟など）はエッジにしない。** 向きの規則が適用できず、逆向き検査とも衝突する。兄弟は共有する親への `child-of` から導く。親が不明なら名前のない親エンティティを立てる。婚姻は「家」のようなハブ Concept への `part-of` で受けるか、`related-to` と本文の一文に留める。
- **順序をフィールドで持たない。** 整数の順序は分岐・並行・合流を表せず、挿入で全件を書き換える。順序で問い合わせたいステップは `follows` で書く。工程に固有で説明の短いステップはエンティティにせず、工程の本文に番号付きで書く。
- **同じ情報を述語に焼き込まない。** 父・母を別の述語にせず `child-of` 一つにし、親の性別は親エンティティの属性に置く。
- **不確かなら Claim。** 争いのある親子・順序は relation ではなく、同じ述語（`child-of` / `follows`）を持つ Claim として確度付きで置く。

背景は [docs/notes/jutsugo-kaisou-memo.md](notes/jutsugo-kaisou-memo.md) にある。

### 述語の階層と標準対応

述語は詳細度で三層に分けて扱う。`related-to` は未分類の印（層 0）、`broader` を持たない述語が層 1、`broader` で親に吊るした述語が層 2 である。層 1 は標準述語を写して使い、層 2 は導入先が任意で足す。

```yaml
predicates:
  related-to:
    description: 何らかの関係がある。意味は本文の関連項目に書く
    maps_to: [dcterms:relation, skos:related]
  derived-from:
    description: 起源・派生元。派生物から起源へ向ける
    maps_to: [prov:wasDerivedFrom, dcterms:source, wdt:P144]
    domain: [Concept, Script]
    range: [Concept, Script]
  borrowed-from:
    description: 表記体系を借用した。改良・継承とは区別する
    broader: derived-from
    domain: [Script]
    range: [Script]
```

| キー | 内容 |
|---|---|
| `broader` | 親述語の名前。1 つだけ。`related-to` は未分類の印であって述語の親にはならないので指定できない。階層は単一の木に限り、確度や期間など別の軸で述語を派生させない（それらは Claim の領分） |
| `maps_to` | 対応する標準語彙の CURIE または IRI の一覧。空でない文字列のリストであることだけを検査し、解決はしない |

`kb validate` は次を検査する。

- ERROR: `domain` / `range` が型名のリストでない（スカラーは 1 要素として扱った上で違反として報告する）。`related-to` 自身に `broader` がある、`broader` の先が存在しない、自身か `related-to` を指す、循環する（循環は循環上の述語だけを 1 件で報告し、循環に至るだけの述語は責めない）。子の `domain` / `range` が直接の親の部分集合でない（親が無制約の側は任意。親に制約があり子が無制約なら違反）。`maps_to` が空でない文字列のリストでない。
- WARNING: `related-to` のエッジのうち、始点と終点の型がともに、`domain` と `range` の両方を持つ層 1 の述語のちょうど 1 つに収まるもの。精緻化の候補を示す。
- INFO: `related-to` のエッジの件数。分類の負債量として報告する。

`kb doctor` は `related-to` でも標準述語でもなく `broader` も持たない述語を `doctor.predicate.nonstandard`（WARNING）で示す。導入先が独自に層 1 を増やした状態の可視化であり、止めはしない。

`query` ビューの `where.relation.predicate` に親を書くと、子孫の述語で書かれたエッジも一致とみなす（汎化）。書かれたエッジ 1 本を祖先の列に写すだけで新しい事実は生まない。推移閉包（`part-of` の多段）はこの機構では導かない。

`kb graph build` は、語彙のいずれかの述語が `broader` か `maps_to` を持つときだけ、`graph.json` に `predicates` オブジェクト（述語名 → `broader` / `maps_to`）を出す。汎化は消費側で行うため、階層をここで渡す。どちらも書かない語彙では `graph.json` は従来どおり `nodes` / `edges` / `claims`（と有効時の `views`）のみで変わらない。エッジの `predicate` は書かれた葉の述語のままである。

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

`description` は有無だけでなく内容も検査する。空文字はエラー、同じ文が二度出るものもエラーとする（改版で前の版の断片が残ると、形式は正しいまま検索結果と index に重複が出続けるため）。`title` と同一のもの、240 文字を超えるものは警告にとどめる。

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

## ビュー（任意）

ビューは、エンティティ本文に書かずに束ねや導出を定義する層である。`kb-domain.yml` の `views.root` で有効化し、そのディレクトリに 1 件 1 YAML で置く。ファイル名の stem がビュー ID になる（ケバブケース）。

出典で支えられた事実はエンティティに、書き手の見方による束ねはビューに置く、という分離を機械的に保つためのもので、ハーネスはビューの内容をエンティティ Markdown へ書き戻さない。RAG などの消費者には `kb sync` が生成するビュー一覧（`views.index`）と `graph.json` の `views` 配列を通して露出する。

```yaml
# list: 割り当てビュー。メンバーを列挙する
name: 一度定義して各所で使う
description: 定義を一か所に置き、利用側はそれを参照するだけにする姿勢を共有するもの。
kind: list
basis: interpretation
members:
  - /concepts/dont-repeat-yourself.md
  - path: /concepts/semantic-layer.md
    note: 指標を一度定義し、各ツールから参照させる
```

```yaml
# query: 導出ビュー。where の AND 条件でメンバーを計算する。新しい情報を持たない
name: 客家料理の料理
description: 客家料理に属する料理。
kind: query
where:
  type: Dish
  relation: { predicate: part-of, target: /concepts/hakka-ryori.md }
```

| フィールド | 内容 |
|---|---|
| `name` / `description` | 必須。`name` は全ビューで一意 |
| `kind` | `list`（割り当て）または `query`（導出） |
| `basis` | `list` で必須。`interpretation`（書き手の見方。`sources` を持てない）または `source`（出典に基づく。`sources` 必須） |
| `members` | `list` で必須。ルート相対パスの文字列、または `{path, note}`。Claim は指定できない |
| `sources` | `basis: source` のときのみ。`ref: <id>` は `references.yml` に存在すること |
| `where` | `query` で必須。`type` / `tags`（すべて含む）/ `relation: {predicate, target}` の AND 条件。語彙と実在エンティティに照らして検証する |

- `list` に `where`、`query` に `members` / `basis` / `sources` を書くとエラー。上記以外のキーもエラー。同じ stem を `.yml` と `.yaml` の両方で置く（ID の重複）のもエラー。
- `basis: source` を書きたくなったビューは、Claim かエンティティへ昇格する候補である。ビューは出典を持たないのが原則で、`source` は昇格前の一時的な状態として許す。
- `kb graph build` はビューを `nodes` / `edges` に混ぜず、独立した `views` 配列へ出力する（`id` / `name` / `description` / `kind` / `basis` / `where` / 解決済み `members`）。

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
