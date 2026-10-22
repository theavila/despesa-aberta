"""Linha de comando: `serenata coletar|analisar|publicar|exportar`."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from pipeline import config as cfg
from pipeline import db, publicacao
from pipeline import respostas as resp
from pipeline.analise import analisar
from pipeline.coletores import camara, cnpj, senado
from pipeline.exportar import exportar
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


def cmd_analisar(args: argparse.Namespace) -> None:
    conf = cfg.carregar_config()
    con = db.conectar(cfg.caminho_banco())
    if not args.sem_cnpj:
        coleta = conf["coleta"]
        retry = {
            "tentativas": coleta["tentativas"],
            "backoff_base": coleta["backoff_base_segundos"],
        }
        with criar_cliente(coleta) as cliente:
            consultados = cnpj.atualizar_cache(con, cliente, conf["cnpj"], **retry)
        log.info("CNPJs consultados na BrasilAPI: %d", consultados)
    resumo = analisar(con, conf["regras"])
    log.info("Alertas: %(novos)d novos, %(ativos)d ativos, %(inativos)d inativos", resumo)
    con.close()


def cmd_publicar(args: argparse.Namespace) -> None:
    conf = cfg.carregar_config()
    dry_run = args.dry_run or not publicacao.publicacao_ativada()
    publicadores = [
        p
        for p in publicacao.criar_publicadores(conf["site"]["nome"])
        if args.rede in (None, p.rede)
    ]
    con = db.conectar(cfg.caminho_banco())
    resultados = publicacao.publicar(con, publicadores, conf, dry_run=dry_run, limite=args.limite)
    con.close()
    modo = "DRY-RUN (nada foi enviado)" if dry_run else "PUBLICAÇÃO REAL"
    print(f"== {modo}: {len(resultados)} post(s) ==\n")
    for r in resultados:
        situacao = "ok" if r.sucesso else f"ERRO: {r.erro}"
        print(f"[{r.rede}] {r.codigo} ({situacao}) {r.url or ''}\n{r.texto}\n")


def cmd_exportar(args: argparse.Namespace) -> None:
    con = db.conectar(cfg.caminho_banco())
    resumo = exportar(
        con,
        cfg.carregar_config(),
        destino=Path(args.destino),
        pasta_respostas=cfg.RAIZ / "respostas",
    )
    con.close()
    log.info(
        "Exportados: %(alertas)d alertas, %(parlamentares)d parlamentares, "
        "%(fornecedores)d fornecedores",
        resumo,
    )


def cmd_resposta(args: argparse.Namespace) -> None:
    resposta = resp.Resposta(
        alerta=args.alerta,
        recebida_em=args.recebida_em or date.today(),
        autor=args.autor,
        texto=Path(args.arquivo).read_text(encoding="utf-8") if args.arquivo else args.texto,
        documento=args.documento,
    )
    print(f"Resposta registrada em {resp.registrar(cfg.RAIZ / 'respostas', resposta)}")


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serenata", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("coletar", help="baixa despesas da Câmara e do Senado")
    p.add_argument("--ano", type=int, nargs="+", default=[date.today().year])
    p.add_argument("--casa", choices=["camara", "senado", "todas"], default="todas")
    p.set_defaults(func=cmd_coletar)

    p = sub.add_parser("analisar", help="aplica as regras e atualiza a tabela de alertas")
    p.add_argument(
        "--sem-cnpj", action="store_true", help="não consulta a BrasilAPI (usa só o cache)"
    )
    p.set_defaults(func=cmd_analisar)

    p = sub.add_parser("publicar", help="publica alertas nas redes (padrão: dry-run)")
    p.add_argument(
        "--dry-run", action="store_true", help="só mostra os posts (já é o padrão sem PUBLICAR=1)"
    )
    p.add_argument("--rede", choices=["x", "bluesky", "mastodon"], help="só esta rede")
    p.add_argument("--limite", type=int, help="máximo de posts por rede nesta execução")
    p.set_defaults(func=cmd_publicar)

    p = sub.add_parser("exportar", help="gera os JSONs do site")
    p.add_argument("--destino", default=str(cfg.RAIZ / "site" / "src" / "data"))
    p.set_defaults(func=cmd_exportar)

    p = sub.add_parser("resposta", help="registra uma justificativa recebida (direito de resposta)")
    p.add_argument("--alerta", required=True, help="código, ex.: A-2026-00123")
    p.add_argument("--autor", required=True, help="quem enviou, ex.: 'Gabinete do parlamentar'")
    texto = p.add_mutually_exclusive_group(required=True)
    texto.add_argument("--texto")
    texto.add_argument("--arquivo", help="arquivo .txt com o texto da resposta")
    p.add_argument("--documento", help="link para documento enviado junto")
    p.add_argument("--recebida-em", type=date.fromisoformat, help="AAAA-MM-DD (padrão: hoje)")
    p.set_defaults(func=cmd_resposta)

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
