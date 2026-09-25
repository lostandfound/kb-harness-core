const app = document.querySelector("#app");
const dialog = document.querySelector("#entity-dialog");
const entityById = new Map();
let tagLabels = {};
const preferredLanguage = navigator.languages?.[0] || navigator.language || "en";
const locale = preferredLanguage.toLowerCase().startsWith("ja") ? "ja" : "en";

const messages = {
  en: {
    pageTitle: "Knowledge Flashcards",
    pageSuffix: "Flashcards",
    brandAria: "Knowledge Flashcards home",
    brandMark: "K",
    brandFirst: "Knowledge",
    brandSecond: "Flashcards",
    headerNote: "Review concepts, one card at a time",
    loading: "Loading study cards…",
    footer: "Your answers stay in this session only",
    related: "Related items",
    close: "Close",
    dialogOpen: "Read full details",
    setupEyebrow: "STUDY SESSION",
    setupTitle: "Review what you know",
    setupLede: "Choose a category, recall what each item means, then reveal the answer to check your understanding.",
    genre: "Category",
    chooseGenre: "Choose a category",
    itemCount: (count) => `${count} ${count === 1 ? "item" : "items"}`,
    questionCount: "Number of cards",
    countHint: "10 cards by default",
    all: "All",
    question: (count) => `${count} ${count === 1 ? "card" : "cards"}`,
    noneAvailable: "There are no cards in this category.",
    fewerAvailable: (available, count) => `Only ${available} available. This session will have ${count} ${count === 1 ? "card" : "cards"}.`,
    start: "Start session",
    quiz: "Flashcard question",
    progress: (current, total) => `${current} of ${total}`,
    chooseAnother: "Change category",
    prompt: "Think about what this item is and how you would explain it.",
    answer: "ANSWER",
    overview: "OVERVIEW",
    details: "Read detailed notes",
    relatedBy: { "used-for": "Used for", "production-involves": "Made with", default: "Related" },
    showAnswer: "Reveal answer",
    review: "Review again",
    known: "Got it",
    complete: "SESSION COMPLETE",
    resultTitle: (genre) => `${genre} · Results`,
    resultLede: "Here is a recap of this session.",
    gotIt: "Got it",
    needsReview: "Review again",
    needsReviewHeading: "Cards to review",
    noReview: "Nothing to review. Nice work!",
    moreDetails: "Read more",
    back: "Choose category",
    again: "Play again",
    loadError: "Could not load the study cards.",
    loadHelp: "Check that the app is served over HTTP, then reload the page.",
    emptyData: "No study cards are available.",
    types: {},
    genres: { all: "All categories" },
  },
  ja: {
    pageTitle: "学習カード",
    pageSuffix: "学習カード",
    brandAria: "学習カード ホーム",
    brandMark: "学",
    brandFirst: "学習",
    brandSecond: "学習カード",
    headerNote: "",
    loading: "学習項目を読み込んでいます…",
    footer: "回答はこのセッション中だけ保持されます",
    related: "関連項目",
    close: "閉じる",
    dialogOpen: "詳しい説明を読む",
    setupEyebrow: "学習セッション",
    setupTitle: "知識をカードで確認する",
    setupLede: "ジャンルを選び、項目の内容を思い出してから答えを開いて理解度を確認します。",
    genre: "ジャンル",
    chooseGenre: "出題するジャンルを選択",
    itemCount: (count) => `${count}件の項目`,
    questionCount: "出題数",
    countHint: "初期設定は10問",
    all: "全件",
    question: (count) => `${count}問`,
    noneAvailable: "このジャンルには出題できる項目がありません。",
    fewerAvailable: (available, count) => `このジャンルは${available}件のため、${count}問を出題します。`,
    start: "クイズを始める",
    quiz: "クイズ問題",
    progress: (current, total) => `${current} / ${total} 問`,
    chooseAnother: "ジャンル選択へ",
    prompt: "この項目がどんなものか、説明を思い出してみましょう。",
    answer: "答え",
    overview: "概要",
    details: "詳しい内容を見る",
    relatedBy: { "used-for": "使用先", "production-involves": "製作に関係", default: "関連" },
    showAnswer: "回答を表示",
    review: "要復習",
    known: "わかった",
    complete: "セッション完了",
    resultTitle: (genre) => `${genre}の結果`,
    resultLede: "今回のセッションを振り返りましょう。",
    gotIt: "わかった",
    needsReview: "要復習",
    needsReviewHeading: "要復習の項目",
    noReview: "要復習の項目はありません",
    moreDetails: "詳しい説明",
    back: "ジャンル選択へ",
    again: "同じ条件でもう一度",
    loadError: "学習項目を読み込めませんでした。",
    loadHelp: "起動方法を確認して、ページを再読み込みしてください。",
    emptyData: "学習項目がありません。",
    types: {},
    genres: { all: "すべて" },
  },
};
const t = messages[locale];
const state = { genre: "all", count: 10, deck: [], index: 0, revealed: false, answers: new Map() };

document.documentElement.lang = locale;
document.title = t.pageTitle;
document.querySelector(".brand").setAttribute("aria-label", t.brandAria);
document.querySelector(".brand-mark").textContent = t.brandMark;
document.querySelector(".brand").lastElementChild.innerHTML = `${escapeHtml(t.brandFirst)} <span class="brand-light">${escapeHtml(t.brandSecond)}</span>`;
document.querySelector(".topbar-note").textContent = t.headerNote;
document.querySelector(".loading-state").textContent = t.loading;
document.querySelector(".site-footer").textContent = t.footer;
document.querySelector('[data-i18n="related"]').textContent = t.related;
document.querySelector("[data-close-dialog]").setAttribute("aria-label", t.close);
document.querySelector("#kb-title").textContent = t.headerNote;

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

function entityGenres(entity) {
  return [entity.type, ...(entity.tags || [])];
}

function genreName(id) {
  return t.genres[id] || tagLabels[id] || t.types[id] || id.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function availableEntities() {
  return [...entityById.values()].filter((entity) => state.genre === "all" || entityGenres(entity).includes(state.genre));
}

function getGenres() {
  const values = new Set(["all"]);
  for (const entity of entityById.values()) for (const genre of entityGenres(entity)) values.add(genre);
  return [...values].map((id) => ({
    id,
    label: genreName(id),
    count: id === "all" ? entityById.size : [...entityById.values()].filter((entity) => entityGenres(entity).includes(id)).length,
  }));
}

function renderSetup() {
  const genres = getGenres();
  const available = availableEntities().length;
  const requested = state.count === "all" ? available : state.count;
  const actualCount = Math.min(requested, available);
  const options = [5, 10, 20, "all"];
  const note = available === 0 ? t.noneAvailable : actualCount < requested ? t.fewerAvailable(available, actualCount) : "";

  app.innerHTML = `
    <section class="setup" aria-labelledby="page-title">
      <p class="eyebrow">${escapeHtml(t.setupEyebrow)}</p>
      <h1 id="page-title">${escapeHtml(t.setupTitle)}</h1>
      <p class="lede">${escapeHtml(t.setupLede)}</p>
      <div class="section-label"><span>${escapeHtml(t.genre)}</span><small>${escapeHtml(t.itemCount(entityById.size))}</small></div>
      <div class="genre-grid" role="group" aria-label="${escapeHtml(t.chooseGenre)}">
        ${genres.map((genre) => `<button class="genre-option" type="button" data-genre="${escapeHtml(genre.id)}" aria-pressed="${genre.id === state.genre}"><span class="genre-name">${escapeHtml(genre.label)}</span><span class="genre-count">${escapeHtml(t.itemCount(genre.count))}</span></button>`).join("")}
      </div>
      <div class="section-label"><span>${escapeHtml(t.questionCount)}</span><small>${escapeHtml(t.countHint)}</small></div>
      <div class="count-options" role="group" aria-label="${escapeHtml(t.questionCount)}">
        ${options.map((count) => `<button class="count-option" type="button" data-count="${count}" aria-pressed="${String(count) === String(state.count)}">${escapeHtml(count === "all" ? t.all : t.question(count))}</button>`).join("")}
      </div>
      <p class="availability" role="status">${escapeHtml(note)}</p>
      <div class="setup-actions"><button class="button button-primary" type="button" data-action="start" ${actualCount === 0 ? "disabled" : ""}>${escapeHtml(t.start)} <span aria-hidden="true">→</span></button></div>
    </section>`;
}

function renderQuiz() {
  const entity = entityById.get(state.deck[state.index]);
  const total = state.deck.length;
  const progress = ((state.index + 1) / total) * 100;
  const related = (entity.related || []).filter((item) => entityById.has(item.id));
  const relationName = (relation) => t.relatedBy[relation] || t.relatedBy.default;

  app.innerHTML = `
    <section class="quiz" aria-label="${escapeHtml(t.quiz)}">
      <div class="quiz-top"><span>${escapeHtml(t.progress(state.index + 1, total))}</span><button class="text-button" type="button" data-action="quit">${escapeHtml(t.chooseAnother)}</button></div>
      <div class="progress-track" role="progressbar" aria-label="${escapeHtml(t.progress(state.index + 1, total))}" aria-valuemin="1" aria-valuemax="${total}" aria-valuenow="${state.index + 1}"><div class="progress-fill" style="width:${progress}%"></div></div>
      <article class="flashcard">
        <span class="type-pill">${escapeHtml(genreName(entity.type))}</span>
        <h1 class="card-title">${escapeHtml(entity.title)}</h1>
        <p class="card-prompt">${escapeHtml(t.prompt)}</p>
        ${state.revealed ? `
          <div class="answer">
            <p class="answer-label">${escapeHtml(t.overview)}</p>
            <p class="answer-text">${escapeHtml(entity.description)}</p>
            ${entity.details ? `<details class="detailed-content"><summary>${escapeHtml(t.details)}</summary><div class="detail-body">${renderMarkdown(entity.details)}</div></details>` : ""}
            ${related.length ? `<div class="related"><p class="related-heading">${escapeHtml(t.related)}</p><div class="related-list">${related.map((item) => `<button class="related-link" type="button" data-entity="${escapeHtml(item.id)}"><span>${escapeHtml(item.title)}</span><small>${escapeHtml(relationName(item.relation))}</small></button>`).join("")}</div></div>` : ""}
          </div>` : `<button class="button button-primary reveal-button" type="button" data-action="reveal">${escapeHtml(t.showAnswer)} <span aria-hidden="true">↓</span></button>`}
      </article>
      ${state.revealed ? `<div class="mark-actions"><button class="mark-button mark-review" type="button" data-answer="review">↻　${escapeHtml(t.review)}</button><button class="mark-button mark-known" type="button" data-answer="known">✓　${escapeHtml(t.known)}</button></div>` : ""}
    </section>`;
  if (state.revealed) app.querySelector('[data-answer="review"]').focus();
}

function renderMarkdown(markdown = "") {
  const inline = (text) => escapeHtml(text).replace(/\[([^\]]+)\]\((\/[^)\s]+)\)/g, (_match, label, path) =>
    `<button class="inline-entity-link" type="button" data-entity="${escapeHtml(path)}">${label}</button>`);
  return markdown.split(/\n\s*\n/).map((block) => {
    const text = block.trim();
    if (!text) return "";
    const heading = text.match(/^(#{1,4})\s+(.+)$/s);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      return `<h${level}>${inline(heading[2])}</h${level}>`;
    }
    return `<p>${inline(text.replace(/\n/g, " "))}</p>`;
  }).join("");
}

function renderResult() {
  const known = [...state.answers.values()].filter((answer) => answer === "known").length;
  const needsReview = state.deck.filter((id) => state.answers.get(id) === "review").map((id) => entityById.get(id));
  app.innerHTML = `
    <section class="result" aria-labelledby="result-title">
      <p class="eyebrow">${escapeHtml(t.complete)}</p>
      <h1 id="result-title">${escapeHtml(t.resultTitle(genreName(state.genre)))}</h1>
      <p class="lede">${escapeHtml(t.resultLede)}</p>
      <div class="result-summary"><div class="summary-item"><span class="summary-label">${escapeHtml(t.gotIt)}</span><span class="summary-value">${known}<small> / ${state.deck.length}</small></span></div><div class="summary-item"><span class="summary-label">${escapeHtml(t.needsReview)}</span><span class="summary-value">${needsReview.length}<small> ${escapeHtml(locale === "ja" ? "件" : "cards")}</small></span></div></div>
      <h2 class="result-heading">${escapeHtml(t.needsReviewHeading)}</h2>
      ${needsReview.length ? `<ul class="review-list">${needsReview.map((entity) => `<li class="review-row"><div><span class="review-title">${escapeHtml(entity.title)}</span><span class="review-desc">${escapeHtml(entity.description)}</span></div><button class="open-entity" type="button" data-entity="${escapeHtml(entity.id)}">${escapeHtml(t.moreDetails)} ↗</button></li>`).join("")}</ul>` : `<p class="empty-review">${escapeHtml(t.noReview)}</p>`}
      <div class="result-actions"><button class="button button-secondary" type="button" data-action="home">${escapeHtml(t.back)}</button><button class="button button-primary" type="button" data-action="again">${escapeHtml(t.again)} <span aria-hidden="true">↻</span></button></div>
    </section>`;
  app.querySelector('[data-action="home"]').focus();
}

function startQuiz() {
  const pool = availableEntities();
  const count = Math.min(state.count === "all" ? pool.length : state.count, pool.length);
  const shuffled = pool.map((entity) => entity.id);
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  state.deck = shuffled.slice(0, count);
  state.index = 0;
  state.revealed = false;
  state.answers = new Map();
  renderQuiz();
}

app.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.genre) {
    state.genre = button.dataset.genre;
    renderSetup();
  } else if (button.dataset.count) {
    state.count = button.dataset.count === "all" ? "all" : Number(button.dataset.count);
    renderSetup();
  } else if (button.dataset.action === "start" || button.dataset.action === "again") {
    startQuiz();
  } else if (button.dataset.action === "reveal") {
    state.revealed = true;
    renderQuiz();
  } else if (button.dataset.answer) {
    state.answers.set(state.deck[state.index], button.dataset.answer);
    if (state.index + 1 === state.deck.length) renderResult();
    else {
      state.index += 1;
      state.revealed = false;
      renderQuiz();
    }
  } else if (button.dataset.action === "home" || button.dataset.action === "quit") {
    renderSetup();
  } else if (button.dataset.entity) {
    showEntity(button.dataset.entity);
  }
});

function showEntity(id) {
  const entity = entityById.get(id);
  if (!entity) return;
  document.querySelector("#dialog-title").textContent = entity.title;
  document.querySelector("#dialog-type").textContent = `${genreName(entity.type)} · ${(entity.tags || []).map(genreName).join(" / ")}`;
  document.querySelector("#dialog-description").textContent = entity.description;
  document.querySelector("#dialog-detail-body").innerHTML = renderMarkdown(entity.details || "");
  if (!dialog.open) dialog.showModal();
}

dialog.addEventListener("click", (event) => {
  if (event.target === dialog || event.target.closest("[data-close-dialog]")) dialog.close();
  else if (event.target.closest("[data-entity]")) showEntity(event.target.closest("[data-entity]").dataset.entity);
});

fetch("/api/flashcards")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((data) => {
    tagLabels = data.tagLabels || {};
    document.querySelector("#kb-title").textContent = data.title || t.headerNote;
    document.title = `${data.title || t.pageTitle} · ${t.pageSuffix}`;
    for (const entity of data.entities || []) entityById.set(entity.id, entity);
    if (!entityById.size) throw new Error(t.emptyData);
    renderSetup();
  })
  .catch((error) => {
    app.innerHTML = `<div class="error-state">${escapeHtml(t.loadError)}<br><small>${escapeHtml(error.message)}</small><p>${escapeHtml(t.loadHelp)}</p></div>`;
  });
