# 考察メモ: 述語を詳細度で層に分ける

2026-09-26 のディスカッションの記録。[軽量オントロジーの考察メモ](keiryo-ontology-memo.md)と[関係をあとから見出すアプローチ](kankei-hakken-memo.md)の続き。前の 2 本が「述語は増やさない」と結論した上で、それでも述語を用意するならどう用意するかを扱う。

「ハーネスへの落とし方」の草案は同日に実装し、契約は[設定リファレンス](../configuration.md#述語の階層と標準対応)が正本である。問いは「述語をあらかじめ用意しておくべきか。`related-to` を詳細度ゼロとして、詳細度を上げると別の述語になるのではないか」。

## 詳細度の階層は均質ではない

`related-to` から下へ降りる道を眺めると、段差の大きさが違う。

| 層 | 例 | 降りるときに増えるもの | 検証器に効くか |
|---|---|---|---|
| 0 | `related-to` | なし。方向も意味もない（domain / range を書けば型の粗い制限としては効く） | 意味には効かない |
| 1 | `part-of` / `derived-from` / `created-by` | 方向と domain / range | 効く |
| 2 | `derived-from` の下の借用 / 改良 / 継承 | 意味の区別のみ。型制約は親と同じか狭くなるだけ | ほぼ効かない |

0 → 1 が最大の段差である。方向を決め、型を決めるので、あとから遡って直すのが高くつく。1 → 2 は意味の精緻化だけで、親述語の上で名前を付け替えるだけである。「述語を増やす」と一括りにしていたものは、実際には性質の違う二つの操作である。

これは前のメモの「述語は 10 前後まで」という上限にも効く。覚えられなくなるのは層 1 の数であり、層 2 は親を知っていれば必要になったときに降りればよい。Kimball で言えば層 1 が適合次元、層 2 が次元の属性である。

## 用意する層と、用意しない層

**層 1 は事前に用意する。** これが「比較可能性」を決める軸だからである。方向と型を持つ述語がなければ、あとで並べて見比べることができない。しかも層 1 はドメインをまたいでよく似ており、部分・派生・主体・場所のいずれかに大半の関係が落ちる。

**層 2 は事前に用意しない。** 用意した瞬間に書き手は「借用か改良か継承か」の選択を迫られ、判断できないときに間違った精度で書く。層 2 は反復が見えてから、親の下に吊るす形で導入先 KB が任意に足す。前のメモの「検証器に弾かせたいか、方向を辿る検索が要るか」という判定はここに残す。

**層 0 は述語ではなく未分類として扱う。** `related-to` は関係の一種ではなく、まだ層 1 に降りていない状態を表す印である。そう捉えると `related-to` の件数は語彙の欠陥ではなく分類の負債量になり、検証器が数を報告する対象になる。

## 層 1 の中身

層 1 は関係の族ごとに 1 つ、という原則で選ぶ。

| 族 | 述語 | 向き | 層 2 の例（KB が任意で足す） |
|---|---|---|---|
| 部分・所属・分類 | `part-of` | 部分 → 全体 | `member-of` `kind-of` `component-of` |
| 起源・派生・系譜 | `derived-from` | 派生物 → 起源 | `borrowed-from` `improved-from` `student-of` `successor-of` |
| 主体・行為 | `created-by` | 対象 → 主体 | `written-by` `founded-by` `performed-by` |
| 空間 | `located-in` | 対象 → 場所 | `born-in` `held-at` |
| 順序・継起 | `follows` | 後続 → 先行 | `succeeds` `replaces` |

その上に層 0 の `related-to` が乗る。

**向きは全族で一つの規則に揃える。「依存する側から、依存される側へ」。** 部分は全体に、派生物は起源に、作品は作者に、出来事は場所に、後続は先行に向かう。書き手が覚える規則が 1 つで済み、逆向きを二重に書く事故も減る。

### 分類と部分を層 1 で分けない

omnibus-kb の「客家料理 part-of 中国料理」は本来 kind-of に近いが、軽量路線ではまず一緒に扱い、区別が問い合わせに効く KB だけが層 2 で `kind-of` を吊るす。失敗したときの被害が最も小さい置き方である。SKOS と DCMI Terms は分けず、ISO 25964 は `BT` を一つ持った上で `BTG`（類）/ `BTP`（部分）/ `BTI`（実例）に細分する。Wikidata（P31 / P279 / P361）や OBO Relation Ontology は最初から分けており、規模が大きくなると分けたくなる、という予告として受け取る。

### 時間を層 1 に入れない

当初は「時間」の族として `during`（対象 → 時期）を候補にしていたが、外した。時期は多くの KB で `born` / `died` のようなフィールドで表され、時代がエンティティになる KB でしか関係にならない。標準を見ても、Wikidata は開始・終了（P580 / P582）を文の修飾子に置き、DCMI Terms の `temporal` は被覆範囲であってエンティティへの参照ではない。時期はフィールドか、期間付き Claim の領分である。時代がエンティティになる KB は、自前の層 2 相当として `during` のような述語を足せばよい。

### 順序の族は入れる

時間を外したときに前後関係も一緒に落としていたが、これは見落としだった。`during` は「対象 → 時期」でエンティティと時期の関係、前後関係は「ステップ → ステップ」の対等な二項関係で、性質が違う。時間を関係として持たない Wikidata でさえ P155 / P156（follows / followed by）は持っており、OBO RO の `preceded_by`、EDM の `isNextInSequence`、CIDOC-CRM の P120 も同じ族である。時間は修飾子で済むが順序は関係でなければ書けない、という判断が標準に共通している。

工程のステップがエンティティになる場合（ステップ自体に出典と説明があり、順序で問い合わせたい）を考えると、候補は順序フィールド（`part-of` 工程 + `order: 3`）、順序付きの `list` ビュー、述語 `follows` の三つである。決め手は分岐と合流で、工程は「麹づくり」と「大豆の蒸煮」が並行して「混合」に合流するような DAG になる。整数のフィールドはこれを書けず、ビューは書き手の見方の層なので出典で支えられた工程の順序の置き場所ではない。`follows` なら「混合 follows 麹づくり」「混合 follows 蒸煮」と 2 本張るだけである。向きは後続 → 先行で、後続は先行が済んでいることに依存するので規則に合う。`precedes` は定義しない。

所属（`part-of`）と順序（`follows`）は別のエッジである。Kimball で言えば所属が次元で、順序は次元内の並びに当たる。ステップが工程に固有で説明も短いなら（レシピの手順など）そもそもエンティティにせず本文の番号付きリストに置き、複数の工程で再利用される技法は Concept として本文から順に参照する。`follows` が要るのは、ステップ自体に出典と説明があって順序で問い合わせたい場合だけである。

「X より後のステップを全部」は `follows` の多段であり、推移閉包を導かない方針はここでも変えない。ただしこの需要は `part-of` の多段より早く来るので、`query` ビューの深さ指定の議論が戻ってくる。

### 血縁: 含意の強い族に置き、対称な関係は書かない

親子は `follows` の派生でも書けそうに見える。子は親より時間的に後だからである。しかし含意の向きが問題で、親子ならば後先である（derived-from ⇒ follows）が、後先だからといって親子ではない（兄弟の生まれ順、役職の前後任も後先）。**複数の族に読める関係は、より多くを含意する族に置く。** 親子は `derived-from` の層 2（`child-of`、子 → 親）であり、時間順序は `born` / `died` のフィールドから出るので失われない。空手史なら父が師でもある人物に `child-of` と `student-of` を 2 本張り、`derived-from` で問えば血縁・師弟を区別せず系統として拾える。

- 父・母を述語で分けない。親側の性別は親エンティティの属性で持つ。述語に焼き込むと同じ情報を二か所で持つ。
- 養子は `child-of` の下の層 3（`adopted-child-of`）。家督や称号の継承は別の族で、`follows` の層 2（`succeeds`）。同じ父子に `child-of` と `succeeds` が 2 本張られるのは、ステップに `part-of` と `follows` を張るのと同じである。
- 争いのある親子は relation にせず、`child-of` を述語にした Claim にする。歴史 KB では親子こそ最も Claim になりやすい。

兄弟は対称である。「依存する側から依存される側へ」の規則が適用できず、既存の検査は同じ述語の A→B と B→A を逆向きエッジとして弾く。対称な関係はこのモデルの外にある。兄弟はエッジにせず、同じ親への `child-of` を共有していることから導く。書かれた 2 本のエッジの結合であって新しい事実を生む推論ではないので、汎化と同じく許してよい。親が不明で兄弟関係だけが史料にある場合は、系譜学が「不詳の父」を立てるのと同じく名前のない親エンティティを立てる。重すぎるなら `related-to` と本文の一文で層 0 に留める。

婚姻も対称で、期間を持ち、起源でも順序でもない。CIDOC-CRM は事象に、GEDCOM X は Couple という関係オブジェクトにする。このハーネスに期間付きの二項関係を書く場所はない（Claim も期間を持たない）。日本史の KB なら「家」をハブ Concept として立て、両者を `part-of` で繋ぐのが自然である。婚姻による家どうしの結びつきが問いの対象なら、家がノードになっているべきである。個人間の婚姻だけなら `related-to` と本文で層 0。

| 関係 | 性質 | 容器 |
|---|---|---|
| 親子・養子 | 有向・生成的 | `child-of`（`derived-from` の層 2）、養子は層 3 |
| 家督・称号の継承 | 有向・順序 | `succeeds`（`follows` の層 2） |
| 兄弟 | 対称 | 書かない。共有する親から導く。親不明ならノード化 |
| 婚姻 | 対称・期間付き | 「家」のハブに `part-of`、または層 0 |
| 争いのある親子 | 不確か | `child-of` を述語にした Claim |

### 既存 KB との齟齬

現在の沖縄空手 KB が使う `taught`（師 → 弟子）は向きの規則に反する。層 1 に揃えるなら `student-of`（弟子 → 師）を `derived-from` の下に置く形になり、既存 KB 側で述語の向きを反転する移行が要る。ここは運用しているオーナーの判断であり、ハーネスは強制しない。

## 既存の標準からの援用

層 1 の 5 族は、独立に設計された語彙が同じところに収束している。層 1 が安定している証拠として使える。

| 族 | ハーネス | DCMI Terms | schema.org | PROV-O | Wikidata | OBO RO / CIDOC-CRM |
|---|---|---|---|---|---|---|
| 未分類 | `related-to` | `relation` | (なし) | (なし) | (なし) | `skos:related`、`edm:isRelatedTo` |
| 部分・所属 | `part-of` | `isPartOf` | `isPartOf` | `hadMember` の逆 | P361 part of | RO `part_of`、CRM P46i forms part of |
| 派生・系譜 | `derived-from` | `source` | `isBasedOn` | `wasDerivedFrom` | P144 based on、P737 influenced by | RO `derives_from`、CRM P130 shows features of |
| 主体 | `created-by` | `creator` | `creator` | `wasAttributedTo` | P170 creator | CRM P14 carried out by（事象経由） |
| 空間 | `located-in` | `spatial` | `containedInPlace` | (なし) | P276 location、P131 | RO `located_in`、CRM P53 |
| 順序・継起 | `follows` | (なし) | `previousItem` | `wasInformedBy`（活動間） | P155 follows、P1365 replaces | RO `preceded_by`、CRM P120i occurs after、`edm:isNextInSequence` |

標準から読み取れること。

- **向きの規則は標準と一致する。** `isPartOf`、`wasDerivedFrom`、`wasAttributedTo`、`containedInPlace` はいずれも「依存する側から依存される側へ」である。標準は逆向き（`hasPart` など）も定義するが、Wikidata が P361 と P527 の同期に恒常的に苦労しているのは、逆向きを書かない判断の実証になる。
- **層 2 を親の下に吊るす構造に先例がある。** PROV-O は `wasRevisionOf` / `wasQuotedFrom` / `hadPrimarySource` を `wasDerivedFrom` の `rdfs:subPropertyOf` として定義している。機構としての `broader` は `rdfs:subPropertyOf` そのものである。
- **推移律を既定で持たない判断に先例がある。** SKOS は `broader` を推移的と宣言せず、推移閉包が欲しい消費者のために `broaderTransitive` を別に置く。書かれたエッジと導出されたエッジを語彙レベルで分ける切り方である。
- **CIDOC-CRM は反面教師になる。** `created-by` を「作品 → 制作事象 → 行為者」と事象経由で表すのが CRM の作法で、表現力は上がるが、このハーネスが避けた重さである。Wikidata が直接プロパティに修飾子を付けて済ませているのが軽量側の解で、ハーネスの relation + Claim の分担はそちらに近い。

### 名前は借りず、対応を書く

名前をそのまま借りるのではなく、ハーネス名を維持し、標準 IRI への対応を語彙に書ける形にする。名前を借りない理由は 3 つある。

- DCMI Terms の `source` は frontmatter の `sources`（出典）と衝突し、書き手を確実に混乱させる。
- `wasDerivedFrom` のようなキャメルケースは、ケバブケースの slug と並ぶ frontmatter で異物になる。
- 一つの標準で全族を過不足なく覆うものがなく、名前を借りると必ず混成になる。

対応表を持つ利点は将来の出口にある。`kb export okf` や `graph.json` が IRI を併記できれば、RDF への変換や他 KB との突合が翻訳表を別に持たずに済む。NDL の Web NDL Authorities が SKOS と DCMI Terms で公開されていることを考えると、文献側との接続にも効く。

## 汎化は許し、推移は拒む

親の述語で問い合わせたときに子孫のエッジも返す（汎化）ことは、前のメモで捨てた推論を部分的に戻すことになる。しかし線は引ける。上位への汎化は、書かれたエッジ 1 本が固定長の祖先の列に写るだけで、新しい事実を生まない。推移律は書かれていないエッジを無限に導きうる。前者は許し、後者は既定で拒む。

## 詳細度と確度を連動させる

階層があると自然に置ける規約がある。**relation の詳細度は、出典なしで断言できる深さまで。それより細かい主張は Claim にする。** 「ソグド文字から派生した」は relation として `derived-from` で書けるが、「借用であって改良ではない」と言い切れないなら relation は層 1 に留め、`borrowed-from` は Claim として確度付きで置く。relation と Claim の線引きが書き手の裁量任せだった問題に、詳細度という物差しを与える。

## ハーネスへの落とし方

### 誰がどこに定義するか

ハーネスはドメイン語彙を持たない。`domain` / `range` は型を参照するので、そもそもハーネス側では書けない。一方、現在の実装では `domain` / `range` は省略可能で、省略すると無制約になる。したがって**層 1 の名前・向き・意味はハーネスが文書で定め、型への束縛は KB が決める**という分担が、今の実装のまま成立する。

配布は文書とテンプレートで行う。[設定リファレンス](../configuration.md#標準述語) に標準述語表を置き、KB は使う族だけ残して domain / range を足す。`extends:` のような継承機構は、語彙がファイル 1 つで見渡せなくなるため採らない。コードへの埋め込みは、ドメイン語彙を持たない原則に反するため採らない。

### 語彙のキー（実装済み。正本は設定リファレンス）

`vocabulary.yml` の述語に次の任意キーを足す。

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

- `broader`: 親述語の名前。1 つだけ。階層は単一の木に限り、「確度つきの derived-from」「期間つきの part-of」のような別軸の派生は作らない（確度と期間は Claim の領分）。
- `maps_to`: 対応する標準語彙の CURIE または IRI の一覧。ハーネスは文字列のリストであることだけを見て、解決はしない。

### 検査と機能（実装済み。正本は設定リファレンス）

| 対象 | 種別 | 内容 |
|---|---|---|
| `kb validate` | ERROR | `broader` の先が存在する。循環しない。子の `domain` / `range` は親の部分集合（親が無制約なら任意） |
| `kb validate` | WARNING | `related-to` のエッジのうち、始点と終点の型の組が層 1 のちょうど 1 つの述語の domain / range にだけ収まるもの（精緻化の余地） |
| `kb validate` | INFO | `related-to` エッジの件数（分類の負債量） |
| `kb doctor` | WARNING | `related-to` でも標準述語でもなく、`broader` も持たない述語（勝手に層 1 を増やした状態の可視化。止めない） |
| `query` ビュー | 機能 | `where.relation.predicate` に親を書けば子孫のエッジも拾う |
| `graph.json` | 機能 | エッジは書かれた葉の述語をそのまま持つ。汎化は消費側で行うため、`broader` か `maps_to` を持つ語彙では `predicates` オブジェクトで階層と対応を渡す。OKF バンドルへの併記は未実装 |

生成物の決定性は変わらない。

## まとめ

- 述語の詳細度は 0（未分類）/ 1（方向と型制約）/ 2（意味の精緻化）の三層で、段差は 0 → 1 が最大。
- 層 1 はハーネスが文書で標準を定め、KB が型に束縛する。層 2 は KB が任意で親の下に吊るす。層 0 は分類の負債として数える。
- 標準述語は `part-of` / `derived-from` / `created-by` / `located-in` / `follows` の 5 つと、その上の `related-to`。向きは「依存する側から依存される側へ」で統一。時間は入れないが、順序は入れる。
- 複数の族に読める関係は、より多くを含意する族に置く（親子は `derived-from`）。所属と順序、血縁と継承は別のエッジ。対称な関係（兄弟・婚姻）はエッジにせず、共有する親かハブで受ける。
- 名前は既存標準から借りず、`maps_to` で対応を書く。`broader` は `rdfs:subPropertyOf` に相当し、汎化は許すが推移は既定で拒む。
- relation の詳細度は出典なしで断言できる深さまで。それより細かい主張は Claim。

## 未決事項

- 標準述語の改版規則。層 1 は遡って直すのが高い層なので、一度公開したら名前と向きは変えない約束が要る。文書上の宣言で済ませるか、`kb-ontology-core` の版と同じ扱いにするか。
- 層 2 の追加条件の明文化。「その述語で絞る問い合わせが RAG 評価に実在するか」を条件にするか。
- `taught` のような既存 KB の述語の移行手順。ハーネスが述語の向き反転を支援する機能を持つか。
- `maps_to` の CURIE 接頭辞（`dcterms:` `prov:` `wdt:` など）の展開表をどこに置くか。
- 対称な関係の扱い。今は書かずにハブか共有親で受けるが、対称な `related-to` が溜まったら、述語に `symmetric: true` を許して逆向き検査を緩め、向きは slug の辞書順のような機械的規約で決める案を検討する。

## 参照

- DCMI Metadata Terms https://www.dublincore.org/specifications/dublin-core/dcmi-terms/
- PROV-O: The PROV Ontology https://www.w3.org/TR/prov-o/
- SKOS Simple Knowledge Organization System Reference https://www.w3.org/TR/skos-reference/
- ISO 25964-1:2011 Thesauri and interoperability with other vocabularies
- OBO Relation Ontology https://oborel.github.io/
- CIDOC Conceptual Reference Model https://cidoc-crm.org/
- Wikidata プロパティ P361 / P144 / P170 / P276 / P580 / P582
