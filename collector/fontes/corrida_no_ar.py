"""Corrida no Ar: última publicação via feed RSS, com scraping da home como fallback."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector import config
from collector.comum import (
    ColetaErro,
    Resultado,
    baixar_feed,
    data_da_entrada,
    get,
    iso,
    limpar_url,
    texto_de_html,
    truncar,
)

_RODAPE_WORDPRESS = re.compile(
    r"\s*(The post|O post)\b.*?(appeared first on|first appeared on|apareceu primeiro em)\b.*$", re.I | re.S
)


def coletar() -> Resultado:
    base = config.CORRIDA_NO_AR_URL.rstrip("/")
    avisos = []

    for caminho in config.CORRIDA_NO_AR_FEED_PATHS:
        post = _tentar_feed(base + caminho, avisos, rotulo=caminho)
        if post:
            return Resultado(post, origem=f"feed {caminho}", avisos=avisos)

    home = get(base + "/").text
    feed_descoberto = descobrir_feed(home, base)
    if feed_descoberto:
        post = _tentar_feed(feed_descoberto, avisos, rotulo=feed_descoberto)
        if post:
            return Resultado(post, origem=f"feed {feed_descoberto}", avisos=avisos)

    post = extrair_primeiro_post(home, base)
    if not post:
        raise ColetaErro("nenhum post encontrado (feed e scraping): " + "; ".join(avisos))
    return Resultado(post, origem="scraping home", avisos=avisos)


def _tentar_feed(url: str, avisos: list[str], rotulo: str) -> dict | None:
    try:
        feed = baixar_feed(url)
    except Exception as exc:
        avisos.append(f"{rotulo}: {exc}")
        return None
    if not feed.entries:
        avisos.append(f"{rotulo}: feed sem itens")
        return None
    return post_do_feed(feed.entries)


def post_do_feed(entradas) -> dict:
    entrada = max(entradas, key=lambda e: data_da_entrada(e) or "")
    return {
        "titulo": entrada.get("title", "").strip(),
        "link": limpar_url(entrada.get("link", "")),
        "resumo": limpar_resumo(entrada.get("summary", "")),
        "publicado_em": data_da_entrada(entrada),
    }


def limpar_resumo(html: str) -> str:
    texto = _RODAPE_WORDPRESS.sub("", texto_de_html(html))
    return truncar(texto, config.CORRIDA_NO_AR_RESUMO_MAX)


def descobrir_feed(html: str, base: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find(
        "link", rel="alternate", type=re.compile(r"application/(rss|atom)\+xml"), href=True
    )
    return urljoin(base + "/", link["href"]) if link else None


def extrair_primeiro_post(html: str, base: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for artigo in soup.find_all("article"):
        if artigo.find("article"):  # ignora o <article> da própria página que envolve a grade
            continue
        ancora = artigo.select_one("h1 a[href], h2 a[href], h3 a[href]")
        if not ancora:
            continue
        horario = artigo.select_one("time[datetime]")
        resumo = artigo.select_one(".uagb-post__excerpt, .entry-summary, .excerpt, p")
        publicado_em = None
        if horario:
            try:
                publicado_em = iso(datetime.fromisoformat(horario["datetime"]))
            except ValueError:
                pass
        return {
            "titulo": ancora.get_text(" ", strip=True),
            "link": limpar_url(urljoin(base + "/", ancora["href"])),
            "resumo": limpar_resumo(str(resumo)) if resumo else "",
            "publicado_em": publicado_em,
        }
    return None
