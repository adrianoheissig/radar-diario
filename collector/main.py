"""Coletor do Radar Diário.

Uso:
    python collector/main.py                 # grava em docs/data/
    python collector/main.py --stdout        # também imprime o JSON
    python collector/main.py --data-dir /tmp/dados

Cada fonte roda isolada: se uma falhar, as demais seguem e o erro fica em
`status.<fonte>`. Só retorna código != 0 (sem gravar nada) se TODAS falharem.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from collector import config  # noqa: E402
from collector.comum import agora, iso  # noqa: E402
from collector.fontes import corrida_no_ar, fiis, infomoney, medium  # noqa: E402

log = logging.getLogger("radar")

# (chave no JSON, função de coleta, fábrica do valor vazio em caso de erro)
FONTES = [
    ("fiis", fiis.coletar, list),
    ("infomoney_manchetes", infomoney.coletar, list),
    ("medium", medium.coletar, list),
    ("corrida_no_ar", corrida_no_ar.coletar, lambda: None),
]

_ARQUIVO_DIARIO = re.compile(r"^resumo-(\d{4}-\d{2}-\d{2})\.json$")


def executar_fonte(nome, coletar):
    inicio = time.monotonic()
    try:
        resultado = coletar()
        dados = resultado.dados
        status = {"ok": True, "erro": None, "origem": resultado.origem, "avisos": resultado.avisos}
    except Exception as exc:
        log.exception("fonte %s falhou", nome)
        dados = None
        status = {"ok": False, "erro": f"{type(exc).__name__}: {exc}", "origem": None, "avisos": []}
    status["duracao_s"] = round(time.monotonic() - inicio, 2)
    return dados, status


def montar_resumo(fontes=None) -> dict:
    fontes = fontes or FONTES
    momento = agora()
    resumo = {"gerado_em": iso(momento), "data": momento.date().isoformat()}
    status = {}
    for nome, coletar, vazio in fontes:
        log.info("coletando %s…", nome)
        dados, status[nome] = executar_fonte(nome, coletar)
        resumo[nome] = dados if status[nome]["ok"] else vazio()
    resumo["status"] = status
    return resumo


def salvar(resumo: dict, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps(resumo, ensure_ascii=False, indent=2) + "\n"
    (data_dir / f"resumo-{resumo['data']}.json").write_text(conteudo, encoding="utf-8")
    (data_dir / "latest.json").write_text(conteudo, encoding="utf-8")
    atualizar_indice(data_dir)


def atualizar_indice(data_dir: Path) -> dict:
    datas = sorted(
        (m.group(1) for p in data_dir.iterdir() if (m := _ARQUIVO_DIARIO.match(p.name))),
        reverse=True,
    )
    indice = {"atualizado_em": iso(agora()), "datas": datas}
    (data_dir / "index.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return indice


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Coletor do Radar Diário")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--stdout", action="store_true", help="imprime o JSON gerado")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    resumo = montar_resumo()
    for nome, st in resumo["status"].items():
        situacao = "OK  " if st["ok"] else "ERRO"
        detalhe = st["origem"] if st["ok"] else st["erro"]
        log.info("[%s] %-20s %5.2fs  %s", situacao, nome, st["duracao_s"], detalhe)
        for aviso in st["avisos"]:
            log.warning("      aviso %s: %s", nome, aviso)

    if not any(st["ok"] for st in resumo["status"].values()):
        log.error("todas as fontes falharam; nada foi gravado")
        return 1

    salvar(resumo, args.data_dir)
    log.info("gravado em %s", args.data_dir)
    if args.stdout:
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
