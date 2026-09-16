"""Configuração do coletor. Edite aqui para mudar fontes, tags e tickers."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "docs" / "data"

TIMEZONE = "America/Sao_Paulo"

# HTTP
HTTP_TIMEOUT = (10, 25)  # (conexão, leitura) em segundos
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 radar-diario/1.0"
)

# 1. Medium
MEDIUM_TAGS = ["Claude", "Vuejs", "artificial-intelligence", "software-engineering"]
MEDIUM_FEED_URL = "https://medium.com/feed/tag/{tag}"
# Quantos itens mais recentes pegar de cada tag (evita que tags com muito volume dominem).
MEDIUM_POR_TAG = 2

# 2. Corrida no Ar
CORRIDA_NO_AR_URL = "https://corridanoar.com"
CORRIDA_NO_AR_FEED_PATHS = ["/feed", "/rss", "/feed.xml"]
CORRIDA_NO_AR_RESUMO_MAX = 280

# 3. InfoMoney FIIs
# O feed da tag "fundos-imobiliarios" é a fonte principal: a seção
# "Últimas notícias sobre FIIs" da página de cotações costuma estar desatualizada.
# A página é usada como fallback (scraping).
INFOMONEY_FII_FEED = "https://www.infomoney.com.br/tudo-sobre/fundos-imobiliarios/feed/"
INFOMONEY_FII_URL = "https://www.infomoney.com.br/cotacoes/b3/fii/"
INFOMONEY_LIMITE = 5

# 4. Cotações dos FIIs
FIIS = ["KNRI11", "HGLG11", "XPML11", "CPTS11", "PVBI11", "KNCR11", "VCJR11", "BTLG11", "CPTI11"]
BRAPI_URL = "https://brapi.dev/api/quote/{ticker}"
# Sem BRAPI_TOKEN a brapi só responde alguns ativos de teste (PETR4, VALE3...).
# Quando a brapi falha para um ticker, o Yahoo Finance é usado como fallback.
FII_FALLBACK_YAHOO = True
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.SA"
# O Yahoo responde 429 para UAs de navegador completos sem cookies; o UA curto é aceito.
YAHOO_USER_AGENT = "Mozilla/5.0"
