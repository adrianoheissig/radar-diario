"""Cotações dos FIIs: brapi.dev (com BRAPI_TOKEN) e Yahoo Finance como fallback."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from collector import config
from collector.comum import ColetaErro, Resultado, arredondar, get, iso, sessao

_DIA = 86_400
_TOKEN_VALIDO = re.compile(r"[A-Za-z0-9._~+/=-]+")
_TOLERANCIA_30D = 7 * _DIA  # aceita série que começa até 7 dias depois do alvo


class BrapiAutenticacao(ColetaErro):
    """Token ausente/inválido: não adianta tentar os demais tickers na brapi."""


def coletar(tickers: list[str] | None = None) -> Resultado:
    tickers = tickers or config.FIIS
    token = os.environ.get("BRAPI_TOKEN", "").strip() or None
    avisos = []
    brapi_ativa = True
    if not token:
        avisos.append("BRAPI_TOKEN não definido: brapi sem token só atende ativos de teste")
    elif not _TOKEN_VALIDO.fullmatch(token):
        # ex.: secret cadastrado com texto colado junto (espaços, quebras de linha)
        avisos.append("BRAPI_TOKEN malformado (contém espaços ou caracteres inválidos): brapi ignorada")
        brapi_ativa = False
    cotacoes = []
    for ticker in tickers:
        cotacao, erros = None, []

        if brapi_ativa:
            try:
                cotacao = cotacao_brapi(ticker, token)
            except BrapiAutenticacao as exc:
                brapi_ativa = False
                avisos.append(f"brapi desativada nesta execução: {exc}")
            except Exception as exc:
                erros.append(f"brapi: {exc}")

        if cotacao is None and config.FII_FALLBACK_YAHOO:
            try:
                cotacao = cotacao_yahoo(ticker)
            except Exception as exc:
                erros.append(f"yahoo: {exc}")

        if erros:
            avisos.append(f"{ticker}: {'; '.join(erros)}")
        cotacoes.append(cotacao or _cotacao_vazia(ticker))

    if all(c["preco"] is None for c in cotacoes):
        raise ColetaErro("nenhuma cotação obtida: " + " | ".join(avisos))

    origens = sorted({c["fonte"] for c in cotacoes if c["fonte"]})
    return Resultado(cotacoes, origem="+".join(origens), avisos=avisos)


# ---------------------------------------------------------------- brapi


def cotacao_brapi(ticker: str, token: str | None) -> dict:
    try:
        resultado = _brapi_get(ticker, token, {"range": "1mo", "interval": "1d"})
    except BrapiAutenticacao:
        raise
    except ColetaErro:
        # alguns planos não liberam histórico: tenta só a cotação
        resultado = _brapi_get(ticker, token, {})

    preco = resultado.get("regularMarketPrice")
    if preco is None:
        raise ColetaErro("resposta sem regularMarketPrice")

    serie = [
        (p["date"], p["close"])
        for p in resultado.get("historicalDataPrice") or []
        if p.get("date") and p.get("close") is not None
    ]
    cotado_em = _parse_iso(resultado.get("regularMarketTime"))
    return _montar(
        ticker,
        preco=preco,
        variacao_dia=resultado.get("regularMarketChangePercent"),
        variacao_30d=variacao_periodo(serie, preco, _referencia(cotado_em, serie)),
        cotado_em=cotado_em,
        fonte="brapi",
    )


def _brapi_get(ticker: str, token: str | None, params: dict) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resposta = sessao.get(
        config.BRAPI_URL.format(ticker=ticker),
        params=params,
        headers=headers,
        timeout=config.HTTP_TIMEOUT,
    )
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}

    if resposta.ok and dados.get("results"):
        return dados["results"][0]

    mensagem = dados.get("message") or f"HTTP {resposta.status_code}"
    codigo = str(dados.get("code") or "").upper()
    if resposta.status_code == 401 or "TOKEN" in codigo:
        raise BrapiAutenticacao(mensagem)
    raise ColetaErro(f"{mensagem} (HTTP {resposta.status_code})")


# ---------------------------------------------------------------- Yahoo


def cotacao_yahoo(ticker: str) -> dict:
    dados = get(
        config.YAHOO_CHART_URL.format(ticker=ticker),
        params={"range": "2mo", "interval": "1d"},
        headers={"User-Agent": config.YAHOO_USER_AGENT},
    ).json()
    chart = dados.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise ColetaErro(f"resposta inválida: {chart.get('error')}")

    resultado = chart["result"][0]
    meta = resultado["meta"]
    preco = meta.get("regularMarketPrice")
    if preco is None:
        raise ColetaErro("resposta sem regularMarketPrice")

    fechamentos = (resultado.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    serie = [(ts, c) for ts, c in zip(resultado.get("timestamp") or [], fechamentos) if c is not None]
    momento = meta.get("regularMarketTime")
    cotado_em = datetime.fromtimestamp(momento, tz=timezone.utc) if momento else None

    variacao_dia = meta.get("regularMarketChangePercent")
    if variacao_dia is None:
        variacao_dia = _variacao_dia_pela_serie(serie, preco, cotado_em)

    return _montar(
        ticker,
        preco=preco,
        variacao_dia=variacao_dia,
        variacao_30d=variacao_periodo(serie, preco, _referencia(cotado_em, serie)),
        cotado_em=cotado_em,
        fonte="yahoo",
    )


def _variacao_dia_pela_serie(serie, preco, cotado_em) -> float | None:
    if not serie or cotado_em is None:
        return None
    dia_cotacao = iso(cotado_em)[:10]
    anteriores = [c for ts, c in serie if iso(datetime.fromtimestamp(ts, tz=timezone.utc))[:10] < dia_cotacao]
    return (preco / anteriores[-1] - 1) * 100 if anteriores and anteriores[-1] else None


# ---------------------------------------------------------------- cálculo


def variacao_periodo(serie: list[tuple[int, float]], preco: float, referencia_ts: int | None, dias: int = 30) -> float | None:
    """Variação % entre o último fechamento de ~`dias` atrás e o preço atual."""
    if not serie or referencia_ts is None:
        return None
    serie = sorted(serie)
    alvo = referencia_ts - dias * _DIA
    anteriores = [c for ts, c in serie if ts <= alvo]
    if anteriores:
        base = anteriores[-1]
    elif serie[0][0] - alvo <= _TOLERANCIA_30D:
        base = serie[0][1]
    else:
        return None
    return (preco / base - 1) * 100 if base else None


def _referencia(cotado_em: datetime | None, serie) -> int | None:
    if cotado_em is not None:
        return int(cotado_em.timestamp())
    return max(ts for ts, _ in serie) if serie else None


def _parse_iso(valor) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None


def _montar(ticker, *, preco, variacao_dia, variacao_30d, cotado_em, fonte) -> dict:
    return {
        "ticker": ticker,
        "preco": arredondar(preco),
        "variacao_dia_pct": arredondar(variacao_dia),
        "variacao_30d_pct": arredondar(variacao_30d),
        "cotado_em": iso(cotado_em) if cotado_em else None,
        "fonte": fonte,
    }


def _cotacao_vazia(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "preco": None,
        "variacao_dia_pct": None,
        "variacao_30d_pct": None,
        "cotado_em": None,
        "fonte": None,
    }
