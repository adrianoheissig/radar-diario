"""InfoMoney: manchetes de capa com resumo, metadados e matéria completa.

A home define quais manchetes e em que ordem (o primeiro card é o destaque).
Os detalhes vêm da página de cada matéria: metatags (resumo, imagem, autor, data),
JSON-LD (categorias e seção) e o corpo em ``article.im-article``.
Se a capa não puder ser lida, usa o feed geral de últimas notícias.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

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
    resumo_de_html,
    truncar,
)
from collector.html_limpo import conteudo_da_entrada, limpar_conteudo, minutos_leitura

_CARDS_IGNORADOS = {
    "card-horizontal-infoproduct",
    "card-newsletter-banner",
    "card-skeleton-xs",
    "card-horizontal-skeleton",
}
_CATEGORIAS_GENERICAS = {"onde investir", "mercados", "reportagem", "últimas notícias"}
_LEIA_TAMBEM = re.compile(r"^\s*(leia também|leia mais|veja também)\b", re.I)
_LINK_PROMOCIONAL = re.compile(r"lps\.infomoney\.com\.br|premium-inscricao|/assine", re.I)
# o CDN de imagens do WordPress da InfoMoney redimensiona pela URL (1920px -> ~25 KB)
_TAMANHO_IMAGEM = "resize=640%2C360&quality=70&strip=all"


def coletar(limite: int | None = None) -> Resultado:
    limite = limite or config.INFOMONEY_LIMITE
    avisos = []

    try:
        capa = manchetes_da_capa(get(config.INFOMONEY_HOME_URL).text, limite)
    except Exception as exc:
        capa = []
        avisos.append(f"capa: {exc}")

    if capa:
        for item in capa:
            try:
                item.update(detalhes_da_materia(get(item["link"]).text, item["link"]))
            except Exception as exc:
                avisos.append(f"detalhes de '{item['titulo'][:40]}': {exc}")
        return Resultado(capa, origem="capa infomoney.com.br", avisos=avisos)

    avisos.append("capa sem manchetes: usando o feed geral")
    feed = baixar_feed(config.INFOMONEY_FEED_GERAL)
    entradas = sorted(feed.entries, key=lambda e: data_da_entrada(e) or "", reverse=True)
    itens = [manchete_do_feed(e) for e in entradas if e.get("link")][:limite]
    if not itens:
        raise ColetaErro("nenhuma manchete encontrada: " + "; ".join(avisos))
    return Resultado(itens, origem="rss feed geral", avisos=avisos)


# ---------------------------------------------------------------- capa


def manchetes_da_capa(html: str, limite: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    raiz = soup.find("main") or soup
    host = urlsplit(config.INFOMONEY_HOME_URL).netloc

    itens, vistos = [], set()
    for card in raiz.select('[data-ds-component^="card-"]'):
        componente = card["data-ds-component"]
        if componente in _CARDS_IGNORADOS:
            continue
        ancora = card.select_one("h1 a[href], h2 a[href], h3 a[href]")
        if not ancora:
            continue
        titulo = re.sub(r"\s+", " ", ancora.get_text(" ", strip=True)).strip()
        link = limpar_url(urljoin(config.INFOMONEY_HOME_URL, ancora["href"]))
        if not titulo or urlsplit(link).netloc != host or link in vistos:
            continue
        vistos.add(link)
        imagem = card.select_one("img[data-src], img[src]")
        itens.append(
            _item_vazio(
                titulo=titulo,
                link=link,
                destaque=componente == "card-headline",
                imagem=imagem_leve((imagem.get("data-src") or imagem.get("src")) if imagem else None),
            )
        )
        if len(itens) >= limite:
            break
    return itens


# ---------------------------------------------------------------- matéria


def detalhes_da_materia(html: str, link: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    ld = _news_article_ld(soup)

    detalhes = {
        "resumo": _meta(soup, "og:description") or _meta(soup, "description"),
        "imagem": imagem_leve(_meta(soup, "og:image")),
        "autor": _meta(soup, "author"),
        "publicado_em": _data_iso(_meta(soup, "article:published_time") or ld.get("datePublished")),
        "secao": _primeiro(ld.get("articleSection")),
        "categorias": [
            c for c in _lista(ld.get("keywords")) if c.lower() not in _CATEGORIAS_GENERICAS
        ][: config.INFOMONEY_MAX_CATEGORIAS],
    }
    if detalhes["resumo"]:
        detalhes["resumo"] = truncar(detalhes["resumo"], config.INFOMONEY_RESUMO_MAX)

    corpo = soup.select_one("article.im-article")
    conteudo = limpar_conteudo(str(corpo), link, ajuste=_limpar_materia) if corpo else None
    detalhes["conteudo_html"] = conteudo
    detalhes["leitura_min"] = minutos_leitura(conteudo)
    # não sobrescreve o que veio da capa com vazio
    return {k: v for k, v in detalhes.items() if v not in (None, "", [])}


def imagem_leve(url: str | None) -> str | None:
    """Versão reduzida das imagens hospedadas em wp-content/uploads; outras URLs ficam como estão."""
    if not url or url.startswith("data:"):
        return None
    partes = urlsplit(url)
    if "/wp-content/uploads/" not in partes.path:
        return url
    return partes._replace(query=_TAMANHO_IMAGEM, fragment="").geturl()


def _limpar_materia(soup: BeautifulSoup) -> None:
    for elemento in soup.select('[data-ds-component="ad"], .cta-middle, iframe, script, style'):
        elemento.decompose()
    for bloco in soup.find_all(["div", "p", "section", "aside"]):
        if bloco.parent is not None and _LEIA_TAMBEM.match(bloco.get_text(" ", strip=True)):
            bloco.decompose()
    # chamadas para assinatura/newsletter no meio do texto
    for link in soup.find_all("a", href=_LINK_PROMOCIONAL):
        if link.parent is None:
            continue
        bloco = link.find_parent(["li", "p"])
        (bloco or link).decompose()


def _meta(soup: BeautifulSoup, nome: str) -> str | None:
    tag = soup.find("meta", attrs={"property": nome}) or soup.find("meta", attrs={"name": nome})
    valor = (tag.get("content") or "").strip() if tag else ""
    return valor or None


def _news_article_ld(soup: BeautifulSoup) -> dict:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            dados = json.loads(script.string or "")
        except ValueError:
            continue
        nos = dados.get("@graph", [dados]) if isinstance(dados, dict) else dados
        for no in nos if isinstance(nos, list) else []:
            tipo = no.get("@type") if isinstance(no, dict) else None
            if tipo in ("NewsArticle", "Article") or (isinstance(tipo, list) and "NewsArticle" in tipo):
                return no
    return {}


def _lista(valor) -> list[str]:
    if isinstance(valor, str):
        return [v.strip() for v in valor.split(",") if v.strip()]
    return [str(v).strip() for v in valor or [] if str(v).strip()]


def _primeiro(valor) -> str | None:
    itens = _lista(valor)
    return itens[0] if itens else None


def _data_iso(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return iso(datetime.fromisoformat(valor.replace("Z", "+00:00")))
    except ValueError:
        return None


def _item_vazio(**campos) -> dict:
    item = {
        "titulo": None,
        "link": None,
        "destaque": False,
        "secao": None,
        "resumo": None,
        "autor": None,
        "publicado_em": None,
        "categorias": [],
        "imagem": None,
        "conteudo_html": None,
        "leitura_min": None,
    }
    item.update(campos)
    return item


# ---------------------------------------------------------------- fallback: feed geral


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
    return _item_vazio(
        titulo=entrada.get("title", "").strip(),
        link=link,
        resumo=resumo_de_html(entrada.get("summary", ""), config.INFOMONEY_RESUMO_MAX),
        autor=entrada.get("author") or None,
        publicado_em=data_da_entrada(entrada),
        categorias=categorias[: config.INFOMONEY_MAX_CATEGORIAS],
        imagem=imagem.get("src"),
        conteudo_html=conteudo,
        leitura_min=minutos_leitura(conteudo),
    )


def _extrair_imagem_destacada(soup: BeautifulSoup, destino: dict) -> None:
    """Tira a imagem destacada do corpo (ela é exibida à parte, como miniatura)."""
    img = soup.select_one("img.wp-post-image")
    if img and img.get("src"):
        destino["src"] = img["src"]
        img.decompose()
