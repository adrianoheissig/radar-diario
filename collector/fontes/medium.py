"""Medium: os itens mais recentes de cada tag, com o texto completo quando disponível.

O feed de tag só traz um trecho. O texto completo vem do feed do autor ou da
publicação (content:encoded), localizando o post pelo guid. Artigos exclusivos
para membros e posts que já saíram do feed não têm texto completo: com
MEDIUM_APENAS_TEXTO_COMPLETO eles são pulados e a tag segue para o próximo item.
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
    buscar_texto = config.MEDIUM_TEXTO_COMPLETO or config.MEDIUM_APENAS_TEXTO_COMPLETO
    itens, avisos, vistos = [], [], set()
    cache: dict[str, object] = {}

    for tag in tags:
        url = config.MEDIUM_FEED_URL.format(tag=quote(tag.lower()))
        try:
            feed = baixar_feed(url)
        except Exception as exc:
            avisos.append(f"tag {tag}: {exc}")
            continue

        entradas = sorted(feed.entries, key=lambda e: data_da_entrada(e) or "", reverse=True)
        da_tag = pulados = 0
        for entrada in entradas:
            if da_tag >= por_tag:
                break
            link = limpar_url(entrada.get("link", ""))
            # o guid (medium.com/p/<id>) é estável; o link muda entre perfil e publicação
            chave = entrada.get("id") or link
            if not link or chave in vistos:
                continue
            vistos.add(chave)
            item = item_do_feed_de_tag(entrada, tag, link)

            if buscar_texto:
                try:
                    item["conteudo_html"] = texto_completo(item, cache)
                except Exception as exc:
                    # no modo "só texto completo" a falha só faz o artigo ser pulado (contado abaixo)
                    if not config.MEDIUM_APENAS_TEXTO_COMPLETO:
                        avisos.append(f"texto completo de '{item['titulo'][:40]}': {exc}")
                item["leitura_min"] = minutos_leitura(item["conteudo_html"])
            if config.MEDIUM_APENAS_TEXTO_COMPLETO and not item["conteudo_html"]:
                pulados += 1
                continue

            del item["_guid"]
            itens.append(item)
            da_tag += 1

        if da_tag < por_tag:
            detalhe = f" ({pulados} sem texto completo pulados)" if pulados else ""
            avisos.append(f"tag {tag}: só {da_tag} de {por_tag} artigos{detalhe}")

    if not itens:
        raise ColetaErro("nenhum item obtido" + (f": {'; '.join(avisos)}" if avisos else ""))

    itens.sort(key=lambda item: item["publicado_em"] or "", reverse=True)
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
