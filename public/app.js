const marketEl = document.querySelector("#market");
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

const state = {
  direction: "long",
  selected: null,
  lastQuote: null,
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

function calculate() {
  const rpt = state.fx?.convertedAmount || parseNumber(rptEl.value);
  const entry = parseNumber(entryEl.value);
  const stop = parseNumber(stopEl.value);
  const riskPerShare = Math.abs(entry - stop);

  if (rpt <= 0 || entry <= 0 || stop <= 0 || riskPerShare <= 0) {
    outputs.slPercent.textContent = "-";
    outputs.qty.textContent = "-";
    outputs.positionSize.textContent = "-";
    outputs.riskAmount.textContent = "-";
    return;
  }

  const qty = Math.floor(rpt / riskPerShare);
  const positionSize = qty * entry;
  const riskAmount = qty * riskPerShare;
  const slPercent = (riskPerShare / entry) * 100;

  outputs.slPercent.textContent = `${formatNumber(slPercent, 2)}%`;
  outputs.qty.textContent = formatNumber(qty, 0);
  outputs.positionSize.textContent = formatMoney(positionSize);
  outputs.riskAmount.textContent = formatMoney(riskAmount);
}

function updateRptPrefix() {
  rptBaseSymbolEl.textContent = currencySymbols.KRW;
}

function updatePricePrefixes() {
  const symbol = currencySymbols[activeCurrency()] || activeCurrency();
  entrySymbolEl.textContent = symbol;
  stopSymbolEl.textContent = symbol;
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
  const entryVenue = quoteForVenue(entryVenueEl.value)?.venue || entryVenueEl.value;
  const stopVenue = quoteForVenue(stopVenueEl.value)?.venue || stopVenueEl.value;
  setStatus(
    `${state.lastQuote.name || state.lastQuote.symbol} · ${state.lastQuote.symbol} · ${state.lastQuote.currency} · 진입 ${entryVenue} / 손절 ${stopVenue}`
  );
}

function quoteForVenue(venue) {
  if (!state.lastQuote) return null;
  return state.lastQuote.venues?.[venue] || state.lastQuote;
}

function updateVenueControls() {
  const hasVenueData = Boolean(state.lastQuote?.venues);
  updateVenueVisibility();
  entryVenueEl.disabled = !hasVenueData;
  stopVenueEl.disabled = !hasVenueData;

  [...entryVenueEl.options].forEach((option) => {
    option.disabled = hasVenueData && !state.lastQuote.venues[option.value];
  });
  [...stopVenueEl.options].forEach((option) => {
    option.disabled = hasVenueData && !state.lastQuote.venues[option.value];
  });

  if (!state.lastQuote?.venues?.[entryVenueEl.value]) entryVenueEl.value = "KRX";
  if (!state.lastQuote?.venues?.[stopVenueEl.value]) stopVenueEl.value = "KRX";
}

function updateVenueVisibility() {
  const shouldShow = activeCurrency() === "KRW" && Boolean(state.lastQuote?.venues);
  venueGridEl.hidden = !shouldShow;
}

function updateEntryFromSelectedVenue() {
  const quote = quoteForVenue(entryVenueEl.value);
  if (!quote) return;
  entryEl.value = formatInputNumber(quote.price);
  updateLoadedStatus();
  calculate();
}

function updateStopFromSelectedVenue() {
  const quote = quoteForVenue(stopVenueEl.value);
  if (!quote) return;
  stopEl.value =
    state.direction === "long"
      ? formatInputNumber(quote.dayLow)
      : formatInputNumber(quote.dayHigh);
  updateLoadedStatus();
  calculate();
}

function applyLoadedQuote(data) {
  state.lastQuote = data;
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
    const params = new URLSearchParams({
      market: marketEl.value,
      q: query,
    });
    if (state.selected?.symbol) {
      params.set("symbol", state.selected.symbol);
    }

    const response = await fetch(`/api/quote?${params}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "가격을 불러오지 못했습니다.");
    }

    applyLoadedQuote(data);
    updateLoadedStatus();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    loadPriceEl.disabled = false;
    loadPriceEl.textContent = "가격 불러오기";
  }
}

queryEl.addEventListener("input", debounceSearch);
queryEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadPrice();
  }
});
marketEl.addEventListener("change", () => {
  state.selected = null;
  state.lastQuote = null;
  queryEl.value = "";
  entryEl.value = "";
  stopEl.value = "";
  suggestionsEl.hidden = true;
  suggestionsEl.innerHTML = "";
  selectedStockEl.textContent = "종목을 검색해 주세요.";
  selectedStockEl.style.color = "var(--blue)";
  updatePricePrefixes();
  updateVenueControls();
  updateVenueVisibility();
  debounceSearch();
  debounceFx();
  calculate();
});
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
rptEl.value = addThousandsSeparators(rptEl.value);
updateVenueControls();
updateVenueVisibility();
updatePricePrefixes();
refreshFx();
search("삼성전자");
calculate();
