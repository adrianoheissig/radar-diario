import json

import feedparser
import pytest

from collector import main
from collector.comum import ColetaErro, Resultado, limpar_url
from collector.fontes import corrida_no_ar, fiis, infomoney, medium

HTML_INFOMONEY = """
<section><h2>Mais lidas</h2><h2><a href="/mercados/nao-e-fii/">Fora da seção</a></h2></section>
<section>
  <div><h2 class="x">Últimas notícias sobre FIIs</h2></div>
  <div data-ds-component="card-sm"><h2><a href="https://www.infomoney.com.br/a/">Notícia &quot;A&quot;</a></h2></div>
  <div data-ds-component="card-sm"><h2><a href="/b/?utm_source=x">Notícia B</a></h2></div>
  <div data-ds-component="card-sm"><h2><a href="/b/">Notícia B duplicada</a></h2></div>
</section>
"""

HOME_CORRIDA = """
<article class="page"><div class="grid">
  <article class="uagb-post__inner-wrap">
    <h1 class="uagb-post__title"><a href="https://corridanoar.com/post-1/">Post 1</a></h1>
    <time datetime="2026-09-16T05:25:31-03:00">16 de setembro</time>
    <div class="uagb-post__excerpt"><p>Resumo do post 1.</p></div>
  </article>
  <article class="uagb-post__inner-wrap"><h1><a href="/post-2/">Post 2</a></h1></article>
</div></article>
"""

RSS_CORRIDA = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Antigo</title><link>https://corridanoar.com/antigo/</link>
  <pubDate>Mon, 14 Sep 2026 08:00:00 +0000</pubDate><description>velho</description></item>
<item><title>Novo</title><link>https://corridanoar.com/novo/?utm_source=rss&amp;utm_medium=rss</link>
  <pubDate>Wed, 16 Sep 2026 08:25:31 +0000</pubDate>
  <description><![CDATA[<img src="x.jpg"/><p>Texto do resumo.</p><p>The post <a href="#">Novo</a> first appeared on <a href="#">Corrida no Ar</a>.</p>]]></description></item>
</channel></rss>"""


def test_limpar_url_remove_rastreamento():
    url = "https://medium.com/@a/post-123?source=rss------claude-5&utm_medium=rss&id=7"
    assert limpar_url(url) == "https://medium.com/@a/post-123?id=7"


def test_infomoney_extrai_apenas_secao_de_fiis_sem_duplicatas():
    itens = infomoney.extrair_manchetes(HTML_INFOMONEY)
    assert itens == [
        {"titulo": 'Notícia "A"', "link": "https://www.infomoney.com.br/a/"},
        {"titulo": "Notícia B", "link": "https://www.infomoney.com.br/b/"},
    ]


def test_corrida_scraping_pega_primeiro_post_interno():
    post = corrida_no_ar.extrair_primeiro_post(HOME_CORRIDA, "https://corridanoar.com")
    assert post["titulo"] == "Post 1"
    assert post["link"] == "https://corridanoar.com/post-1/"
    assert post["resumo"] == "Resumo do post 1."
    assert post["publicado_em"] == "2026-09-16T05:25:31-03:00"


def test_corrida_feed_pega_mais_recente_e_limpa_rodape():
    post = corrida_no_ar.post_do_feed(feedparser.parse(RSS_CORRIDA).entries)
    assert post == {
        "titulo": "Novo",
        "link": "https://corridanoar.com/novo/",
        "resumo": "Texto do resumo.",
        "publicado_em": "2026-09-16T05:25:31-03:00",
    }


RSS_MEDIUM = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Mesmo post</title><link>https://blog.exemplo.com/post-abc123?source=rss</link><guid>https://medium.com/p/abc123</guid>
  <pubDate>Wed, 16 Sep 2026 16:00:00 GMT</pubDate></item>
<item><title>Mesmo post</title><link>https://medium.com/@autor/post-abc123?source=rss</link><guid>https://medium.com/p/abc123</guid>
  <pubDate>Wed, 16 Sep 2026 16:00:00 GMT</pubDate></item>
<item><title>Outro</title><link>https://medium.com/@autor/outro-def456</link><guid>https://medium.com/p/def456</guid>
  <pubDate>Wed, 16 Sep 2026 17:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_medium_deduplica_pelo_guid_e_ordena(monkeypatch):
    monkeypatch.setattr(medium, "baixar_feed", lambda url: feedparser.parse(RSS_MEDIUM))
    resultado = medium.coletar(tags=["a", "b"], por_tag=5)
    assert [i["titulo"] for i in resultado.dados] == ["Outro", "Mesmo post"]
    assert resultado.dados[1]["link"] == "https://blog.exemplo.com/post-abc123"
    assert resultado.dados[1]["tag"] == "a"


def test_medium_respeita_cota_por_tag(monkeypatch):
    feeds = {
        "muito": RSS_MEDIUM.replace("abc123", "m1").replace("def456", "m2"),
        "pouco": RSS_MEDIUM.replace("abc123", "p1").replace("def456", "p2"),
    }
    monkeypatch.setattr(medium, "baixar_feed", lambda url: feedparser.parse(feeds[url.rsplit("/", 1)[-1]]))
    resultado = medium.coletar(tags=["muito", "pouco"], por_tag=1)
    # cada tag contribui só com o seu item mais recente ("Outro", 17h)
    assert [(i["tag"], i["link"].rsplit("-", 1)[-1]) for i in resultado.dados] == [("muito", "m2"), ("pouco", "p2")]


def test_variacao_30d_usa_ultimo_fechamento_antes_do_alvo():
    dia = 86_400
    hoje = 1_789_600_000
    serie = [(hoje - 40 * dia, 90.0), (hoje - 31 * dia, 100.0), (hoje - 29 * dia, 105.0), (hoje, 110.0)]
    assert fiis.variacao_periodo(serie, 110.0, hoje) == pytest.approx(10.0)
    # série curta demais (começa 20 dias depois do alvo) não gera número
    assert fiis.variacao_periodo([(hoje - 10 * dia, 100.0)], 110.0, hoje) is None


def test_fiis_sem_token_cai_no_yahoo_e_desativa_brapi(monkeypatch):
    chamadas = {"brapi": 0}

    def brapi(ticker, token):
        chamadas["brapi"] += 1
        raise fiis.BrapiAutenticacao("Token de autenticação não fornecido")

    def yahoo(ticker):
        if ticker == "FALHA11":
            raise ColetaErro("fora do ar")
        return fiis._montar(ticker, preco=10, variacao_dia=1.234, variacao_30d=None, cotado_em=None, fonte="yahoo")

    monkeypatch.delenv("BRAPI_TOKEN", raising=False)
    monkeypatch.setattr(fiis, "cotacao_brapi", brapi)
    monkeypatch.setattr(fiis, "cotacao_yahoo", yahoo)

    resultado = fiis.coletar(["AAAA11", "FALHA11", "BBBB11"])
    assert chamadas["brapi"] == 1
    assert resultado.origem == "yahoo"
    assert [c["preco"] for c in resultado.dados] == [10.0, None, 10.0]
    assert resultado.dados[0]["variacao_dia_pct"] == 1.23
    assert any("FALHA11" in a for a in resultado.avisos)


def test_falha_de_uma_fonte_nao_derruba_as_outras(tmp_path, monkeypatch):
    def quebra():
        raise ColetaErro("site mudou")

    fontes = [
        ("fiis", lambda: Resultado([{"ticker": "KNRI11"}], origem="teste"), list),
        ("corrida_no_ar", quebra, lambda: None),
    ]
    resumo = main.montar_resumo(fontes)
    assert resumo["fiis"] == [{"ticker": "KNRI11"}]
    assert resumo["corrida_no_ar"] is None
    assert resumo["status"]["corrida_no_ar"]["ok"] is False
    assert "site mudou" in resumo["status"]["corrida_no_ar"]["erro"]

    (tmp_path / "resumo-2020-01-01.json").write_text("{}")
    (tmp_path / "outro.json").write_text("{}")
    main.salvar(resumo, tmp_path)
    indice = json.loads((tmp_path / "index.json").read_text())
    assert indice["datas"] == [resumo["data"], "2020-01-01"]
    assert json.loads((tmp_path / "latest.json").read_text()) == resumo


def test_main_nao_grava_se_todas_as_fontes_falharem(tmp_path, monkeypatch):
    def quebra():
        raise RuntimeError("offline")

    monkeypatch.setattr(main, "FONTES", [("fiis", quebra, list), ("medium", quebra, list)])
    assert main.main(["--data-dir", str(tmp_path)]) == 1
    assert list(tmp_path.iterdir()) == []
