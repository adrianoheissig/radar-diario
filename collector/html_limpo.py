"""Limpeza e sanitização do HTML completo vindo dos feeds.

O HTML é de terceiros e vai ser renderizado no painel, então passa por:
1. uma limpeza com BeautifulSoup (rodapés de feed, pixels de rastreamento,
   botões de compartilhamento, blocos vazios, URLs relativas);
2. uma allowlist estrita com nh3 (sem scripts, estilos, iframes ou atributos de evento).
O frontend ainda aplica DOMPurify antes de exibir.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from urllib.parse import urljoin

import nh3
from bs4 import BeautifulSoup

TAGS = {
    "p", "br", "hr", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "sup", "sub", "mark",
    "a", "ul", "ol", "li", "blockquote", "pre", "code",
    "figure", "figcaption", "img",
    "table", "thead", "tbody", "tr", "th", "td",
}
ATRIBUTOS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "th": {"colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
}

RODAPE_FEED = re.compile(
    r"^\s*(The post|O post)\b.*?(appeared first on|first appeared on|apareceu primeiro em)\b",
    re.I | re.S,
)
RODAPE_MEDIUM = re.compile(r"was originally published in .* on Medium", re.I | re.S)

_PALAVRA = re.compile(r"\w+")
_BLOCOS = ["p", "figure", "div", "li", "ul", "ol", "blockquote", "h2", "h3", "h4"]


def limpar_conteudo(
    html: str | None,
    base_url: str,
    ajuste: Callable[[BeautifulSoup], None] | None = None,
) -> str | None:
    """Devolve HTML seguro e enxuto, ou None se não sobrar texto."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    if ajuste:
        ajuste(soup)

    for p in soup.find_all(["p", "div"]):
        texto = p.get_text(" ", strip=True)
        if RODAPE_FEED.search(texto) or RODAPE_MEDIUM.search(texto):
            p.decompose()

    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        pixel = img.get("width") == "1" or img.get("height") == "1" or "/_/stat" in src
        if not src or pixel:
            img.decompose()
            continue
        img["src"] = urljoin(base_url, src)
        img["loading"] = "lazy"

    for a in soup.find_all("a", href=True):
        if "*" in a["href"]:  # e-mail mascarado por anti-spam: mantém só o texto
            a.unwrap()
            continue
        a["href"] = urljoin(base_url, a["href"])

    for titulo in soup.find_all("h1"):
        titulo.name = "h2"

    # remove blocos que ficaram vazios (embeds sem conteúdo, parágrafos de compartilhamento)
    for bloco in reversed(soup.find_all(_BLOCOS)):
        if not bloco.get_text(strip=True) and not bloco.find(["img", "hr", "br"]):
            bloco.decompose()

    limpo = nh3.clean(
        str(soup),
        tags=TAGS,
        attributes=ATRIBUTOS,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    ).strip()
    limpo = re.sub(r"(<br\s*/?>\s*){3,}", "<br><br>", limpo)
    limpo = re.sub(r">\s*\n\s*<", ">\n<", limpo)

    if not BeautifulSoup(limpo, "html.parser").get_text(strip=True):
        return None
    return limpo


def minutos_leitura(html: str | None, palavras_por_minuto: int = 220) -> int | None:
    if not html:
        return None
    palavras = len(_PALAVRA.findall(BeautifulSoup(html, "html.parser").get_text(" ")))
    return max(1, math.ceil(palavras / palavras_por_minuto))


def conteudo_da_entrada(entrada) -> str:
    """HTML completo de uma entrada do feedparser (content:encoded), se houver."""
    for bloco in entrada.get("content") or []:
        if bloco.get("value"):
            return bloco["value"]
    return ""
