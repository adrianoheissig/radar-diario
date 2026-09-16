const { createApp, ref, computed, onMounted } = Vue;

const DATA_DIR = "data";
const REGEX_DATA = /^\d{4}-\d{2}-\d{2}$/;

const fmtPreco = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmtPct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
const fmtData = new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const fmtDataHora = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
const fmtRelativo = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });

async function buscarJson(caminho, semCache = false) {
  const url = semCache ? `${caminho}?t=${Date.now()}` : caminho;
  const resposta = await fetch(url, { cache: semCache ? "no-store" : "default" });
  if (!resposta.ok) throw new Error(`${caminho}: HTTP ${resposta.status}`);
  return resposta.json();
}

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

createApp({
  components: { StatusFonte },
  setup() {
    const resumo = ref(null);
    const datas = ref([]);
    const dataAtual = ref("");
    const carregando = ref(true);
    const erroCarga = ref("");
    const tema = ref(document.documentElement.dataset.theme || "dark");

    const indiceAtual = computed(() => datas.value.indexOf(dataAtual.value));
    const temMaisAntigo = computed(() => indiceAtual.value >= 0 && indiceAtual.value < datas.value.length - 1);
    const temMaisNovo = computed(() => indiceAtual.value > 0);

    async function carregar(data) {
      carregando.value = true;
      erroCarga.value = "";
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
        carregando.value = false;
      }
    }

    function irPara(data) {
      if (!REGEX_DATA.test(data)) return;
      if (location.hash.slice(1) === data) carregar(data);
      else location.hash = data; // dispara hashchange -> carregar
    }

    function mover(passo) {
      const destino = datas.value[indiceAtual.value + passo];
      if (destino) irPara(destino);
    }

    function dataDoHash() {
      const h = decodeURIComponent(location.hash.slice(1));
      return REGEX_DATA.test(h) ? h : "";
    }

    onMounted(async () => {
      try {
        const indice = await buscarJson(`${DATA_DIR}/index.json`, true);
        datas.value = Array.isArray(indice.datas) ? indice.datas : [];
      } catch (e) {
        console.warn("index.json indisponível", e);
      }
      window.addEventListener("hashchange", () => carregar(dataDoHash()));
      await carregar(dataDoHash());
    });

    function alternarTema() {
      tema.value = tema.value === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = tema.value;
      document.querySelector('meta[name="theme-color"]').content = tema.value === "dark" ? "#0d1117" : "#f6f8fa";
      try { localStorage.setItem("radar-tema", tema.value); } catch (_) {}
    }

    const st = (fonte) => (resumo.value && resumo.value.status && resumo.value.status[fonte]) || null;

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
      resumo, datas, dataAtual, carregando, erroCarga, tema,
      temMaisAntigo, temMaisNovo, irPara, mover, alternarTema, st,
      formatarData, formatarDataHora, formatarPreco, formatarPct, classeVariacao, tempoRelativo,
    };
  },
}).mount("#app");
