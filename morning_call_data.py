
from datetime import datetime, timezone
import urllib.request
import urllib.error

# ------------------------------------------------------------------
# CONFIGURAÇÃO DE ATIVOS
# ------------------------------------------------------------------

YAHOO_TICKERS = {
    # Índices e Bolsas
    "ibovespa":      "^BVSP",
    "sp500":         "^GSPC",
    "nasdaq":        "^IXIC",
    "dow_jones":     "^DJI",
    "vix":           "^VIX",
    "ewz":           "EWZ",

    # Câmbio
    "usdbrl":        "BRL=X",
    "dxy":           "DX-Y.NYB",

    # Juros EUA
    "us_13w":        "^IRX",
    "us_5y":         "^FVX",
    "us_10y":        "^TNX",

    # Commodities (via futuros Yahoo)
    "brent":         "BZ=F",
    "gold":          "GC=F",
    "silver":        "SI=F",
    "iron_ore":      "TIO=F",

    # ADRs brasileiras
    "petrobras":     "PBR",
    "vale":          "VALE",
    "itau":          "ITUB",
    "bradesco":      "BBD",
    "ambev":         "ABEV",
    "eletrobras":    "EBR",
    "gerdau":        "GGB",
    "csn":           "SID",
}

COINGECKO_IDS = {
    "bitcoin":  "bitcoin",
    "ethereum": "ethereum",
    "xrp":      "ripple",
}

USER_AGENT = "Mozilla/5.0 (compatible; MorningCallBot/1.0)"


# ------------------------------------------------------------------
# FUNÇÕES DE COLETA
# ------------------------------------------------------------------

def fetch_yahoo(ticker: str, retries: int = 2, timeout: int = 8):
    """Busca preço e variação diária de um ticker no Yahoo Finance."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range=2d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            result = data["chart"]["result"][0]
            meta = result["meta"]

            price = meta.get("regularMarketPrice")
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

            if price is None or prev_close is None:
                return {"status": "unavailable", "reason": "campos ausentes"}

            change_pct = ((price - prev_close) / prev_close) * 100

            return {
                "status": "ok",
                "price": round(price, 4),
                "change_pct": round(change_pct, 2),
                "currency": meta.get("currency"),
                "market_state": meta.get("marketState"),
            }

        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                IndexError, TypeError, json.JSONDecodeError) as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            return {"status": "unavailable", "reason": str(e)}

    return {"status": "unavailable", "reason": "esgotadas as tentativas"}


def fetch_coingecko_batch(ids: list, retries: int = 2, timeout: int = 8):
    """Busca preço e variação 24h de várias criptos em uma única chamada."""
    ids_param = ",".join(ids)
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids_param}&vs_currencies=usd&include_24hr_change=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError) as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            return {}

    return {}


# ------------------------------------------------------------------
# COLETA PRINCIPAL
# ------------------------------------------------------------------

def collect_all():
    results = {}

    print("Coletando dados do Yahoo Finance...")
    for key, ticker in YAHOO_TICKERS.items():
        print(f"  -> {key} ({ticker})")
        results[key] = fetch_yahoo(ticker)
        results[key]["ticker"] = ticker
        time.sleep(0.4)  # evita bloqueio por rate limit

    print("Coletando dados do CoinGecko...")
    cg_data = fetch_coingecko_batch(list(COINGECKO_IDS.values()))

    for key, cg_id in COINGECKO_IDS.items():
        entry = cg_data.get(cg_id)
        if entry and "usd" in entry:
            results[key] = {
                "status": "ok",
                "price": entry["usd"],
                "change_pct": round(entry.get("usd_24h_change", 0), 2),
                "currency": "USD",
                "ticker": f"{cg_id.upper()}-USD",
            }
        else:
            results[key] = {
                "status": "unavailable",
                "reason": "sem resposta do CoinGecko",
                "ticker": f"{cg_id.upper()}-USD",
            }

    return results


def build_payload():
    data = collect_all()

    ok_count = sum(1 for v in data.values() if v.get("status") == "ok")
    total = len(data)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": f"{ok_count}/{total}",
        "data": data,
    }
    return payload


# ------------------------------------------------------------------
# EXECUÇÃO
# ------------------------------------------------------------------

if __name__ == "__main__":
    payload = build_payload()

    with open("morning_call_data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("\nConcluído.")
    print(f"Cobertura: {payload['coverage']}")
    print("Arquivo gerado: morning_call_data.json")

    # Log de falhas para diagnóstico rápido
    falhas = [k for k, v in payload["data"].items() if v.get("status") != "ok"]
    if falhas:
        print("\nAtivos sem cotação nesta execução:")
        for f_key in falhas:
            reason = payload["data"][f_key].get("reason", "desconhecido")
            print(f"  - {f_key}: {reason}")
