# 📡 radar-diario

Painel pessoal publicado no **GitHub Pages** que mostra, toda manhã, um resumo com:

- cotações dos meus **FIIs** (preço, variação do dia e de 30 dias);
- manchetes de **FIIs da InfoMoney**;
- artigos recentes do **Medium** (os mais novos de cada tag);
- a última publicação do **Corrida no Ar**.

Sem backend e sem banco: um script Python roda no GitHub Actions, grava JSON em `docs/data/` e faz commit. O GitHub Pages serve a pasta `docs/`.

```
GitHub Actions (cron 06:00 BRT)
   └─ python collector/main.py
        ├─ docs/data/resumo-YYYY-MM-DD.json
        ├─ docs/data/latest.json
        └─ docs/data/index.json   (lista de datas disponíveis)
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
│   ├── main.py            # orquestra as fontes e grava os JSONs
│   └── fontes/
│       ├── fiis.py        # brapi.dev (+ fallback Yahoo Finance)
│       ├── infomoney.py   # feed RSS de FIIs (+ fallback scraping)
│       ├── medium.py      # feeds RSS por tag
│       └── corrida_no_ar.py  # feed RSS (+ fallback scraping da home)
├── docs/                  # site do GitHub Pages
│   ├── index.html  app.js  style.css
│   └── data/              # JSONs gerados pelo coletor
├── tests/                 # testes offline (pytest)
├── Dockerfile  docker-compose.yml
└── requirements.txt  requirements-dev.txt
```

## Rodando localmente (Docker)

Pré-requisito: Docker com Compose v2.

```bash
cp .env.example .env          # opcional: preencha BRAPI_TOKEN
docker compose build
docker compose run --rm coletor   # coleta e grava em docs/data/
docker compose run --rm testes    # testes offline
docker compose up -d web          # painel em http://localhost:8080
```

`collector/` e `docs/` são montados como volume, então dá para editar o código sem rebuild (só rode `docker compose build` se mudar `requirements*.txt`).

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

O cron do GitHub Actions é sempre em **UTC**. 06:00 em `America/Sao_Paulo` (UTC−3, sem horário de verão desde 2019) = **09:00 UTC**:

```yaml
- cron: "0 9 * * *"
```

Observações:

- O GitHub pode atrasar execuções agendadas em alguns minutos (às vezes mais) em horários de pico.
- Em repositórios públicos, workflows agendados são desativados após 60 dias sem atividade no repositório. Se isso acontecer, reative em *Actions*.

## Fontes e fallbacks

| Fonte | Principal | Fallback |
|---|---|---|
| FIIs | `brapi.dev/api/quote/{ticker}?range=1mo` (com `BRAPI_TOKEN`) | Yahoo Finance `v8/finance/chart/{ticker}.SA` |
| InfoMoney | RSS `infomoney.com.br/tudo-sobre/fundos-imobiliarios/feed/` | scraping da seção "Últimas notícias sobre FIIs" em `/cotacoes/b3/fii/` |
| Medium | RSS `medium.com/feed/tag/{tag}`: os `MEDIUM_POR_TAG` mais recentes de cada tag, deduplicados pelo guid e ordenados por data | tags que falham viram aviso; as outras seguem |
| Corrida no Ar | RSS em `/feed`, `/rss`, `/feed.xml` | autodescoberta via `<link rel="alternate">` e scraping do 1º post da home |

Detalhes:

- **brapi sem token** só atende alguns ativos de teste (PETR4, VALE3...). Ao receber erro de autenticação, o coletor desativa a brapi naquela execução e usa o Yahoo para todos os tickers. Com token, a brapi é usada e o Yahoo só entra se um ticker falhar.
- **InfoMoney**: a seção de notícias da página de cotações costuma estar desatualizada (em set/2026 trazia só 4 notícias, de um mês antes). Por isso o feed da tag é a fonte principal.
- **Yahoo** responde 429 para User-Agent de navegador completo sem cookies. Por isso ele usa um UA curto (`YAHOO_USER_AGENT` em `config.py`).
- A variação de 30 dias compara o preço atual com o último fechamento de 30 dias atrás ou antes.

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
    {"ticker": "KNRI11", "preco": 157.54, "variacao_dia_pct": -0.59, "variacao_30d_pct": 5.65,
     "cotado_em": "2026-09-15T18:07:00-03:00", "fonte": "brapi"}
  ],
  "infomoney_manchetes": [{"titulo": "...", "link": "https://..."}],
  "medium": [{"titulo": "...", "link": "...", "autor": "...", "tag": "Claude", "publicado_em": "ISO-8601"}],
  "corrida_no_ar": {"titulo": "...", "link": "...", "resumo": "...", "publicado_em": "ISO-8601"},
  "status": {
    "fiis": {"ok": true, "erro": null, "origem": "brapi", "avisos": [], "duracao_s": 1.8}
    // ... uma entrada por fonte
  }
}
```

`cotado_em`, `fonte`, `data` e `status` são extras em relação ao schema mínimo. `index.json`:

```json
{"atualizado_em": "2026-09-16T06:00:14-03:00", "datas": ["2026-09-16", "2026-09-15"]}
```

## Personalização

Tudo em [`collector/config.py`](collector/config.py): `MEDIUM_TAGS`, `MEDIUM_POR_TAG`, `FIIS`, `INFOMONEY_LIMITE`, `FII_FALLBACK_YAHOO` etc.

No painel, a data escolhida fica na URL (`#2026-09-15`) e o tema claro/escuro é lembrado no navegador.
