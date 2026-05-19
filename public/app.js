const marketEl = document.querySelector("#market");
const candleModeEl = document.querySelector("#candleMode");
const entryDateModeEl = document.querySelector("#entryDateMode");
const stopDateModeEl = document.querySelector("#stopDateMode");
const queryEl = document.querySelector("#query");
const suggestionsEl = document.querySelector("#suggestions");
const selectedStockEl = document.querySelector("#selectedStock");
const loadPriceEl = document.querySelector("#loadPrice");
const venueGridEl = document.querySelector(".venue-grid");
const entryVenueEl = document.querySelector("#entryVenue");
const stopVenueEl = document.querySelector("#stopVenue");
const rptBaseSymbolEl = document.querySelector("#rptBaseSymbol");
const entrySymbolEl = document.querySelector("#entrySymbol");
const stopSymbolEl = document.querySelector("#stopSymbol");
const convertedRptEl = document.querySelector("#convertedRpt");
const rptEl = document.querySelector("#rpt");
const entryEl = document.querySelector("#entry");
const stopEl = document.querySelector("#stop");
const longBtn = document.querySelector("#longBtn");
const shortBtn = document.querySelector("#shortBtn");

const outputs = {
  slPercent: document.querySelector("#slPercent"),
  qty: document.querySelector("#qty"),
  positionSize: document.querySelector("#positionSize"),
  riskAmount: document.querySelector("#riskAmount"),
};
const calculationNoteEl = document.querySelector("#calculationNote");

const state = {
  direction: "long",
  selected: null,
  lastQuote: null,
  quotesByDate: {},
  fx: {
    from: "KRW",
    to: "KRW",
    rate: 1,
    krwPerUnit: 1,
    convertedAmount: 1000000,
    source: "KRW",
  },
  fxTimer: null,
  searchTimer: null,
};

const currencySymbols = {
  KRW: "₩",
  USD: "$",
  JPY: "¥",
  HKD: "HK$",
  CNY: "¥",
  VND: "₫",
};

function parseNumber(value) {
  const number = Number(String(value).replace(/[^\d.-]/g, ""));
  return Number.isFinite(number) ? number : 0;
}

function formatNumber(value, maximumFractionDigits = 2) {
  if (!Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits,
  }).format(value);
}

function addThousandsSeparators(value) {
  const text = String(value ?? "").replace(/[^\d.]/g, "");
  if (!text) return "";

  const [integerPart, ...decimalParts] = text.split(".");
  const integer = integerPart.replace(/^0+(?=\d)/, "") || "0";
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  if (text.endsWith(".")) return `${grouped}.`;
  if (decimalParts.length) return `${grouped}.${decimalParts.join("")}`;
  return grouped;
}

function formatControlledInput(input) {
  input.value = addThousandsSeparators(input.value);
}

function formatMoney(value) {
  if (!Number.isFinite(value)) return "-";
  const currency = activeCurrency();
  const prefix = currencySymbols[currency] || `${currency} `;
  const decimals = ["USD", "HKD", "CNY"].includes(currency) ? 2 : 0;
  return `${prefix}${formatNumber(value, decimals)}`;
}

function formatCurrencyAmount(value, currency) {
  if (!Number.isFinite(value)) return "-";
  const prefix = currencySymbols[currency] || `${currency} `;
  const decimals = ["USD", "HKD", "CNY"].includes(currency) ? 2 : 0;
  return `${prefix}${formatNumber(value, decimals)}`;
}

function formatKrwAmount(value) {
  if (!Number.isFinite(value)) return "-";
  return `₩${formatNumber(value, 0)}`;
}

function formatPositionSize(value) {
  const baseText = formatMoney(value);
  const currency = activeCurrency();
  const krwPerUnit = state.fx?.krwPerUnit;
  if (currency === "KRW" || !Number.isFinite(krwPerUnit)) {
    return baseText;
  }

  const krwValue = value * krwPerUnit;
  return `${baseText}<span class="krw-converted">(${formatKrwAmount(krwValue)})</span>`;
}

function activeCurrency() {
  return state.lastQuote?.currency || state.selected?.currency || selectedMarketCurrency() || "KRW";
}

function selectedMarketCurrency() {
  const optionText = marketEl.selectedOptions[0]?.textContent || "";
  const match = optionText.match(/\(([^)]+)\)/);
  return match ? match[1] : "";
}

function setStatus(message, tone = "normal") {
  selectedStockEl.textContent = message;
  selectedStockEl.style.color = tone === "error" ? "var(--red)" : "var(--blue)";
}

function setDirection(direction) {
  state.direction = direction;
  longBtn.classList.toggle("active", direction === "long");
  shortBtn.classList.toggle("active", direction === "short");

  updateStopFromSelectedVenue();
  calculate();
}

function formatInputNumber(value) {
  if (!Number.isFinite(Number(value))) return "";
  return addThousandsSeparators(Number(value).toFixed(4).replace(/\.?0+$/, ""));
}

function setEmptyResults() {
  outputs.slPercent.textContent = "-";
  outputs.qty.textContent = "-";
  outputs.positionSize.textContent = "-";
  outputs.riskAmount.textContent = "-";
  calculationNoteEl.hidden = true;
  calculationNoteEl.textContent = "";
}

function setUnavailableResults(message) {
  outputs.slPercent.textContent = "계산 불가";
  outputs.qty.textContent = "계산 불가";
  outputs.positionSize.textContent = "계산 불가";
  outputs.riskAmount.textContent = "계산 불가";
  calculationNoteEl.hidden = false;
  calculationNoteEl.textContent = message;
}

function calculate() {
  const rpt = state.fx?.convertedAmount || parseNumber(rptEl.value);
  const entry = parseNumber(entryEl.value);
  const stop = parseNumber(stopEl.value);

  if (rpt <= 0 || entry <= 0 || stop <= 0) {
    setEmptyResults();
    return;
  }

  const riskPerShare =
    state.direction === "long"
      ? entry - stop
      : stop - entry;

  if (riskPerShare <= 0) {
    const message =
      state.direction === "long"
        ? "계산 불가: 롱은 손절가가 진입가보다 낮아야 합니다."
        : "계산 불가: 숏은 손절가가 진입가보다 높아야 합니다.";
    setUnavailableResults(message);
    return;
  }

  const qty = Math.floor(rpt / riskPerShare);
  const positionSize = qty * entry;
  const riskAmount = qty * riskPerShare;
  const slPercent = (riskPerShare / entry) * 100;

  outputs.slPercent.textContent = `${formatNumber(slPercent, 2)}%`;
  outputs.qty.textContent = formatNumber(qty, 0);
  outputs.positionSize.innerHTML = formatPositionSize(positionSize);
  outputs.riskAmount.textContent = formatMoney(riskAmount);
  calculationNoteEl.hidden = true;
  calculationNoteEl.textContent = "";
}

function updateRptPrefix() {
  rptBaseSymbolEl.textContent = currencySymbols.KRW;
  syncCurrencyPrefixSpace(rptBaseSymbolEl);
}

function updatePricePrefixes() {
  const symbol = currencySymbols[activeCurrency()] || activeCurrency();
  entrySymbolEl.textContent = symbol;
  stopSymbolEl.textContent = symbol;
  syncCurrencyPrefixSpace(entrySymbolEl);
  syncCurrencyPrefixSpace(stopSymbolEl);
}

function periodWord() {
  return candleModeEl.value === "W" ? "거래주" : "거래일";
}

function updateDateModeLabels() {
  const word = periodWord();
  [...entryDateModeEl.options, ...stopDateModeEl.options].forEach((option) => {
    option.textContent = option.value === "PREV" ? `직전 ${word}` : `최신 ${word}`;
  });
}

function syncCurrencyPrefixSpace(prefixEl) {
  const wrapper = prefixEl.closest(".money-input");
  if (!wrapper) return;

  requestAnimationFrame(() => {
    const prefixWidth = prefixEl.getBoundingClientRect().width;
    wrapper.style.setProperty("--prefix-space", `${Math.ceil(prefixWidth) + 30}px`);
  });
}

function renderConvertedRpt() {
  const baseAmount = parseNumber(rptEl.value);
  const currency = activeCurrency();
  const converted = currency === "KRW" ? baseAmount : state.fx?.convertedAmount;

  if (!baseAmount) {
    convertedRptEl.textContent = "적용 RPT: -";
    return;
  }

  const convertedText = formatCurrencyAmount(converted || 0, currency);
  if (currency === "KRW") {
    convertedRptEl.textContent = `적용 RPT: ${convertedText}`;
    return;
  }

  const krwPerUnit = state.fx?.krwPerUnit;
  const rateText = krwPerUnit
    ? ` · 1 ${currency} ≈ ₩${formatNumber(krwPerUnit, 2)}`
    : "";
  convertedRptEl.textContent = `적용 RPT: ${convertedText}${rateText}`;
}

async function refreshFx() {
  const baseAmount = parseNumber(rptEl.value);
  const currency = activeCurrency();
  updateRptPrefix();
  updatePricePrefixes();

  if (!baseAmount || currency === "KRW") {
    state.fx = {
      from: "KRW",
      to: "KRW",
      rate: 1,
      krwPerUnit: 1,
      convertedAmount: baseAmount,
      source: "KRW",
    };
    renderConvertedRpt();
    calculate();
    return;
  }

  convertedRptEl.textContent = "적용 RPT: 환율 조회 중...";
  try {
    const params = new URLSearchParams({
      amount: String(baseAmount),
      to: currency,
    });
    const response = await fetch(`/api/fx?${params}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "환율을 불러오지 못했습니다.");
    }
    state.fx = data;
    renderConvertedRpt();
  } catch (error) {
    state.fx = null;
    convertedRptEl.textContent = error.message;
  }
  calculate();
}

function debounceFx() {
  const baseAmount = parseNumber(rptEl.value);
  const currency = activeCurrency();
  if (state.fx?.to === currency && Number.isFinite(state.fx.rate)) {
    state.fx = {
      ...state.fx,
      amount: baseAmount,
      convertedAmount: baseAmount * state.fx.rate,
    };
    renderConvertedRpt();
    calculate();
  }

  clearTimeout(state.fxTimer);
  state.fxTimer = setTimeout(refreshFx, 250);
}

function debounceSearch() {
  clearTimeout(state.searchTimer);
  const query = queryEl.value.trim();
  state.selected = null;

  if (query.length < 2) {
    suggestionsEl.hidden = true;
    suggestionsEl.innerHTML = "";
    return;
  }

  state.searchTimer = setTimeout(() => search(query), 220);
}

async function search(query) {
  try {
    const response = await fetch(
      `/api/search?q=${encodeURIComponent(query)}&market=${marketEl.value}`
    );
    const data = await response.json();
    renderSuggestions(data.results || []);
  } catch {
    suggestionsEl.hidden = true;
  }
}

function renderSuggestions(results) {
  suggestionsEl.innerHTML = "";
  if (!results.length) {
    suggestionsEl.hidden = true;
    return;
  }

  const fragment = document.createDocumentFragment();
  results.slice(0, 7).forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion";
    button.innerHTML = `
      <span>
        <strong>${escapeHtml(item.name || item.symbol)}</strong>
        <span>${escapeHtml(item.exchange || item.market || "")}</span>
      </span>
      <code>${escapeHtml(item.symbol)}</code>
    `;
    button.addEventListener("click", () => selectStock(item));
    fragment.appendChild(button);
  });

  suggestionsEl.appendChild(fragment);
  suggestionsEl.hidden = false;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function selectStock(item) {
  state.selected = item;
  queryEl.value = item.name || item.symbol;
  suggestionsEl.hidden = true;
  setStatus(`${item.name || item.symbol} · ${item.symbol}`);
}

function updateLoadedStatus() {
  if (!state.lastQuote) return;
  const entryQuote = quoteForSelection("entry");
  const stopQuote = quoteForSelection("stop");
  const entryVenue = entryQuote?.venue || entryVenueEl.value;
  const stopVenue = stopQuote?.venue || stopVenueEl.value;
  const source = entryQuote?.source || state.lastQuote.source;
  const delay = entryQuote?.delay ? ` · ${entryQuote.delay}` : "";
  const entryDate = describeQuoteDate(entryQuote, entryDateModeEl.value);
  const stopDate = describeQuoteDate(stopQuote, stopDateModeEl.value);
  setStatus(
    `${state.lastQuote.name || state.lastQuote.symbol} · ${state.lastQuote.symbol} · ${state.lastQuote.currency} · 진입 ${entryDate} ${entryVenue} / 손절 ${stopDate} ${stopVenue} · ${source}${delay}`
  );
}

function describeQuoteDate(quote, mode) {
  const label = `${mode === "PREV" ? "직전" : "최신"} ${quote?.candle === "W" ? "주" : "일"}`;
  return quote?.tradingDate ? `${label}(${quote.tradingDate})` : label;
}

function quoteBundleForDate(dateMode) {
  return state.quotesByDate?.[dateMode] || null;
}

function quoteForSelection(kind) {
  const dateMode = kind === "entry" ? entryDateModeEl.value : stopDateModeEl.value;
  const venue = kind === "entry" ? entryVenueEl.value : stopVenueEl.value;
  const bundle = quoteBundleForDate(dateMode);
  if (!bundle) return null;
  return bundle.venues?.[venue] || bundle;
}

function updateVenueControls() {
  updateVenueVisibility();

  const entryBundle = quoteBundleForDate(entryDateModeEl.value);
  const stopBundle = quoteBundleForDate(stopDateModeEl.value);
  updateVenueSelect(entryVenueEl, entryBundle);
  updateVenueSelect(stopVenueEl, stopBundle);
  updateVenueLabels();
}

function updateVenueVisibility() {
  const selectedBundles = [quoteBundleForDate(entryDateModeEl.value), quoteBundleForDate(stopDateModeEl.value)];
  const shouldShow =
    activeCurrency() === "KRW" &&
    selectedBundles.some((bundle) => Object.keys(bundle?.venues || {}).length > 1);
  venueGridEl.hidden = !shouldShow;
}

function updateVenueSelect(selectEl, bundle) {
  const venues = bundle?.venues || {};
  const hasVenueData = Boolean(bundle?.venues);
  selectEl.disabled = !hasVenueData;

  [...selectEl.options].forEach((option) => {
    option.disabled = hasVenueData && !venues[option.value];
  });

  if (!venues[selectEl.value]) selectEl.value = "KRX";
}

function updateVenueLabels() {
  const nxtQuote = state.quotesByDate?.TODAY?.venues?.NXT;
  const label = nxtQuote?.realtime
    ? "NXT (실시간)"
    : nxtQuote?.delay
      ? `NXT (${nxtQuote.delay})`
      : "NXT";

  [...entryVenueEl.options, ...stopVenueEl.options].forEach((option) => {
    if (option.value === "NXT") option.textContent = label;
  });
}

function updateEntryFromSelectedVenue() {
  const quote = quoteForSelection("entry");
  if (!quote) return;
  entryEl.value = formatInputNumber(quote.price);
  updateLoadedStatus();
  calculate();
}

function updateStopFromSelectedVenue() {
  const quote = quoteForSelection("stop");
  if (!quote) return;
  stopEl.value =
    state.direction === "long"
      ? formatInputNumber(quote.dayLow)
      : formatInputNumber(quote.dayHigh);
  updateLoadedStatus();
  calculate();
}

function applyLoadedQuotes(quotesByDate) {
  state.quotesByDate = quotesByDate;
  state.lastQuote = quotesByDate.TODAY || quotesByDate.PREV;
  updatePricePrefixes();
  updateVenueControls();
  updateEntryFromSelectedVenue();
  updateStopFromSelectedVenue();
  refreshFx();
}

async function loadPrice() {
  const query = queryEl.value.trim();
  if (!query) {
    setStatus("종목명 또는 심볼을 입력해 주세요.", "error");
    return;
  }

  loadPriceEl.disabled = true;
  loadPriceEl.textContent = "불러오는 중";
  setStatus("가격 데이터를 불러오는 중입니다...");

  try {
    const baseParams = {
      market: marketEl.value,
      candle: candleModeEl.value,
      q: query,
    };
    if (state.selected?.symbol) {
      baseParams.symbol = state.selected.symbol;
    }

    const [todayQuote, prevQuote] = await Promise.all([
      fetchQuoteForDate(baseParams, "TODAY"),
      fetchQuoteForDate(baseParams, "PREV"),
    ]);

    applyLoadedQuotes({ TODAY: todayQuote, PREV: prevQuote });
    updateLoadedStatus();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    loadPriceEl.disabled = false;
    loadPriceEl.textContent = "가격 불러오기";
  }
}

async function fetchQuoteForDate(baseParams, dateMode) {
  const params = new URLSearchParams({
    ...baseParams,
    dateMode,
  });
  const response = await fetch(`/api/quote?${params}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "가격을 불러오지 못했습니다.");
  }
  return data;
}

queryEl.addEventListener("input", debounceSearch);
queryEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadPrice();
  }
});
marketEl.addEventListener("change", () => {
  clearLoadedInputs();
  updatePricePrefixes();
  updateVenueControls();
  updateVenueVisibility();
  debounceSearch();
  debounceFx();
  calculate();
});
candleModeEl.addEventListener("change", () => {
  state.lastQuote = null;
  state.quotesByDate = {};
  entryEl.value = "";
  stopEl.value = "";
  updateDateModeLabels();
  updateVenueControls();
  updateVenueVisibility();
  setStatus(`${candleModeEl.value === "W" ? "주봉" : "일봉"} 기준으로 가격을 다시 불러와 주세요.`);
  calculate();
});
entryDateModeEl.addEventListener("change", () => {
  updateVenueControls();
  updateEntryFromSelectedVenue();
});
stopDateModeEl.addEventListener("change", () => {
  updateVenueControls();
  updateStopFromSelectedVenue();
});

function clearLoadedInputs() {
  state.selected = null;
  state.lastQuote = null;
  state.quotesByDate = {};
  queryEl.value = "";
  entryEl.value = "";
  stopEl.value = "";
  suggestionsEl.hidden = true;
  suggestionsEl.innerHTML = "";
  selectedStockEl.textContent = "종목을 검색해 주세요.";
  selectedStockEl.style.color = "var(--blue)";
}
loadPriceEl.addEventListener("click", loadPrice);
entryVenueEl.addEventListener("change", updateEntryFromSelectedVenue);
stopVenueEl.addEventListener("change", updateStopFromSelectedVenue);
longBtn.addEventListener("click", () => setDirection("long"));
shortBtn.addEventListener("click", () => setDirection("short"));
[rptEl, entryEl, stopEl].forEach((input) =>
  input.addEventListener("input", () => {
    formatControlledInput(input);
    if (input === rptEl) debounceFx();
    calculate();
  })
);

queryEl.value = "삼성전자";
updateDateModeLabels();
updateVenueControls();
updateVenueVisibility();
updatePricePrefixes();
refreshFx();
search("삼성전자");
calculate();
