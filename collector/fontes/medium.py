"""Medium: pega os itens mais recentes de cada tag e agrega ordenando por data."""

from __future__ import annotations

from urllib.parse import quote

from collector import config
from collector.comum import ColetaErro, Resultado, baixar_feed, data_da_entrada, limpar_url


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
            itens.append(
                {
                    "titulo": entrada.get("title", "").strip(),
                    "link": link,
                    "autor": entrada.get("author") or None,
                    "tag": tag,
                    "publicado_em": data_da_entrada(entrada),
                }
            )
            da_tag += 1

    if not itens:
        raise ColetaErro("nenhum item obtido" + (f": {'; '.join(avisos)}" if avisos else ""))

    itens.sort(key=lambda item: item["publicado_em"] or "", reverse=True)
    return Resultado(itens, origem="rss", avisos=avisos)
