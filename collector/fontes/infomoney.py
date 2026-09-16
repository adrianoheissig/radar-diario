"""InfoMoney: manchetes recentes sobre FIIs com resumo, metadados e matéria completa.

Fonte principal: feed da tag "fundos-imobiliarios". Fallback: scraping da seção
"Últimas notícias sobre FIIs" da página de cotações (só título e link).
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector import config
from collector.comum import (
    ColetaErro,
    Resultado,
    baixar_feed,
    data_da_entrada,
    get,
    limpar_url,
    resumo_de_html,
)
from collector.html_limpo import conteudo_da_entrada, limpar_conteudo, minutos_leitura

_TITULO_SECAO = "últimas notícias sobre fiis"
_CATEGORIAS_GENERICAS = {"onde investir", "mercados", "fundos imobiliários"}


def coletar(limite: int | None = None) -> Resultado:
    limite = limite or config.INFOMONEY_LIMITE
    avisos = []

    try:
        feed = baixar_feed(config.INFOMONEY_FII_FEED)
        entradas = sorted(feed.entries, key=lambda e: data_da_entrada(e) or "", reverse=True)
        itens = [manchete_do_feed(e) for e in entradas if e.get("link")][:limite]
        if itens:
            return Resultado(itens, origem="rss tudo-sobre/fundos-imobiliarios")
        avisos.append("feed sem itens")
    except Exception as exc:
        avisos.append(f"feed: {exc}")

    itens = extrair_manchetes(get(config.INFOMONEY_FII_URL).text)
    if not itens:
        raise ColetaErro("nenhuma manchete encontrada: " + "; ".join(avisos))
    avisos.append("scraping: só título e link disponíveis")
    return Resultado(itens[:limite], origem="scraping cotacoes/b3/fii", avisos=avisos)


def manchete_do_feed(entrada) -> dict:
    link = limpar_url(entrada.get("link", ""))
    imagem = {}
    conteudo = limpar_conteudo(
        conteudo_da_entrada(entrada), link, ajuste=lambda soup: _extrair_imagem_destacada(soup, imagem)
    )
    categorias = [
        t["term"]
        for t in entrada.get("tags") or []
        if t.get("term") and t["term"].lower() not in _CATEGORIAS_GENERICAS
    ]
    return {
        "titulo": entrada.get("title", "").strip(),
        "link": link,
        "resumo": resumo_de_html(entrada.get("summary", ""), config.INFOMONEY_RESUMO_MAX),
        "autor": entrada.get("author") or None,
        "publicado_em": data_da_entrada(entrada),
        "categorias": categorias[: config.INFOMONEY_MAX_CATEGORIAS],
        "imagem": imagem.get("src"),
        "conteudo_html": conteudo,
        "leitura_min": minutos_leitura(conteudo),
    }


def _extrair_imagem_destacada(soup: BeautifulSoup, destino: dict) -> None:
    """Tira a imagem destacada do corpo (ela é exibida à parte, como miniatura)."""
    img = soup.select_one("img.wp-post-image")
    if img and img.get("src"):
        destino["src"] = img["src"]
        img.decompose()


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
            itens.append(
                {
                    "titulo": texto,
                    "link": link,
                    "resumo": None,
                    "autor": None,
                    "publicado_em": None,
                    "categorias": [],
                    "imagem": None,
                    "conteudo_html": None,
                    "leitura_min": None,
                }
            )
    return itens
