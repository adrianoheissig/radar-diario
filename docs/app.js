const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } = Vue;

const DATA_DIR = "data";
const REGEX_DATA = /^\d{4}-\d{2}-\d{2}$/;

const ABAS = [
  { id: "fiis", rotulo: "FIIs", fonte: "fiis" },
  { id: "infomoney", rotulo: "InfoMoney", fonte: "infomoney_manchetes" },
  { id: "medium", rotulo: "Medium", fonte: "medium" },
  { id: "corrida", rotulo: "Corrida", fonte: "corrida_no_ar" },
];
const ABA_PADRAO = ABAS[0].id;

const fmtPreco = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmtPct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
const fmtData = new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const fmtDataHora = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
const fmtRelativo = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });

// ---------------------------------------------------------------- sanitização

// O coletor já sanitiza com nh3; aqui é a segunda camada, antes do v-html.
DOMPurify.addHook("afterSanitizeAttributes", (no) => {
  if (no.tagName === "A") {
    no.setAttribute("target", "_blank");
    no.setAttribute("rel", "noopener noreferrer nofollow");
  } else if (no.tagName === "IMG") {
    no.setAttribute("loading", "lazy");
    no.setAttribute("referrerpolicy", "no-referrer");
  }
});

function sanitizar(html) {
  return DOMPurify.sanitize(html || "", {
    FORBID_TAGS: ["style", "form", "input", "button", "iframe", "object", "embed", "svg", "math"],
    FORBID_ATTR: ["style", "class", "id"],
    ADD_ATTR: ["target"],
  });
}

// ---------------------------------------------------------------- util

async function buscarJson(caminho, semCache = false) {
  const url = semCache ? `${caminho}?t=${Date.now()}` : caminho;
  const resposta = await fetch(url, { cache: semCache ? "no-store" : "default" });
  if (!resposta.ok) throw new Error(`${caminho}: HTTP ${resposta.status}`);
  return resposta.json();
}

function lerHash() {
  const partes = decodeURIComponent(location.hash.slice(1)).split("/").filter(Boolean);
  const data = partes.find((p) => REGEX_DATA.test(p)) || "";
  const aba = partes.find((p) => ABAS.some((a) => a.id === p)) || ABA_PADRAO;
  return { data, aba };
}

function montarHash(data, aba) {
  return "#" + [data, aba].filter(Boolean).join("/");
}

function hashCurto(texto) {
  let h = 0;
  for (let i = 0; i < texto.length; i++) h = (Math.imul(31, h) + texto.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

// ---------------------------------------------------------------- componentes

const StatusFonte = {
  props: { status: { type: Object, default: null } },
  template: `
    <div v-if="status && !status.ok" class="alerta alerta-erro" role="alert">
      Falha na coleta: {{ status.erro }}
    </div>
    <details v-else-if="status && status.avisos && status.avisos.length" class="alerta alerta-aviso">
      <summary>{{ status.avisos.length }} aviso(s) na coleta</summary>
      <ul><li v-for="(a, i) in status.avisos" :key="i">{{ a }}</li></ul>
    </details>
  `,
};

const ConteudoSeguro = {
  props: { html: { type: String, required: true } },
  setup(props) {
    const limpo = computed(() => sanitizar(props.html));
    return { limpo };
  },
  template: `<div class="artigo" v-html="limpo"></div>`,
};

const Leitor = {
  components: { ConteudoSeguro },
  props: {
    html: { type: String, required: true },
    link: { type: String, required: true },
    fonte: { type: String, required: true },
    aberto: { type: Boolean, default: false },
    rotuloAbrir: { type: String, default: "Ler aqui" },
  },
  emits: ["alternar"],
  template: `
    <div class="leitor">
      <button type="button" class="botao-expandir" :aria-expanded="aberto" @click="$emit('alternar')">
        <span>{{ aberto ? 'Recolher' : rotuloAbrir }}</span>
        <span class="seta" aria-hidden="true">{{ aberto ? '▴' : '▾' }}</span>
      </button>
      <div v-if="aberto" class="leitor-corpo">
        <conteudo-seguro :html="html"></conteudo-seguro>
        <div class="leitor-rodape">
          <button type="button" class="botao-expandir botao-expandir-fim" @click="$emit('alternar')">
            <span>Recolher</span><span class="seta" aria-hidden="true">▴</span>
          </button>
          <a :href="link" target="_blank" rel="noopener">Ver no {{ fonte }} ↗</a>
        </div>
      </div>
    </div>
  `,
};

// ---------------------------------------------------------------- app

createApp({
  components: { StatusFonte, ConteudoSeguro, Leitor },
  setup() {
    const resumo = ref(null);
    const datas = ref([]);
    const dataAtual = ref("");
    const dataCarregada = ref(null); // data pedida no hash ("" = mais recente)
    const carregando = ref(true);
    const erroCarga = ref("");
    const tema = ref(document.documentElement.dataset.theme || "dark");
    const aba = ref(ABA_PADRAO);
    const abertos = reactive(new Set());
    const filtroTag = ref("");
    const barraAbas = ref(null);

    const indiceAtual = computed(() => datas.value.indexOf(dataAtual.value));
    const temMaisAntigo = computed(() => indiceAtual.value >= 0 && indiceAtual.value < datas.value.length - 1);
    const temMaisNovo = computed(() => indiceAtual.value > 0);

    // ---- dados

    async function carregar(data) {
      carregando.value = true;
      erroCarga.value = "";
      abertos.clear();
      filtroTag.value = "";
      try {
        const ehMaisRecente = !data || data === datas.value[0];
        resumo.value = ehMaisRecente
          ? await buscarJson(`${DATA_DIR}/latest.json`, true)
          : await buscarJson(`${DATA_DIR}/resumo-${data}.json`);
        dataAtual.value = resumo.value.data || data;
      } catch (e) {
        resumo.value = null;
        erroCarga.value = data
          ? `Não encontrei o resumo de ${formatarData(data)}.`
          : "Nenhum resumo disponível ainda. Rode o coletor para gerar o primeiro.";
        console.error(e);
      } finally {
        dataCarregada.value = data;
        carregando.value = false;
      }
    }

    // ---- navegação (hash = #[data/]aba)

    function aplicarHash() {
      const { data, aba: abaHash } = lerHash();
      aba.value = abaHash;
      if (data !== dataCarregada.value) carregar(data);
    }

    function dataParaHash(data) {
      return data && data !== datas.value[0] ? data : "";
    }

    function irParaData(data) {
      if (!REGEX_DATA.test(data)) return;
      location.hash = montarHash(dataParaHash(data), aba.value);
    }

    function mover(passo) {
      const destino = datas.value[indiceAtual.value + passo];
      if (destino) irParaData(destino);
    }

    function selecionarAba(id) {
      if (aba.value === id) return;
      aba.value = id;
      history.replaceState(null, "", montarHash(dataParaHash(dataAtual.value), id));
      // posição "natural" da barra de abas (offsetTop de um elemento sticky muda ao rolar)
      const topo = document.querySelector(".topo");
      const topoAbas = topo ? topo.offsetTop + topo.offsetHeight : 0;
      if (window.scrollY > topoAbas) window.scrollTo({ top: topoAbas });
    }

    // ---- expandir / recolher

    const estaAberto = (link) => abertos.has(link);

    async function alternar(link, prefixo) {
      if (abertos.has(link)) {
        abertos.delete(link);
        // ao recolher um texto longo, volta para o início do item
        await nextTick();
        const el = document.getElementById(idItem(prefixo, link));
        if (el && el.getBoundingClientRect().top < 0) el.scrollIntoView({ block: "start" });
      } else {
        abertos.add(link);
      }
    }

    const tagsMedium = computed(() => [...new Set((resumo.value?.medium || []).map((m) => m.tag))]);
    const mediumFiltrado = computed(() =>
      (resumo.value?.medium || []).filter((m) => !filtroTag.value || m.tag === filtroTag.value)
    );
    const mediumComTexto = computed(() => mediumFiltrado.value.filter((m) => m.conteudo_html));
    const todosMediumAbertos = computed(
      () => mediumComTexto.value.length > 0 && mediumComTexto.value.every((m) => abertos.has(m.link))
    );

    function alternarTodosMedium() {
      const abrir = !todosMediumAbertos.value;
      mediumComTexto.value.forEach((m) => (abrir ? abertos.add(m.link) : abertos.delete(m.link)));
    }

    // ---- ciclo de vida

    let observador;
    onMounted(async () => {
      if (barraAbas.value && "ResizeObserver" in window) {
        observador = new ResizeObserver(([e]) =>
          document.documentElement.style.setProperty("--altura-abas", `${e.target.offsetHeight}px`)
        );
        observador.observe(barraAbas.value);
      }
      try {
        const indice = await buscarJson(`${DATA_DIR}/index.json`, true);
        datas.value = Array.isArray(indice.datas) ? indice.datas : [];
      } catch (e) {
        console.warn("index.json indisponível", e);
      }
      window.addEventListener("hashchange", aplicarHash);
      aplicarHash();
    });
    onBeforeUnmount(() => {
      window.removeEventListener("hashchange", aplicarHash);
      if (observador) observador.disconnect();
    });

    // ---- apresentação

    function alternarTema() {
      tema.value = tema.value === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = tema.value;
      document.querySelector('meta[name="theme-color"]').content = tema.value === "dark" ? "#0d1117" : "#f6f8fa";
      try { localStorage.setItem("radar-tema", tema.value); } catch (_) {}
    }

    const st = (fonte) => (resumo.value && resumo.value.status && resumo.value.status[fonte]) || null;

    function contagem(a) {
      if (!resumo.value) return 0;
      const dados = resumo.value[a.fonte];
      if (a.id === "fiis" || a.id === "corrida") return 0;
      return Array.isArray(dados) ? dados.length : 0;
    }

    const idItem = (prefixo, link) => `${prefixo}-${hashCurto(link)}`;

    function formatarData(iso) {
      return fmtData.format(new Date(`${iso}T12:00:00Z`));
    }
    function formatarDataHora(iso) {
      return iso ? fmtDataHora.format(new Date(iso)) : "";
    }
    function formatarPreco(v) {
      return v == null ? "—" : fmtPreco.format(v);
    }
    function formatarPct(v) {
      return v == null ? "—" : `${fmtPct.format(v)}%`;
    }
    function classeVariacao(v) {
      if (v == null || v === 0) return "neutro";
      return v > 0 ? "positivo" : "negativo";
    }
    function tempoRelativo(iso) {
      const seg = (new Date(iso).getTime() - Date.now()) / 1000;
      const unidades = [["year", 31536000], ["month", 2592000], ["day", 86400], ["hour", 3600], ["minute", 60]];
      for (const [unidade, s] of unidades) {
        if (Math.abs(seg) >= s) return fmtRelativo.format(Math.round(seg / s), unidade);
      }
      return "agora";
    }

    return {
      abas: ABAS, aba, barraAbas, resumo, datas, dataAtual, carregando, erroCarga, tema,
      temMaisAntigo, temMaisNovo, irParaData, mover, selecionarAba, alternarTema, st, contagem,
      estaAberto, alternar, idItem, filtroTag, tagsMedium, mediumFiltrado, todosMediumAbertos, alternarTodosMedium,
      formatarData, formatarDataHora, formatarPreco, formatarPct, classeVariacao, tempoRelativo,
    };
  },
}).mount("#app");
