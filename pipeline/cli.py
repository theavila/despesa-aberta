"""Linha de comando: `serenata coletar|analisar|publicar|exportar`."""

import argparse
import logging
import sys
from datetime import date

from pipeline import config as cfg
from pipeline import db
from pipeline.coletores import camara, senado
from pipeline.http import criar_cliente
from pipeline.normalizacao.normalizar import normalizar

log = logging.getLogger("serenata")


def cmd_coletar(args: argparse.Namespace) -> None:
    conf = cfg.carregar_config()
    coleta = conf["coleta"]
    urls = coleta["urls"]
    retry = {"tentativas": coleta["tentativas"], "backoff_base": coleta["backoff_base_segundos"]}
    casas = ["camara", "senado"] if args.casa == "todas" else [args.casa]
    con = db.conectar(cfg.caminho_banco())
    with criar_cliente(coleta) as cliente:
        for ano in args.ano:
            if "camara" in casas:
                deputados = camara.buscar_deputados(
                    cliente, urls["camara_deputados"], senado.legislaturas_do_ano(ano), **retry
                )
                db.gravar_parlamentares(con, deputados)
                linhas = camara.coletar(cliente, urls["camara_cotas"], ano, **retry)
                novas = db.inserir_brutos(con, linhas, "camara", ano)
                log.info("Câmara %s: %d linhas, %d novas", ano, len(linhas), novas)
            if "senado" in casas:
                senadores = senado.buscar_senadores(
                    cliente,
                    urls["senado_lista_atual"],
                    urls["senado_lista_legislatura"],
                    ano,
                    **retry,
                )
                db.gravar_parlamentares(con, senadores)
                linhas = senado.coletar(cliente, urls["senado_ceaps"], ano, **retry)
                novas = db.inserir_brutos(con, linhas, "senado", ano)
                log.info("Senado %s: %d linhas, %d novas", ano, len(linhas), novas)
    log.info("Despesas normalizadas: %d", normalizar(con, urls))
    con.close()


def cmd_normalizar(args: argparse.Namespace) -> None:
    con = db.conectar(cfg.caminho_banco())
    log.info("Despesas normalizadas: %d", normalizar(con, cfg.carregar_config()["coleta"]["urls"]))
    con.close()


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serenata", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("coletar", help="baixa despesas da Câmara e do Senado")
    p.add_argument("--ano", type=int, nargs="+", default=[date.today().year])
    p.add_argument("--casa", choices=["camara", "senado", "todas"], default="todas")
    p.set_defaults(func=cmd_coletar)

    p = sub.add_parser("normalizar", help="refaz a tabela de despesas a partir dos dados brutos")
    p.set_defaults(func=cmd_normalizar)
    return parser


def main(argv: list[str] | None = None) -> None:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")
    args = criar_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
