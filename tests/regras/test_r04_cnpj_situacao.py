from datetime import date

import polars as pl

from pipeline.regras.base import ESQUEMA_CNPJ, Contexto
from pipeline.regras.r04_cnpj_situacao import REGRA
from tests.fabrica import despesa, despesas

DIA = date(2026, 5, 15)


def _contexto(*linhas: dict) -> Contexto:
    return Contexto(cnpjs=pl.DataFrame(list(linhas), schema=ESQUEMA_CNPJ))


def _cnpj(cnpj, situacao="ATIVA", data_situacao=date(2010, 1, 1), data_inicio=date(2010, 1, 1)):
    return {
        "cnpj": cnpj,
        "situacao": situacao,
        "data_situacao": data_situacao,
        "data_inicio": data_inicio,
    }


def test_cnpj_aberto_depois_da_despesa():
    ctx = _contexto(_cnpj("11111111000111", data_inicio=date(2026, 6, 1)))
    r = REGRA.aplicar(
        despesas(despesa(id="a", fornecedor_cnpj_cpf="11111111000111", data=DIA)), {}, ctx
    )
    assert r["despesa_id"].to_list() == ["a"]
    assert r["detalhe"][0] == (
        "Segundo a Receita Federal, o CNPJ do fornecedor começou a funcionar em 01/06/2026, "
        "depois da data da despesa (15/05/2026)."
    )


def test_cnpj_inativo_antes_da_despesa():
    ctx = _contexto(_cnpj("22222222000122", situacao="BAIXADA", data_situacao=date(2025, 1, 2)))
    r = REGRA.aplicar(
        despesas(despesa(id="b", fornecedor_cnpj_cpf="22222222000122", data=DIA)), {}, ctx
    )
    assert r["despesa_id"].to_list() == ["b"]
    assert "situação 'BAIXADA' desde 02/01/2025" in r["detalhe"][0]


def test_nao_marca_empresa_ativa_nem_baixada_depois_da_despesa():
    ctx = _contexto(
        _cnpj("33333333000133"),
        _cnpj("44444444000144", situacao="BAIXADA", data_situacao=date(2026, 9, 1)),
    )
    df = despesas(
        despesa(fornecedor_cnpj_cpf="33333333000133", data=DIA),
        despesa(fornecedor_cnpj_cpf="44444444000144", data=DIA),
    )
    assert REGRA.aplicar(df, {}, ctx).is_empty()


def test_ignora_cpf_cnpj_sem_consulta_e_despesa_sem_data():
    ctx = _contexto(_cnpj("55555555000155", situacao="NULA"))
    df = despesas(
        despesa(fornecedor_cnpj_cpf="12345678901", data=DIA),  # CPF
        despesa(fornecedor_cnpj_cpf="66666666000166", data=DIA),  # ainda não consultado
        despesa(fornecedor_cnpj_cpf="55555555000155", data=None),
    )
    assert REGRA.aplicar(df, {}, ctx).is_empty()
