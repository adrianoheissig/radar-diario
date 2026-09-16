"""InfoMoney: manchetes mais recentes sobre FIIs (feed da tag, com scraping da página como fallback)."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector import config
from collector.comum import ColetaErro, Resultado, baixar_feed, data_da_entrada, get, limpar_url

_TITULO_SECAO = "últimas notícias sobre fiis"


def coletar(limite: int | None = None) -> Resultado:
    limite = limite or config.INFOMONEY_LIMITE
    avisos = []

    try:
        feed = baixar_feed(config.INFOMONEY_FII_FEED)
        entradas = sorted(feed.entries, key=lambda e: data_da_entrada(e) or "", reverse=True)
        itens = [
            {"titulo": e.get("title", "").strip(), "link": limpar_url(e.get("link", ""))}
            for e in entradas
            if e.get("link")
        ]
        if itens:
            return Resultado(itens[:limite], origem="rss tudo-sobre/fundos-imobiliarios")
        avisos.append("feed sem itens")
    except Exception as exc:
        avisos.append(f"feed: {exc}")

    itens = extrair_manchetes(get(config.INFOMONEY_FII_URL).text)
    if not itens:
        raise ColetaErro("nenhuma manchete encontrada: " + "; ".join(avisos))
    return Resultado(itens[:limite], origem="scraping cotacoes/b3/fii", avisos=avisos)


def extrair_manchetes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    titulo = next(
        (h for h in soup.find_all(["h2", "h3"]) if _TITULO_SECAO in h.get_text(" ", strip=True).lower()),
        None,
    )
    if not titulo:
        return []
    secao = titulo.find_parent("section") or titulo.parent

    itens, vistos = [], set()
    for ancora in secao.select("h2 a[href], h3 a[href]"):
        link = limpar_url(urljoin(config.INFOMONEY_FII_URL, ancora["href"]))
        texto = ancora.get_text(" ", strip=True)
        if texto and link not in vistos:
            vistos.add(link)
            itens.append({"titulo": texto, "link": link})
    return itens
