# 📡 radar-diario

Painel pessoal publicado no **GitHub Pages** que mostra, toda manhã, um resumo com:

- cotações dos meus **FIIs** (preço, variação do dia e de 30 dias);
- manchetes de **FIIs da InfoMoney** com resumo, autor, categorias e a matéria completa;
- artigos recentes do **Medium** (os mais novos de cada tag), com o texto completo para ler no painel;
- a última publicação do **Corrida no Ar**, completa.

Cada fonte fica em uma aba. Textos longos abrem e fecham com um botão, sem sair do painel.

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
| InfoMoney | RSS `infomoney.com.br/tudo-sobre/fundos-imobiliarios/feed/` (resumo, autor, categorias, imagem e matéria completa via `content:encoded`) | scraping da seção "Últimas notícias sobre FIIs" em `/cotacoes/b3/fii/` (só título e link) |
| Medium | RSS `medium.com/feed/tag/{tag}`: os `MEDIUM_POR_TAG` mais recentes de cada tag, deduplicados pelo guid. Texto completo buscado no feed do autor/publicação | sem texto completo (exclusivo para membros ou fora do feed do autor): fica o trecho + link; tags que falham viram aviso |
| Corrida no Ar | RSS em `/feed`, `/rss`, `/feed.xml` (post completo via `content:encoded`) | autodescoberta via `<link rel="alternate">` e scraping do 1º post da home (só resumo) |

Detalhes:

- **brapi sem token** só atende alguns ativos de teste (PETR4, VALE3...). Ao receber erro de autenticação, o coletor desativa a brapi naquela execução e usa o Yahoo para todos os tickers. Com token, a brapi é usada e o Yahoo só entra se um ticker falhar.
- **InfoMoney**: a seção de notícias da página de cotações costuma estar desatualizada (em set/2026 trazia só 4 notícias, de um mês antes). Por isso o feed da tag é a fonte principal.
- **Yahoo** responde 429 para User-Agent de navegador completo sem cookies. Por isso ele usa um UA curto (`YAHOO_USER_AGENT` em `config.py`).
- A variação de 30 dias compara o preço atual com o último fechamento de 30 dias atrás ou antes.
- **Medium, texto completo**: o feed de tag só traz um trecho. O coletor lê o feed do autor (`medium.com/feed/@autor`), da publicação (`medium.com/feed/publicacao`) ou do domínio próprio (`blog.exemplo.com/feed`) e localiza o post pelo guid. Desligue com `MEDIUM_TEXTO_COMPLETO = False`.

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
    {"ticker": "KNRI11", "preco": 157.6, "variacao_dia_pct": -0.55, "variacao_30d_pct": 5.69,
     "cotado_em": "2026-09-15T18:07:00-03:00", "fonte": "brapi"}
  ],
  "infomoney_manchetes": [
    {"titulo": "...", "link": "https://...", "resumo": "...", "autor": "...", "publicado_em": "ISO-8601",
     "categorias": ["FIIs", "XPML11"], "imagem": "https://...", "conteudo_html": "<p>...</p>", "leitura_min": 3}
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

Tudo em [`collector/config.py`](collector/config.py): `MEDIUM_TAGS`, `MEDIUM_POR_TAG`, `MEDIUM_TEXTO_COMPLETO`, `FIIS`, `INFOMONEY_LIMITE`, `INFOMONEY_RESUMO_MAX`, `FII_FALLBACK_YAHOO` etc.

No painel, a aba e a data ficam na URL (`#medium`, `#2026-09-15/corrida`), então dá para salvar atalhos. O tema claro/escuro é lembrado no navegador.
