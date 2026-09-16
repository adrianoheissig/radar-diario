import json

import feedparser
import pytest

from collector import main
from collector.comum import ColetaErro, Resultado, limpar_url
from collector.fontes import corrida_no_ar, fiis, infomoney, medium
from collector.html_limpo import limpar_conteudo, minutos_leitura

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

RSS_CORRIDA = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>x</title>
<item><title>Antigo</title><link>https://corridanoar.com/antigo/</link>
  <pubDate>Mon, 14 Sep 2026 08:00:00 +0000</pubDate><description>velho</description></item>
<item><title>Novo</title><link>https://corridanoar.com/novo/?utm_source=rss&amp;utm_medium=rss</link>
  <pubDate>Wed, 16 Sep 2026 08:25:31 +0000</pubDate>
  <description><![CDATA[<img src="x.jpg"/><p>Texto do resumo.</p><p>The post <a href="#">Novo</a> first appeared on <a href="#">Corrida no Ar</a>.</p>]]></description>
  <content:encoded><![CDATA[<img class="webfeedsFeaturedVisual" src="/mini.jpg" width="150"/><p>Parágrafo um.</p><h3>Seção</h3>
    <p>Fale <a href="mailto:co***@x.com">conosco</a>.</p>
    <p class="addtoany_share_save_container"><a href="https://www.addtoany.com/add_to/x"></a></p>
    <p>The post <a href="#">Novo</a> first appeared on <a href="#">Corrida no Ar</a>.</p>]]></content:encoded>
  <media:content url="https://corridanoar.com/grande.jpg" medium="image"/></item>
</channel></rss>"""


def test_limpar_url_remove_rastreamento():
    url = "https://medium.com/@a/post-123?source=rss------claude-5&utm_medium=rss&id=7"
    assert limpar_url(url) == "https://medium.com/@a/post-123?id=7"


def test_infomoney_extrai_apenas_secao_de_fiis_sem_duplicatas():
    itens = [{"titulo": i["titulo"], "link": i["link"]} for i in infomoney.extrair_manchetes(HTML_INFOMONEY)]
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


def test_corrida_feed_pega_mais_recente_com_conteudo_completo():
    post = corrida_no_ar.post_do_feed(feedparser.parse(RSS_CORRIDA).entries)
    assert post["titulo"] == "Novo"
    assert post["link"] == "https://corridanoar.com/novo/"
    assert post["resumo"] == "Texto do resumo."
    assert post["publicado_em"] == "2026-09-16T05:25:31-03:00"
    assert post["imagem"] == "https://corridanoar.com/grande.jpg"
    assert post["conteudo_html"] == "<p>Parágrafo um.</p><h3>Seção</h3>\n<p>Fale conosco.</p>"
    assert post["leitura_min"] == 1


def test_sanitizacao_remove_perigos_e_ruido():
    html = """<h1>T</h1><p onclick="x()" style="color:red">Oi <a href="/rel">link</a> <a href="javascript:alert(1)">js</a></p>
    <script>alert(1)</script><iframe src="https://evil.example"></iframe><style>p{}</style>
    <figure class="wp-block-embed"><div class="wp-block-embed__wrapper"></div></figure>
    <img src="https://medium.com/_/stat?event=x" width="1" height="1"><img data-src="/a.png" src="data:image/gif;base64,xx">
    <p>My story was originally published in Pub on Medium, where people are continuing the conversation.</p>"""
    limpo = limpar_conteudo(html, "https://site.com/post/")
    assert limpo == (
        '<h2>T</h2><p>Oi <a href="https://site.com/rel" rel="noopener noreferrer nofollow">link</a> '
        '<a rel="noopener noreferrer nofollow">js</a></p>\n<img loading="lazy" src="https://site.com/a.png">'
    )
    assert limpar_conteudo("<p> </p><script>x</script>", "https://s.com") is None
    assert minutos_leitura("<p>" + "palavra " * 500 + "</p>") == 3


RSS_MEDIUM = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Mesmo post</title><link>https://blog.exemplo.com/post-abc123?source=rss</link><guid>https://medium.com/p/abc123</guid>
  <pubDate>Wed, 16 Sep 2026 16:00:00 GMT</pubDate>
  <description><![CDATA[<div class="medium-feed-item"><p class="medium-feed-image"><a href="#"><img src="https://cdn/img.png"></a></p><p class="medium-feed-snippet">Trecho do post.</p></div>]]></description></item>
<item><title>Mesmo post</title><link>https://medium.com/@autor/post-abc123?source=rss</link><guid>https://medium.com/p/abc123</guid>
  <pubDate>Wed, 16 Sep 2026 16:00:00 GMT</pubDate></item>
<item><title>Outro</title><link>https://medium.com/@autor/outro-def456</link><guid>https://medium.com/p/def456</guid>
  <pubDate>Wed, 16 Sep 2026 17:00:00 GMT</pubDate></item>
</channel></rss>"""

RSS_AUTOR = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>autor</title>
<item><title>Outro</title><link>https://medium.com/@autor/outro-def456</link><guid>https://medium.com/p/def456</guid>
  <content:encoded><![CDATA[<p>Texto completo.</p><img src="https://medium.com/_/stat?event=post" width="1" height="1">]]></content:encoded></item>
</channel></rss>"""


def _feeds_falsos(monkeypatch, feeds):
    requisicoes = []

    def baixar(url):
        requisicoes.append(url)
        if url not in feeds:
            raise ColetaErro(f"404 {url}")
        return feedparser.parse(feeds[url])

    monkeypatch.setattr(medium, "baixar_feed", baixar)
    return requisicoes


def test_medium_deduplica_pelo_guid_e_ordena(monkeypatch):
    monkeypatch.setattr(medium.config, "MEDIUM_TEXTO_COMPLETO", False)
    _feeds_falsos(monkeypatch, {f"https://medium.com/feed/tag/{t}": RSS_MEDIUM for t in ("a", "b")})
    resultado = medium.coletar(tags=["a", "b"], por_tag=5)
    assert [i["titulo"] for i in resultado.dados] == ["Outro", "Mesmo post"]
    mesmo = resultado.dados[1]
    assert mesmo["link"] == "https://blog.exemplo.com/post-abc123"
    assert mesmo["tag"] == "a"
    assert mesmo["resumo"] == "Trecho do post."
    assert mesmo["imagem"] == "https://cdn/img.png"
    assert "_guid" not in mesmo


def test_medium_respeita_cota_por_tag(monkeypatch):
    monkeypatch.setattr(medium.config, "MEDIUM_TEXTO_COMPLETO", False)
    _feeds_falsos(monkeypatch, {
        "https://medium.com/feed/tag/muito": RSS_MEDIUM.replace("abc123", "m1").replace("def456", "m2"),
        "https://medium.com/feed/tag/pouco": RSS_MEDIUM.replace("abc123", "p1").replace("def456", "p2"),
    })
    resultado = medium.coletar(tags=["muito", "pouco"], por_tag=1)
    # cada tag contribui só com o seu item mais recente ("Outro", 17h)
    assert [(i["tag"], i["link"].rsplit("-", 1)[-1]) for i in resultado.dados] == [("muito", "m2"), ("pouco", "p2")]


def test_medium_busca_texto_completo_no_feed_do_autor(monkeypatch):
    monkeypatch.setattr(medium.config, "MEDIUM_TEXTO_COMPLETO", True)
    requisicoes = _feeds_falsos(monkeypatch, {
        "https://medium.com/feed/tag/a": RSS_MEDIUM,
        "https://medium.com/feed/@autor": RSS_AUTOR,
    })
    resultado = medium.coletar(tags=["a"], por_tag=5)
    outro, mesmo = resultado.dados
    assert outro["conteudo_html"] == "<p>Texto completo.</p>"
    assert outro["leitura_min"] == 1
    # post de domínio próprio: feed não existe -> fica só com o trecho e gera aviso
    assert mesmo["conteudo_html"] is None
    assert any("Mesmo post" in a for a in resultado.avisos)
    assert requisicoes.count("https://medium.com/feed/@autor") == 1


def test_medium_feed_de_origem():
    assert medium.feed_de_origem("https://medium.com/@joao/post-1") == "https://medium.com/feed/@joao"
    assert medium.feed_de_origem("https://medium.com/javarevisited/post-1") == "https://medium.com/feed/javarevisited"
    assert medium.feed_de_origem("https://joao.medium.com/post-1") == "https://joao.medium.com/feed"
    assert medium.feed_de_origem("https://blog.stackademic.com/post-1") == "https://blog.stackademic.com/feed"


RSS_INFOMONEY = """<?xml version="1.0"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>x</title>
<item><title>FII XPML11 aprova emissão</title><link>https://www.infomoney.com.br/onde-investir/fii-xpml11/</link>
  <dc:creator>Vinicius Alves</dc:creator><pubDate>Wed, 16 Sep 2026 15:02:54 +0000</pubDate>
  <category>Onde Investir</category><category>FIIs</category><category>XPML11</category>
  <description><![CDATA[<p><img class="wp-post-image" src="https://im/capa.jpg"/>A oferta será restrita.</p><p>The post <a href="#">X</a> appeared first on <a href="#">InfoMoney</a>.</p>]]></description>
  <content:encoded><![CDATA[<img class="attachment-medium wp-post-image" src="https://im/capa.jpg"/><p>Corpo da matéria.</p>
    <figure class="wp-block-embed-youtube"><div class="wp-block-embed__wrapper"></div></figure>
    <p><strong>Leia também: <a href="/outra/">Outra</a></strong></p>]]></content:encoded></item>
</channel></rss>"""


def test_infomoney_manchete_com_detalhes():
    item = infomoney.manchete_do_feed(feedparser.parse(RSS_INFOMONEY).entries[0])
    assert item == {
        "titulo": "FII XPML11 aprova emissão",
        "link": "https://www.infomoney.com.br/onde-investir/fii-xpml11/",
        "resumo": "A oferta será restrita.",
        "autor": "Vinicius Alves",
        "publicado_em": "2026-09-16T12:02:54-03:00",
        "categorias": ["FIIs", "XPML11"],
        "imagem": "https://im/capa.jpg",
        "conteudo_html": (
            '<p>Corpo da matéria.</p>\n<p><strong>Leia também: '
            '<a href="https://www.infomoney.com.br/outra/" rel="noopener noreferrer nofollow">Outra</a></strong></p>'
        ),
        "leitura_min": 1,
    }


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
