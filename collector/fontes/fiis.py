"""Cotações dos FIIs: brapi.dev (com BRAPI_TOKEN) e Yahoo Finance como fallback.

Variações calculadas a partir do último pregão (a coleta roda antes da abertura):
- dia:    variação do último pregão;
- semana: preço vs. último fechamento antes da segunda-feira da semana do último pregão;
- mês:    preço vs. último fechamento antes do dia 1º do mês do último pregão.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

from collector import config
from collector.comum import TZ, ColetaErro, Resultado, arredondar, get, iso, sessao

_TOKEN_VALIDO = re.compile(r"[A-Za-z0-9._~+/=-]+")
# histórico suficiente para cobrir o fechamento do mês anterior; planos que não
# liberam 3 meses caem para 1 mês e, por fim, só a cotação
_RANGES_BRAPI = ("3mo", "1mo", None)


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
    resultado = None
    for faixa in _RANGES_BRAPI:
        params = {"range": faixa, "interval": "1d"} if faixa else {}
        try:
            resultado = _brapi_get(ticker, token, params)
            break
        except BrapiAutenticacao:
            raise
        except ColetaErro:
            if faixa is None:
                raise

    preco = resultado.get("regularMarketPrice")
    if preco is None:
        raise ColetaErro("resposta sem regularMarketPrice")

    serie = [
        (p["date"], p["close"])
        for p in resultado.get("historicalDataPrice") or []
        if p.get("date") and p.get("close") is not None
    ]
    cotado_em = _parse_iso(resultado.get("regularMarketTime"))
    semana, mes = variacoes_semana_mes(serie, preco, _referencia(cotado_em, serie))
    return _montar(
        ticker,
        preco=preco,
        variacao_dia=resultado.get("regularMarketChangePercent"),
        variacao_semana=semana,
        variacao_mes=mes,
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
        params={"range": "3mo", "interval": "1d"},
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

    semana, mes = variacoes_semana_mes(serie, preco, _referencia(cotado_em, serie))
    return _montar(
        ticker,
        preco=preco,
        variacao_dia=variacao_dia,
        variacao_semana=semana,
        variacao_mes=mes,
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


def variacoes_semana_mes(
    serie: list[tuple[int, float]], preco: float, referencia: date | None
) -> tuple[float | None, float | None]:
    """(semana, mês) em %, relativos à semana e ao mês da data do último pregão."""
    if not serie or referencia is None:
        return None, None
    pontos = sorted((_dia_sp(ts), fechamento) for ts, fechamento in serie)
    inicio_semana = referencia - timedelta(days=referencia.weekday())
    inicio_mes = referencia.replace(day=1)
    return _variacao_desde(pontos, preco, inicio_semana), _variacao_desde(pontos, preco, inicio_mes)


def _variacao_desde(pontos: list[tuple[date, float]], preco: float, inicio: date) -> float | None:
    # série que não alcança o período anterior (histórico curto) não gera número
    anteriores = [fechamento for dia, fechamento in pontos if dia < inicio]
    if not anteriores or not anteriores[-1]:
        return None
    return (preco / anteriores[-1] - 1) * 100


def _dia_sp(ts: int) -> date:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(TZ).date()


def _referencia(cotado_em: datetime | None, serie) -> date | None:
    if cotado_em is not None:
        return cotado_em.astimezone(TZ).date()
    return _dia_sp(max(ts for ts, _ in serie)) if serie else None


def _parse_iso(valor) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None


def _montar(ticker, *, preco, variacao_dia, variacao_semana, variacao_mes, cotado_em, fonte) -> dict:
    return {
        "ticker": ticker,
        "preco": arredondar(preco),
        "variacao_dia_pct": arredondar(variacao_dia),
        "variacao_semana_pct": arredondar(variacao_semana),
        "variacao_mes_pct": arredondar(variacao_mes),
        "cotado_em": iso(cotado_em) if cotado_em else None,
        "fonte": fonte,
    }


def _cotacao_vazia(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "preco": None,
        "variacao_dia_pct": None,
        "variacao_semana_pct": None,
        "variacao_mes_pct": None,
        "cotado_em": None,
        "fonte": None,
    }
