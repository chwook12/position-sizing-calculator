from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import sys
import time
import asyncio
import base64
import hmac
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
_fx_cache: dict[str, tuple[float, dict]] = {}
_kis_approval_cache: dict[str, tuple[float, str]] = {}

FX_SYMBOLS = {
    "USD": "KRW=X",
    "JPY": "JPYKRW=X",
    "HKD": "HKDKRW=X",
    "CNY": "CNYKRW=X",
}

KIS_CONFIG_FILE = ROOT / "kis_config.json"
KIS_REST_BASE = {
    "prod": "https://openapi.koreainvestment.com:9443",
    "vps": "https://openapivts.koreainvestment.com:29443",
}
KIS_WS_BASE = {
    "prod": "ws://ops.koreainvestment.com:21000/tryitout",
    "vps": "ws://ops.koreainvestment.com:31000/tryitout",
}
KIS_NXT_CCN_COLUMNS = [
    "MKSC_SHRN_ISCD",
    "STCK_CNTG_HOUR",
    "STCK_PRPR",
    "PRDY_VRSS_SIGN",
    "PRDY_VRSS",
    "PRDY_CTRT",
    "WGHN_AVRG_STCK_PRC",
    "STCK_OPRC",
    "STCK_HGPR",
    "STCK_LWPR",
    "ASKP1",
    "BIDP1",
    "CNTG_VOL",
    "ACML_VOL",
    "ACML_TR_PBMN",
    "SELN_CNTG_CSNU",
    "SHNU_CNTG_CSNU",
    "NTBY_CNTG_CSNU",
    "CTTR",
    "SELN_CNTG_SMTN",
    "SHNU_CNTG_SMTN",
    "CNTG_CLS_CODE",
    "SHNU_RATE",
    "PRDY_VOL_VRSS_ACML_VOL_RATE",
    "OPRC_HOUR",
    "OPRC_VRSS_PRPR_SIGN",
    "OPRC_VRSS_PRPR",
    "HGPR_HOUR",
    "HGPR_VRSS_PRPR_SIGN",
    "HGPR_VRSS_PRPR",
    "LWPR_HOUR",
    "LWPR_VRSS_PRPR_SIGN",
    "LWPR_VRSS_PRPR",
    "BSOP_DATE",
    "NEW_MKOP_CLS_CODE",
    "TRHT_YN",
    "ASKP_RSQN1",
    "BIDP_RSQN1",
    "TOTAL_ASKP_RSQN",
    "TOTAL_BIDP_RSQN",
    "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL",
    "PRDY_SMNS_HOUR_ACML_VOL_RATE",
    "HOUR_CLS_CODE",
    "MRKT_TRTM_CLS_CODE",
    "VI_STND_PRC",
]


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


def http_json_post(url: str, payload: dict, timeout: int = 10) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def is_authorized(headers) -> bool:
    password = os.environ.get("APP_PASSWORD", "").strip()
    if not password:
        return True

    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[6:], validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False

    username, separator, given_password = decoded.partition(":")
    if not separator:
        return False

    expected_username = os.environ.get("APP_USERNAME", "").strip()
    if expected_username and not hmac.compare_digest(username, expected_username):
        return False

    return hmac.compare_digest(given_password, password)


def auth_required_response(handler: SimpleHTTPRequestHandler) -> None:
    body = b"Authentication required"
    handler.send_response(401)
    handler.send_header("WWW-Authenticate", 'Basic realm="Position Sizing Calculator"')
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


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


def load_kis_config() -> dict | None:
    config: dict[str, str] = {
        "app_key": os.environ.get("KIS_APP_KEY", "").strip(),
        "app_secret": os.environ.get("KIS_APP_SECRET", "").strip(),
        "env": os.environ.get("KIS_ENV", "prod").strip().lower() or "prod",
    }

    if KIS_CONFIG_FILE.is_file():
        try:
            local_config = json.loads(KIS_CONFIG_FILE.read_text(encoding="utf-8"))
            config["app_key"] = local_config.get("app_key") or local_config.get("appkey") or config["app_key"]
            config["app_secret"] = (
                local_config.get("app_secret")
                or local_config.get("appsecret")
                or local_config.get("secretkey")
                or config["app_secret"]
            )
            config["env"] = (local_config.get("env") or config["env"]).lower()
        except (OSError, json.JSONDecodeError):
            return None

    if not config["app_key"] or not config["app_secret"]:
        return None
    if config["env"] not in KIS_REST_BASE:
        config["env"] = "prod"
    return config


def kis_approval_key(config: dict) -> str:
    cache_key = f"{config['env']}:{config['app_key']}"
    cached = _kis_approval_cache.get(cache_key)
    if cached and time.time() - cached[0] < 60 * 60 * 20:
        return cached[1]

    data = http_json_post(
        f"{KIS_REST_BASE[config['env']]}/oauth2/Approval",
        {
            "grant_type": "client_credentials",
            "appkey": config["app_key"],
            "secretkey": config["app_secret"],
        },
    )
    approval_key = data.get("approval_key")
    if not approval_key:
        raise ValueError(data.get("msg1") or "한국투자 WebSocket 접속키 발급에 실패했습니다.")

    _kis_approval_cache[cache_key] = (time.time(), approval_key)
    return approval_key


async def kis_realtime_tick(config: dict, code: str, timeout: float = 2.8) -> dict:
    try:
        import websockets
    except ImportError as exc:
        raise ValueError("websockets 패키지가 설치되어 있지 않습니다.") from exc

    approval_key = kis_approval_key(config)
    tr_id = "H0NXCNT0"
    subscribe_message = {
        "header": {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8",
        },
        "body": {"input": {"tr_id": tr_id, "tr_key": code}},
    }

    async with websockets.connect(KIS_WS_BASE[config["env"]], ping_interval=None) as ws:
        await ws.send(json.dumps(subscribe_message))
        end_at = asyncio.get_running_loop().time() + timeout

        while True:
            remaining = end_at - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("한국투자 NXT 실시간 시세 수신 시간이 초과되었습니다.")

            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            if not raw:
                continue

            if raw[0] in {"0", "1"}:
                parts = raw.split("|")
                if len(parts) < 4 or parts[1] != tr_id:
                    continue
                values = parts[3].split("^")
                row = dict(zip(KIS_NXT_CCN_COLUMNS, values))
                if row.get("MKSC_SHRN_ISCD") == code:
                    return row
                continue

            message = json.loads(raw)
            header = message.get("header", {})
            if header.get("tr_id") == "PINGPONG":
                await ws.pong(raw)
                continue
            body = message.get("body") or {}
            if body.get("rt_cd") == "1":
                raise ValueError(body.get("msg1") or "한국투자 WebSocket 구독에 실패했습니다.")


def fetch_kis_nxt_quote(code: str) -> dict:
    config = load_kis_config()
    if not config:
        raise ValueError("한국투자 API 설정이 없습니다.")

    row = asyncio.run(kis_realtime_tick(config, code))
    price = parse_price(row.get("STCK_PRPR"))
    day_low = parse_price(row.get("STCK_LWPR"))
    day_high = parse_price(row.get("STCK_HGPR"))
    previous_close = None
    previous_diff = parse_price(row.get("PRDY_VRSS"))
    if price is not None and previous_diff is not None:
        sign = row.get("PRDY_VRSS_SIGN")
        previous_close = price - previous_diff if sign in {"1", "2"} else price + previous_diff

    if price is None or day_low is None or day_high is None:
        raise ValueError("한국투자 NXT 실시간 가격 데이터를 찾을 수 없습니다.")

    return {
        "price": price,
        "dayLow": day_low,
        "dayHigh": day_high,
        "previousClose": previous_close,
        "timestamp": f"{row.get('BSOP_DATE', '')} {row.get('STCK_CNTG_HOUR', '')}".strip(),
        "source": "KIS/NXT",
        "venue": "NXT",
        "realtime": True,
    }


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
        venues["NXT"] = fetch_kis_nxt_quote(code)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
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


def latest_chart_price(symbol: str) -> tuple[float, int | None]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=1d&interval=1d"
    data = http_json(url)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError("환율 데이터를 찾을 수 없습니다.")

    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    timestamp = meta.get("regularMarketTime")
    if not price:
        close_values = (
            (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        )
        price = next((value for value in reversed(close_values) if value is not None), None)
    if not price:
        raise ValueError("환율 데이터를 찾을 수 없습니다.")
    return float(price), timestamp


def fallback_krw_rate(currency: str) -> dict:
    data = http_json("https://open.er-api.com/v6/latest/KRW")
    rates = data.get("rates", {})
    rate = rates.get(currency)
    if not rate:
        raise ValueError("환율 데이터를 찾을 수 없습니다.")

    krw_per_unit = 1 / float(rate)
    return {
        "from": "KRW",
        "to": currency,
        "rate": float(rate),
        "krwPerUnit": krw_per_unit,
        "source": "open.er-api.com",
        "timestamp": data.get("time_last_update_utc"),
    }


def fetch_krw_rate(currency: str) -> dict:
    currency = currency.upper()
    if currency == "KRW":
        return {
            "from": "KRW",
            "to": "KRW",
            "rate": 1,
            "krwPerUnit": 1,
            "source": "KRW",
            "timestamp": None,
        }

    cached = _fx_cache.get(currency)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    try:
        symbol = FX_SYMBOLS.get(currency)
        if not symbol:
            raise ValueError("Yahoo 환율 심볼이 없습니다.")
        krw_per_unit, timestamp = latest_chart_price(symbol)
        payload = {
            "from": "KRW",
            "to": currency,
            "rate": 1 / krw_per_unit,
            "krwPerUnit": krw_per_unit,
            "source": "Yahoo Finance",
            "timestamp": timestamp,
        }
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        payload = fallback_krw_rate(currency)

    _fx_cache[currency] = (time.time(), payload)
    return payload


def convert_krw(amount: float, currency: str) -> dict:
    fx = fetch_krw_rate(currency)
    converted = amount * fx["rate"]
    return {**fx, "amount": amount, "convertedAmount": converted}


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
        if not is_authorized(self.headers):
            return auth_required_response(self)

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

        if parsed.path == "/api/fx":
            params = parse_qs(parsed.query)
            currency = ((params.get("to") or ["KRW"])[0] or "KRW").upper()
            amount = parse_price((params.get("amount") or ["0"])[0]) or 0
            try:
                return json_response(self, 200, convert_krw(amount, currency))
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
