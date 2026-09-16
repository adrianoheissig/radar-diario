"""Utilidades compartilhadas pelas fontes: HTTP, datas, feeds e limpeza de texto."""

from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from collector import config

TZ = ZoneInfo(config.TIMEZONE)


class ColetaErro(Exception):
    """Falha esperada de coleta (fonte fora do ar, formato mudou etc.)."""


@dataclass
class Resultado:
    dados: Any
    origem: str
    avisos: list[str] = field(default_factory=list)


def _criar_sessao() -> requests.Session:
    sessao = requests.Session()
    sessao.headers.update(
        {
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
    )
    retry = Retry(
        total=2,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=False,
    )
    adaptador = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adaptador)
    sessao.mount("http://", adaptador)
    return sessao


sessao = _criar_sessao()


def get(url: str, **kwargs) -> requests.Response:
    resposta = sessao.get(url, timeout=config.HTTP_TIMEOUT, **kwargs)
    resposta.raise_for_status()
    return resposta


def agora() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def struct_time_para_iso(st: time.struct_time) -> str:
    return iso(datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc))


def data_da_entrada(entrada) -> str | None:
    for chave in ("published_parsed", "updated_parsed"):
        if entrada.get(chave):
            return struct_time_para_iso(entrada[chave])
    return None


def baixar_feed(url: str):
    feed = feedparser.parse(get(url).content)
    if feed.bozo and not feed.entries:
        raise ColetaErro(f"conteúdo não é um feed válido ({feed.get('bozo_exception')})")
    return feed


def limpar_url(url: str) -> str:
    """Remove parâmetros de rastreamento (utm_*, source) do link."""
    partes = urlsplit(url)
    query = [
        (k, v) for k, v in parse_qsl(partes.query) if not k.startswith("utm_") and k != "source"
    ]
    return urlunsplit(partes._replace(query=urlencode(query)))


def texto_de_html(html: str) -> str:
    texto = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", texto).strip()


def truncar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0]
    return corte.rstrip(" ,.;:") + "…"


def arredondar(valor: float | None, casas: int = 2) -> float | None:
    return None if valor is None else round(float(valor), casas)
