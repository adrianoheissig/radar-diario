# 📡 radar-diario

Painel pessoal publicado no **GitHub Pages** que mostra, toda manhã, um resumo com:

- cotações dos meus **FIIs** (preço e variação do último pregão, da semana e do mês);
- as **manchetes de capa da InfoMoney** com seção, resumo, autor, categorias e a matéria completa;
- artigos recentes do **Medium** (os mais novos de cada tag), só os que têm texto completo para ler no painel;
- a última publicação do **Corrida no Ar**, completa.

Cada fonte fica em uma aba. Textos longos abrem e fecham com um botão, sem sair do painel.

Sem backend e sem banco: um script Python roda no GitHub Actions, grava JSON em `docs/data/` e faz commit. O GitHub Pages serve a pasta `docs/`.

```
Gatilho diário às 06:00 BRT (cron externo; cron do GitHub como reserva)
   └─ GitHub Actions
        ├─ python collector/main.py
        │    ├─ docs/data/resumo-YYYY-MM-DD.json
        │    ├─ docs/data/latest.json
        │    └─ docs/data/index.json   (lista de datas disponíveis)
        └─ git commit + push (só se mudou)
GitHub Pages (main /docs)
   └─ index.html + app.js (Vue 3 via CDN) lê os JSONs
```

## Estrutura

```
.
├── .github/workflows/coleta-diaria.yml   # cron diário + disparo manual
├── collector/
│   ├── config.py          # tags, tickers, URLs  ← personalize aqui
│   ├── comum.py           # HTTP com retry, datas, feeds
│   ├── html_limpo.py      # limpeza + sanitização (nh3) do HTML completo
│   ├── main.py            # orquestra as fontes e grava os JSONs
│   └── fontes/
│       ├── fiis.py        # brapi.dev (+ fallback Yahoo Finance)
│       ├── infomoney.py   # feed RSS de FIIs (+ fallback scraping)
│       ├── medium.py      # feeds RSS por tag
│       └── corrida_no_ar.py  # feed RSS (+ fallback scraping da home)
├── docs/                  # site do GitHub Pages
│   ├── index.html  app.js  style.css   # Vue 3 + DOMPurify via CDN
│   └── data/              # JSONs gerados pelo coletor
├── tests/                 # testes offline (pytest)
├── Dockerfile  docker-compose.yml
└── requirements.txt  requirements-dev.txt
```

## Rodando localmente (Docker)

Pré-requisito: Docker com Compose v2.

```bash
cp .env.example .env          # opcional: preencha BRAPI_TOKEN
docker compose build coletor testes
docker compose run --rm coletor   # coleta e grava em docs/data/
docker compose run --rm testes    # testes offline
docker compose up -d web          # painel em http://localhost:8080
```

`collector/` e `docs/` são montados como volume, então dá para editar o código sem rebuild (só rode `docker compose build coletor testes` se mudar `requirements*.txt`).

Parar o painel: `docker compose down`.

### Sem Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python collector/main.py --stdout
pytest -q
python -m http.server -d docs 8080
```

## Publicando no GitHub

1. **Criar o repositório** e subir o código:
   ```bash
   gh repo create radar-diario --public --source . --push
   ```
   > No plano gratuito do GitHub, o Pages só funciona em repositório **público**. Isso deixa os JSONs (inclusive a lista de tickers) visíveis. Com GitHub Pro dá para usar repositório privado.
2. **Habilitar o Pages**: *Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main` / pasta `/docs` → Save*.
   O site fica em `https://<usuario>.github.io/radar-diario/`.
3. **Cadastrar o token da brapi** (opcional, recomendado): crie um token gratuito em <https://brapi.dev/dashboard> e cadastre em *Settings → Secrets and variables → Actions → New repository secret*, nome `BRAPI_TOKEN`.
4. **Permissão de escrita do Actions**: o workflow já declara `permissions: contents: write`. Se a sua conta/organização restringe isso, libere em *Settings → Actions → General → Workflow permissions → Read and write permissions*.
5. **Primeira execução**: *Actions → Coleta diária → Run workflow*.

## Agendamento

O cron do GitHub Actions é sempre em **UTC**, e São Paulo é UTC−3 (sem horário de verão desde 2019):

```yaml
- cron: "53 8 * * *"   # principal: 05:53 em São Paulo
- cron: "23 9 * * *"   # reserva:   06:23
- cron: "13 11 * * *"  # reserva:   08:13
```

- O GitHub pode **atrasar ou descartar** execuções agendadas em horários de pico, principalmente na virada da hora (`0 * * * *`). Por isso os minutos "quebrados" e as duas reservas.
- As reservas só coletam se `docs/data/resumo-<hoje>.json` ainda não existir; caso contrário terminam em segundos, sem commit. O disparo manual (*Run workflow*) sempre coleta.
- Se mesmo assim o resumo do dia não sair, o painel mostra um aviso de que está exibindo o resumo de um dia anterior.
- Em repositórios públicos, workflows agendados são desativados após 60 dias sem atividade no repositório. Se isso acontecer, reative em *Actions*.

### O agendador do GitHub não é confiável no horário

Na prática, o cron do GitHub tem atrasado muito ou simplesmente não disparado (em 17/09/2026, dos 3 horários só um rodou, e com 4h19 de atraso). Por isso o gatilho no horário vem de um **serviço de cron externo**, que chama a API do GitHub; os crons acima ficam só como reserva.

**1. Criar o token** (uma vez) em <https://github.com/settings/personal-access-tokens/new>:

| Campo | Valor |
|---|---|
| Token name | `radar-diario-cron` |
| Resource owner | `adrianoheissig` |
| Repository access | *Only select repositories* → `radar-diario` |
| Permissions → Repository | *Actions*: **Read and write** (o *Metadata: Read* entra sozinho) |
| Expiration | o prazo que preferir (anote para renovar) |

Guarde o token: ele só aparece uma vez. Ele só serve para disparar workflows deste repositório.

**2. Criar o job** em <https://cron-job.org> (grátis), com *Enable advanced settings*:

| Campo | Valor |
|---|---|
| Title | `Radar Diário` |
| URL | `https://api.github.com/repos/adrianoheissig/radar-diario/actions/workflows/coleta-diaria.yml/dispatches` |
| Schedule | todos os dias, 06:00, timezone `America/Sao_Paulo` |
| Request method | `POST` |
| Request body | `{"ref":"main"}` |
| Headers | `Accept: application/vnd.github+json`<br>`Authorization: Bearer <SEU_TOKEN>`<br>`Content-Type: application/json`<br>`X-GitHub-Api-Version: 2026-03-10` |

A resposta esperada é **HTTP 200**, sem corpo (a versão antiga `2022-11-28` ainda funciona e responde 204, mas está marcada como *deprecated*, com desligamento em 10/03/2028). O mesmo teste pelo terminal:

```bash
curl -i -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer $GITHUB_TOKEN" -H "X-GitHub-Api-Version: 2026-03-10" -d '{"ref":"main"}' https://api.github.com/repos/adrianoheissig/radar-diario/actions/workflows/coleta-diaria.yml/dispatches
```

As versões disponíveis aparecem em <https://api.github.com/versions>.

Como o disparo externo é `workflow_dispatch`, ele sempre coleta (a regra de "pular se o resumo já existe" vale só para os crons de reserva). Se o token vazar ou expirar, o job passa a receber 401/403: gere outro em *Settings → Developer settings → Personal access tokens* e atualize no cron-job.org.

## Fontes e fallbacks

| Fonte | Principal | Fallback |
|---|---|---|
| FIIs | `brapi.dev/api/quote/{ticker}?range=1mo` (com `BRAPI_TOKEN`) | Yahoo Finance `v8/finance/chart/{ticker}.SA` |
| InfoMoney | capa `infomoney.com.br` (as `INFOMONEY_LIMITE` primeiras manchetes, na ordem da home; o 1º card é o destaque) + página de cada matéria (metatags, JSON-LD e corpo em `article.im-article`) | feed geral `infomoney.com.br/feed/` (últimas notícias) |
| Medium | RSS `medium.com/feed/tag/{tag}`: os `MEDIUM_POR_TAG` mais recentes **com texto completo** de cada tag, deduplicados pelo guid. Texto buscado no feed do autor/publicação | artigos sem texto completo (exclusivos para membros ou fora do feed do autor) são pulados; tag com menos artigos que a cota ou que falha vira aviso |
| Corrida no Ar | RSS em `/feed`, `/rss`, `/feed.xml` (post completo via `content:encoded`) | autodescoberta via `<link rel="alternate">` e scraping do 1º post da home (só resumo) |

Detalhes:

- **brapi sem token** só atende alguns ativos de teste (PETR4, VALE3...). Ao receber erro de autenticação, o coletor desativa a brapi naquela execução e usa o Yahoo para todos os tickers. Com token, a brapi é usada e o Yahoo só entra se um ticker falhar.
- **InfoMoney**: o feed geral não traz as manchetes da capa, então os detalhes vêm da página de cada matéria (1 requisição por manchete). Anúncios, "Leia também" e chamadas de assinatura são removidos do corpo, e as imagens usam a versão reduzida do CDN (`resize=640,360`).
- **Yahoo** responde 429 para User-Agent de navegador completo sem cookies. Por isso ele usa um UA curto (`YAHOO_USER_AGENT` em `config.py`).
- **Variações dos FIIs** (a coleta roda antes da abertura, então tudo é relativo ao último pregão):
  - *Dia ant.*: variação do último pregão;
  - *Semana*: preço vs. último fechamento antes da segunda-feira da semana do último pregão;
  - *Mês*: preço vs. último fechamento antes do dia 1º do mês do último pregão.
  O histórico pedido é de 3 meses (`range=3mo`); se o plano não permitir, cai para 1 mês e depois só a cotação.
- **Medium, texto completo**: o feed de tag só traz um trecho. O coletor lê o feed do autor (`medium.com/feed/@autor`), da publicação (`medium.com/feed/publicacao`) ou do domínio próprio (`blog.exemplo.com/feed`) e localiza o post pelo guid. Com `MEDIUM_APENAS_TEXTO_COMPLETO = False` os artigos sem texto completo voltam a aparecer (trecho + link).

## Conteúdo completo e segurança

O HTML dos artigos vem de sites de terceiros e é exibido dentro do painel, então passa por duas camadas:

1. **Coletor** ([`collector/html_limpo.py`](collector/html_limpo.py)): remove rodapés de feed, pixels de rastreamento, botões de compartilhamento e blocos vazios, resolve URLs relativas e aplica allowlist com [nh3](https://github.com/messense/nh3). Ficam só tags de texto, listas, código, tabelas, imagens e links. Scripts, estilos, iframes e atributos de evento são removidos.
2. **Navegador**: [DOMPurify](https://github.com/cure53/DOMPurify) sanitiza de novo antes do `v-html`, e todos os links abrem em nova aba com `rel="noopener noreferrer"`.

Com o conteúdo completo, cada resumo diário fica com ~130 KB (cerca de 50 MB por ano de histórico em `docs/data/`).

## Tratamento de erros

Cada fonte roda isolada. Se uma falhar, as demais são coletadas e o erro fica registrado em `status`:

- falha total de uma fonte: `status.<fonte>.ok = false`, `erro` preenchido, e o dado fica vazio (`[]` ou `null`);
- falha parcial (ex.: 1 ticker, 1 tag): `ok = true` com a mensagem em `avisos`; ticker sem cotação aparece com `preco: null`;
- **todas** as fontes falharam: nada é gravado e o processo sai com código 1 (o job do Actions fica vermelho e o GitHub avisa por e-mail).

O painel mostra falhas e avisos no card de cada fonte.

## Schema (`latest.json` / `resumo-YYYY-MM-DD.json`)

```jsonc
{
  "gerado_em": "2026-09-16T06:00:12-03:00",
  "data": "2026-09-16",
  "fiis": [
    {"ticker": "KNRI11", "preco": 157.6, "variacao_dia_pct": -0.83, "variacao_semana_pct": -0.15, "variacao_mes_pct": -0.22,
     "cotado_em": "2026-09-15T18:07:00-03:00", "fonte": "brapi"}
  ],
  "infomoney_manchetes": [
    {"titulo": "...", "link": "https://...", "destaque": true, "secao": "Mercados", "resumo": "...",
     "autor": "...", "publicado_em": "ISO-8601", "categorias": ["Ações", "Dólar"], "imagem": "https://...",
     "conteudo_html": "<p>...</p>", "leitura_min": 6}
  ],
  "medium": [
    {"titulo": "...", "link": "...", "autor": "...", "tag": "Claude", "publicado_em": "ISO-8601",
     "resumo": "trecho", "imagem": "https://...", "conteudo_html": "<p>...</p> ou null", "leitura_min": 7}
  ],
  "corrida_no_ar": {"titulo": "...", "link": "...", "resumo": "...", "publicado_em": "ISO-8601",
                    "imagem": "https://...", "conteudo_html": "<p>...</p>", "leitura_min": 3},
  "status": {
    "fiis": {"ok": true, "erro": null, "origem": "brapi", "avisos": [], "duracao_s": 1.8}
    // ... uma entrada por fonte
  }
}
```

Os campos além do schema mínimo original (`data`, `status`, `cotado_em`, `fonte`, `resumo`, `imagem`, `conteudo_html`, `leitura_min` etc.) podem ser `null` quando a fonte não fornece; o painel trata isso. `conteudo_html` já vem sanitizado. `index.json`:

```json
{"atualizado_em": "2026-09-16T06:00:14-03:00", "datas": ["2026-09-16", "2026-09-15"]}
```

## Personalização

Tudo em [`collector/config.py`](collector/config.py): `MEDIUM_TAGS`, `MEDIUM_POR_TAG`, `MEDIUM_APENAS_TEXTO_COMPLETO`, `FIIS`, `INFOMONEY_LIMITE`, `INFOMONEY_RESUMO_MAX`, `FII_FALLBACK_YAHOO` etc.

No painel, a aba e a data ficam na URL (`#medium`, `#2026-09-15/corrida`), então dá para salvar atalhos. O tema claro/escuro é lembrado no navegador.
