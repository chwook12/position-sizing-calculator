from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)

MARKETS = {
    "AUTO": {"label": "자동", "currency": ""},
    "KR": {"label": "KR", "currency": "KRW", "nation": "KOR"},
    "US": {"label": "US", "currency": "USD", "nation": "USA"},
    "JP": {"label": "JP", "currency": "JPY", "nation": "JPN"},
    "HK": {"label": "HK", "currency": "HKD", "nation": "HKG"},
    "CN": {"label": "CN", "currency": "CNY", "nation": "CHN"},
    "VN": {"label": "VN", "currency": "VND", "nation": "VNM"},
}

KR_SUFFIX_BY_TYPE = {
    "KOSPI": ".KS",
    "KOSDAQ": ".KQ",
    "KONEX": ".KQ",
}

_search_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_quote_cache: dict[str, tuple[float, dict]] = {}


def http_json(
    url: str,
    timeout: int = 10,
    form: dict | None = None,
    extra_headers: dict | None = None,
) -> dict:
    body = urlencode(form).encode("utf-8") if form else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = Request(url, data=body, headers=headers)
    with urlopen(req, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def json_response(handler: SimpleHTTPRequestHandler, status: int, data: dict | list) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: SimpleHTTPRequestHandler, status: int, message: str) -> None:
    json_response(handler, status, {"error": message})


def market_from_nation(nation_code: str | None) -> str:
    return {
        "KOR": "KR",
        "USA": "US",
        "JPN": "JP",
        "HKG": "HK",
        "CHN": "CN",
        "VNM": "VN",
    }.get(nation_code or "", "AUTO")


def yahoo_symbol_from_naver(item: dict) -> str:
    nation = item.get("nationCode")
    code = str(item.get("code") or "").strip()
    reuters = str(item.get("reutersCode") or "").strip()
    type_code = str(item.get("typeCode") or "").upper()

    if nation == "KOR":
        suffix = KR_SUFFIX_BY_TYPE.get(type_code, ".KS")
        return f"{code}{suffix}"

    if nation == "USA":
        return code

    if reuters:
        return reuters

    return code


def normalize_symbol(symbol: str, market: str) -> list[str]:
    symbol = symbol.strip().upper()
    if not symbol:
        return []

    if "." in symbol or "-" in symbol:
        return [symbol]

    if market == "KR" and re.fullmatch(r"\d{5,6}", symbol):
        return [f"{symbol.zfill(6)}.KS", f"{symbol.zfill(6)}.KQ"]

    if market == "JP" and re.fullmatch(r"\d{4}", symbol):
        return [f"{symbol}.T"]

    if market == "HK" and re.fullmatch(r"\d{1,5}", symbol):
        return [f"{symbol.zfill(4)}.HK"]

    if market == "CN" and re.fullmatch(r"\d{6}", symbol):
        if symbol.startswith("6"):
            return [f"{symbol}.SS"]
        return [f"{symbol}.SZ"]

    if market == "VN":
        return [f"{symbol}.VN", symbol]

    return [symbol]


def parse_price(value) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text.upper() in {"N/A", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def search_naver(query: str, market: str) -> list[dict]:
    url = (
        "https://m.stock.naver.com/front-api/search/autoComplete"
        f"?query={quote(query)}&target=stock"
    )
    try:
        data = http_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    items = data.get("result", {}).get("items", [])
    results = []
    wanted_nation = MARKETS.get(market, {}).get("nation")

    for item in items:
        if item.get("category") != "stock":
            continue
        if wanted_nation and item.get("nationCode") != wanted_nation:
            continue

        item_market = market_from_nation(item.get("nationCode"))
        results.append(
            {
                "symbol": yahoo_symbol_from_naver(item),
                "rawSymbol": item.get("code", ""),
                "name": item.get("name", ""),
                "exchange": item.get("typeName") or item.get("typeCode") or "",
                "market": item_market,
                "currency": MARKETS.get(item_market, {}).get("currency", ""),
                "source": "Naver",
            }
        )

    return results


def naver_domestic_code(symbol: str) -> str | None:
    match = re.search(r"(\d{5,6})(?:\.(?:KS|KQ))?$", symbol.strip().upper())
    if not match:
        return None
    return match.group(1).zfill(6)


def fetch_naver_domestic_quote(symbol: str) -> dict:
    code = naver_domestic_code(symbol)
    if not code:
        raise ValueError("국내 종목 코드가 아닙니다.")

    basic = http_json(f"https://m.stock.naver.com/api/stock/{code}/basic")
    prices = http_json(
        f"https://m.stock.naver.com/api/stock/{code}/price?pageSize=1&page=1"
    )
    latest = prices[0] if prices else {}
    exchange = basic.get("stockExchangeType", {})

    price = parse_price(latest.get("closePrice") or basic.get("closePrice"))
    day_low = parse_price(latest.get("lowPrice"))
    day_high = parse_price(latest.get("highPrice"))
    move = parse_price(basic.get("compareToPreviousClosePrice"))
    move_code = (basic.get("compareToPreviousPrice") or {}).get("code")
    previous_close = None
    if price is not None and move is not None:
        if move_code in {"1", "2"}:
            previous_close = price - move
        elif move_code in {"4", "5"}:
            previous_close = price + move
        else:
            previous_close = price

    if price is None or day_low is None or day_high is None:
        raise ValueError("KRX 가격 데이터를 찾을 수 없습니다.")

    suffix = ".KQ" if exchange.get("code") == "KQ" else ".KS"
    krx_quote = {
        "price": price,
        "dayLow": day_low,
        "dayHigh": day_high,
        "previousClose": previous_close,
        "timestamp": latest.get("localTradedAt") or basic.get("localTradedAt"),
        "source": "Naver/KRX",
        "venue": "KRX",
    }
    venues = {"KRX": krx_quote}

    try:
        venues["NXT"] = fetch_nxt_quote(code)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        pass

    return {
        "symbol": f"{code}{suffix}",
        "name": basic.get("stockName") or code,
        "currency": "KRW",
        "exchange": exchange.get("nameKor") or basic.get("stockExchangeName") or "KRX",
        "price": krx_quote["price"],
        "dayLow": krx_quote["dayLow"],
        "dayHigh": krx_quote["dayHigh"],
        "previousClose": previous_close,
        "timestamp": krx_quote["timestamp"],
        "source": "Naver/KRX",
        "venues": venues,
        "defaultVenue": "KRX",
    }


def fetch_nxt_quote(code: str) -> dict:
    data = http_json(
        "https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do",
        form={"pageIndex": "1", "pageUnit": "20", "searchKeyword": code},
        extra_headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.nextrade.co.kr/menu/transactionStatusMain/menuList.do",
        },
    )
    rows = data.get("brdinfoTimeList") or []
    normalized_code = f"A{code}"
    row = next((item for item in rows if item.get("isuSrdCd") == normalized_code), rows[0] if rows else None)
    if not row:
        raise ValueError("NXT 가격 데이터를 찾을 수 없습니다.")

    price = parse_price(row.get("curPrc"))
    day_low = parse_price(row.get("lwpr"))
    day_high = parse_price(row.get("hgpr"))
    previous_close = parse_price(row.get("basePrc"))
    if price is None or day_low is None or day_high is None:
        raise ValueError("NXT 가격 데이터를 찾을 수 없습니다.")

    return {
        "price": price,
        "dayLow": day_low,
        "dayHigh": day_high,
        "previousClose": previous_close,
        "timestamp": data.get("setTime") or row.get("nowDd"),
        "source": "Nextrade/NXT",
        "venue": "NXT",
        "delay": "20분 지연",
    }


def yahoo_market_from_exchange(exchange: str) -> str:
    exchange = exchange.upper()
    if exchange in {"KSC", "KOE"}:
        return "KR"
    if exchange in {"NMS", "NYQ", "ASE", "BTS", "PCX"}:
        return "US"
    if exchange == "JPX":
        return "JP"
    if exchange == "HKG":
        return "HK"
    if exchange in {"SHH", "SHZ"}:
        return "CN"
    return "AUTO"


def search_yahoo(query: str, market: str) -> list[dict]:
    url = (
        "https://query2.finance.yahoo.com/v1/finance/search"
        f"?q={quote(query)}&quotesCount=12&newsCount=0&listsCount=0&enableFuzzyQuery=true"
    )
    try:
        data = http_json(url)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    results = []
    for quote_item in data.get("quotes", []):
        if quote_item.get("quoteType") not in {"EQUITY", "ETF"}:
            continue
        item_market = yahoo_market_from_exchange(quote_item.get("exchange", ""))
        if market != "AUTO" and item_market != market:
            continue

        results.append(
            {
                "symbol": quote_item.get("symbol", ""),
                "rawSymbol": quote_item.get("symbol", ""),
                "name": quote_item.get("longname") or quote_item.get("shortname") or "",
                "exchange": quote_item.get("exchDisp") or quote_item.get("exchange") or "",
                "market": item_market,
                "currency": MARKETS.get(item_market, {}).get("currency", ""),
                "source": "Yahoo",
            }
        )

    return results


def search_symbols(query: str, market: str) -> list[dict]:
    key = (query.casefold().strip(), market)
    cached = _search_cache.get(key)
    if cached and time.time() - cached[0] < 120:
        return cached[1]

    merged = []
    seen = set()
    for result in search_naver(query, market) + search_yahoo(query, market):
        symbol = result.get("symbol")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        merged.append(result)

    _search_cache[key] = (time.time(), merged[:12])
    return merged[:12]


def fetch_chart(symbol: str) -> dict:
    cached = _quote_cache.get(symbol)
    if cached and time.time() - cached[0] < 30:
        return cached[1]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=5d&interval=1d"
    data = http_json(url)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        error = data.get("chart", {}).get("error") or {}
        raise ValueError(error.get("description") or "가격 데이터를 찾을 수 없습니다.")

    meta = result.get("meta", {})
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    timestamps = result.get("timestamp") or []
    last_index = len(timestamps) - 1
    close_values = quote_data.get("close") or []
    high_values = quote_data.get("high") or []
    low_values = quote_data.get("low") or []

    def latest(values: list, fallback=None):
        for value in reversed(values):
            if value is not None:
                return value
        return fallback

    payload = {
        "symbol": meta.get("symbol") or symbol,
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "currency": meta.get("currency") or "",
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        "price": meta.get("regularMarketPrice") or latest(close_values),
        "dayLow": meta.get("regularMarketDayLow") or latest(low_values),
        "dayHigh": meta.get("regularMarketDayHigh") or latest(high_values),
        "previousClose": meta.get("chartPreviousClose"),
        "timestamp": timestamps[last_index] if last_index >= 0 else None,
    }
    if not payload["price"]:
        raise ValueError("가격 데이터를 찾을 수 없습니다.")

    _quote_cache[symbol] = (time.time(), payload)
    return payload


def quote_symbol(symbol: str, market: str) -> dict:
    last_error = "가격 데이터를 찾을 수 없습니다."
    for candidate in normalize_symbol(symbol, market):
        if market == "KR" or naver_domestic_code(candidate):
            try:
                return fetch_naver_domestic_quote(candidate)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)

        try:
            return fetch_chart(candidate)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
    raise ValueError(last_error)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = unquote((params.get("q") or [""])[0]).strip()
            market = ((params.get("market") or ["AUTO"])[0] or "AUTO").upper()
            if not query:
                return json_response(self, 200, {"results": []})
            return json_response(self, 200, {"results": search_symbols(query, market)})

        if parsed.path == "/api/quote":
            params = parse_qs(parsed.query)
            symbol = unquote((params.get("symbol") or [""])[0]).strip()
            market = ((params.get("market") or ["AUTO"])[0] or "AUTO").upper()
            query = unquote((params.get("q") or [""])[0]).strip()

            if not symbol and query:
                matches = search_symbols(query, market)
                if matches:
                    symbol = matches[0]["symbol"]

            if not symbol:
                return error_response(self, 400, "종목명 또는 심볼을 입력해 주세요.")

            try:
                return json_response(self, 200, quote_symbol(symbol, market))
            except ValueError as exc:
                return error_response(self, 404, str(exc))

        return self.serve_static(parsed.path)

    def serve_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        target = (PUBLIC / path.lstrip("/")).resolve()
        if not str(target).startswith(str(PUBLIC.resolve())) or not target.is_file():
            return self.send_error(404, "File not found")

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def find_port(start: int = 8000) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("사용 가능한 포트를 찾지 못했습니다.")


def main() -> None:
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else int(sys.argv[1]) if len(sys.argv) > 1 else find_port()
    host = "0.0.0.0" if env_port else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), Handler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Position sizing calculator: http://{display_host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
