# 考察メモ: 基本エンティティのフィールドをプリセット化するか

2026-09-26 のディスカッションの記録。[述語を詳細度で層に分ける](jutsugo-kaisou-memo.md)の続き。問いは「omnibus-kb の Person は schema.org を参考にプロパティを決めた。基本エンティティ（Person / Organization / Place / Event / Work / Concept）のプロパティをハーネス側でプリセット化するのはどうか」。

結論は「**名前と写し方の合意は文書で置く。型の検査は消費者が現れてから**」。契約は[設定リファレンス](../configuration.md#フィールドの写し方と推奨名)が正本で、このメモは判断の経緯を残す。

## omnibus-kb の実物

`knowledge/vocabulary.yml` は Person に `extra_fields: [jobTitle, worksFor]`、Work に `[year]`、Event に `[date]` を持つ。値を並べると次のとおり。

| 型 | フィールド | 実際の値 | 診断 |
|---|---|---|---|
| Person | `jobTitle` | 計算機科学者 / CEO / 教授 / 漫画家 / 起業家・投資家 / データウェアハウス・コンサルタント、著述家 | 分類的属性。値が統制されず複合値も混ざる。比較・絞り込みに使えない |
| Person | `worksFor` | Viewpoints Research Institute（創設者、2001〜2018年）/ Anthropic / なし（専業漫画家）/ Kimball Group（2015年に活動終了） | schema.org では range が Organization（Thing）。文字列に押し込んだ結果、役職・期間・否定が括弧書きで溜まっている |
| Person | （なし） | | `born` / `died` が無い |
| Work | `year` | '2021' … '1996'、殷代後期、4世紀中頃 | 時間の端点だが、年表現に収まらない値がある |
| Event | `date` | 1594-1654 | 期間を 1 フィールドに入れている |

`worksFor` の壊れ方が最も示唆的である。range が Thing のプロパティを文字列フィールドにすると、関係の属性（役割・期間）を書く場所がないので全部括弧に入る。これは述語（`part-of` の下の `member-of`）か本文の領分であり、フィールドではない。

## schema.org からの写し方

schema.org の Person は 60 を超えるプロパティを持つが、写す先は一つではない。規則は三つで足りる。

- **range が Thing（別のモノ）のプロパティは述語に写す。** `worksFor` / `memberOf` → `part-of` の層 2、`birthPlace` → `located-in` の層 2、`parent` → `derived-from` の層 2、`author` → `created-by`。組織や場所をノードにするほど重要でなければ本文に書く。
- **range が DataType で、並べる・絞る・突合するのに使う値だけがフィールド。** 時間の端点（生没・設立・開始終了・成立刊行）と外部識別子。
- **分類的属性（`jobTitle` / `gender` / `nationality` など）はタグか本文。** フィールドにすると統制語彙の外に値が散る。その軸で絞る問い合わせが実際に来たときだけタグの軸にする。

`name` / `alternateName` / `description` は `title` / `aliases` / `description` として既にあり、共通フィールドは schema.org とほぼ対応済みである。

## 最初の提案と、それが過剰だった理由

最初は次を提案した。

1. `extra_fields` を `{名前: value_type}` で書けるようにし、フィールドにも `maps_to` を持たせる
2. `year-expression` を広げ（紀元前・3 桁・`不詳`）、`iri` 型を足す。正本は `kb-ontology-core` なのでコアの版を上げる
3. ハーネスの `PERSON_DATE_RE` を廃止してコアに委譲する
4. 標準フィールド（`same_as`、`born` / `died`、`founded` / `dissolved`、`start` / `end`、`created` / `published`）と基本型の雛形

観察された問題と機構を照合すると、`worksFor` と `jobTitle` は規則 1 行で解け、名前のばらつきは推奨表で解ける。「殷代後期」は並べる機能が無いので何も壊していない。紀元前・3 桁の年が書けないのは本物の欠陥だが、今どの KB も踏んでいない。外部識別子は突合・重複検出の機能が無いので使い手がいない。

述語の階層をハーネスの機構として実装したときは**消費者がいた**。domain / range の検証器が層 2 を弾き、`query` ビューが親で問うて子孫を拾う。フィールドの型にはその消費者がいない。`query` ビューの `where` は type / tags / relation だけでフィールドを見ず、`kb serve` に時系列はなく、`same_as` で突合する機能もない。「比較可能性のために型を付ける」と言いながら比較する側が存在しないのは、それ自体が「世界の構造を先に設計する」ことになる。しかもコストは二つのリポジトリにまたがり、述語の階層より重い変更をより弱い動機で行うことになる。

## 判断

- **今やる**: 写し方の規則と推奨するフィールド名の表を[設定リファレンス](../configuration.md#フィールドの写し方と推奨名)に置く。検査はしない。名前の統一は、複数の KB を同じスキルで書くエージェントには効くが、検証器が要るほどの効き方ではない。
- **見送る**: `extra_fields` の型宣言、`iri` 型、`same_as` の検査。再開条件は、フィールド値を読む消費者がハーネスに入るとき（`where` にフィールド条件が要る、`kb serve` に時系列が要る、`same_as` で重複検出をしたい、のいずれかが RAG 評価や運用で実際に出たとき）。
- **見送る**: 年表現の拡張とハーネス側の正規表現の廃止。コアを別の理由で触るときに同梱する。

プリセットの価値は「名前と写し方の合意」にあり、「型の検査」にはまだない。述語で「層 1 は事前に用意し、層 2 は反復が見えてから」と決めたのと同じ判断基準である。

## omnibus-kb 側の整理（参考。導入先の判断）

- `jobTitle` → 落として `description` か本文の一文へ（既に `description` に職業が書かれているものが多い）
- `worksFor` → 落とす。組織をノードにするほど重要なら Organization 型を足して `member-of`、そうでなければ本文「経歴」へ
- `year` → `published`、`date` → `start` / `end`。「殷代後期」「4世紀中頃」はそのまま置いてよい。並べる機能が来たときに年表現へ直す
- `born` / `died` を Person に足す

## 未決事項

- **年表現の定義がハーネスとコアで食い違っている。** ハーネスの `PERSON_DATE_RE`（`born` / `died`）は `1560` `1560?` `1560頃` `不詳` を受け、コアの `YEAR_EXPRESSION_RE`（値 Claim）は `1560` `1560?` `1560頃` `1560年代` を受ける。どちらも紀元前と 3 桁以下の年を受けない。分野を限定しない KB では紀元前が書けないのは欠陥で、コアに一本化して広げるのが筋。コアを次に触るときに同梱する。
- 外部識別子（`same_as`）を突合に使う機能を持つか。NDL 典拠・Wikidata・VIAF の IRI を並べる一つのフィールドにすれば、典拠ごとにフィールドを増やさずに済む。
- フィールド条件を `query` ビューの `where` に足すか。足すなら、そのときが型宣言の導入時点になる。

## 参照

- schema.org Person / Organization / Event / CreativeWork https://schema.org/Person
- omnibus-kb `knowledge/vocabulary.yml`（2026-09-26 時点）
