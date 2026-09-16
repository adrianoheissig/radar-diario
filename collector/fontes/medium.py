"""Medium: os itens mais recentes de cada tag, com o texto completo quando disponível.

O feed de tag só traz um trecho. O texto completo vem do feed do autor ou da
publicação (content:encoded), localizando o post pelo guid. Artigos exclusivos
para membros e posts que já saíram do feed ficam só com o trecho.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from collector import config
from collector.comum import ColetaErro, Resultado, baixar_feed, data_da_entrada, limpar_url, texto_de_html
from collector.html_limpo import conteudo_da_entrada, limpar_conteudo, minutos_leitura


def coletar(tags: list[str] | None = None, por_tag: int | None = None) -> Resultado:
    tags = tags or config.MEDIUM_TAGS
    por_tag = por_tag or config.MEDIUM_POR_TAG
    itens, avisos, vistos = [], [], set()

    for tag in tags:
        url = config.MEDIUM_FEED_URL.format(tag=quote(tag.lower()))
        try:
            feed = baixar_feed(url)
        except Exception as exc:
            avisos.append(f"tag {tag}: {exc}")
            continue

        entradas = sorted(feed.entries, key=lambda e: data_da_entrada(e) or "", reverse=True)
        da_tag = 0
        for entrada in entradas:
            if da_tag >= por_tag:
                break
            link = limpar_url(entrada.get("link", ""))
            # o guid (medium.com/p/<id>) é estável; o link muda entre perfil e publicação
            chave = entrada.get("id") or link
            if not link or chave in vistos:
                continue
            vistos.add(chave)
            itens.append(item_do_feed_de_tag(entrada, tag, link))
            da_tag += 1

    if not itens:
        raise ColetaErro("nenhum item obtido" + (f": {'; '.join(avisos)}" if avisos else ""))

    if config.MEDIUM_TEXTO_COMPLETO:
        cache: dict[str, object] = {}
        for item in itens:
            try:
                item["conteudo_html"] = texto_completo(item, cache)
            except Exception as exc:
                avisos.append(f"texto completo de '{item['titulo'][:40]}': {exc}")
            item["leitura_min"] = minutos_leitura(item["conteudo_html"])

    itens.sort(key=lambda item: item["publicado_em"] or "", reverse=True)
    for item in itens:
        del item["_guid"]
    return Resultado(itens, origem="rss", avisos=avisos)


def item_do_feed_de_tag(entrada, tag: str, link: str) -> dict:
    soup = BeautifulSoup(entrada.get("summary", ""), "html.parser")
    trecho = soup.select_one(".medium-feed-snippet")
    imagem = soup.select_one(".medium-feed-image img[src]")
    return {
        "titulo": entrada.get("title", "").strip(),
        "link": link,
        "autor": entrada.get("author") or None,
        "tag": tag,
        "publicado_em": data_da_entrada(entrada),
        "resumo": texto_de_html(str(trecho)) if trecho else None,
        "imagem": imagem["src"] if imagem else None,
        "conteudo_html": None,
        "leitura_min": None,
        "_guid": entrada.get("id"),
    }


def feed_de_origem(link: str) -> str | None:
    """Feed do autor/publicação a partir do link do post."""
    partes = urlsplit(link)
    host = partes.netloc.lower()
    caminho = [p for p in partes.path.split("/") if p]
    if host in ("medium.com", "www.medium.com"):
        # medium.com/@autor/slug ou medium.com/publicacao/slug
        return f"https://medium.com/feed/{caminho[0]}" if len(caminho) >= 2 else None
    # autor.medium.com/slug ou domínio próprio de publicação
    return f"https://{host}/feed"


def texto_completo(item: dict, cache: dict) -> str | None:
    url = feed_de_origem(item["link"])
    if not url or not item.get("_guid"):
        return None
    if url not in cache:
        cache[url] = baixar_feed(url)
    entrada = next((e for e in cache[url].entries if e.get("id") == item["_guid"]), None)
    if entrada is None:
        return None
    return limpar_conteudo(conteudo_da_entrada(entrada), item["link"])
