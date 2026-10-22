from datetime import date

from pipeline.regras.base import Contexto
from pipeline.regras.feriados import feriados_nacionais, pascoa
from pipeline.regras.r05_fim_de_semana import REGRA
from tests.fabrica import despesa, despesas

ESCRITORIO = "Manutenção de escritório de apoio à atividade parlamentar"
PARAMS = {"valor_minimo": 100.0, "categorias": [ESCRITORIO]}


def test_pascoa_e_feriados():
    assert pascoa(2026) == date(2026, 4, 5)
    assert pascoa(2027) == date(2027, 3, 28)
    feriados = feriados_nacionais(2026)
    assert feriados[date(2026, 4, 3)] == "Sexta-feira Santa"
    assert date(2026, 11, 20) in feriados
    assert date(2023, 11, 20) not in feriados_nacionais(2023)


def test_marca_sabado_domingo_e_feriado():
    df = despesas(
        despesa(id="sab", categoria=ESCRITORIO, valor=200.0, data=date(2026, 3, 14)),
        despesa(id="dom", categoria=ESCRITORIO, valor=200.0, data=date(2026, 3, 15)),
        despesa(id="tir", categoria=ESCRITORIO, valor=200.0, data=date(2026, 4, 21)),  # terça
        despesa(id="ter", categoria=ESCRITORIO, valor=200.0, data=date(2026, 3, 17)),
    )
    r = REGRA.aplicar(df, PARAMS, Contexto()).sort("despesa_id")
    assert r["despesa_id"].to_list() == ["dom", "sab", "tir"]
    detalhes = dict(zip(r["despesa_id"], r["detalhe"], strict=True))
    assert detalhes["sab"] == ("Documento de despesa de expediente emitido em 14/03/2026, sábado.")
    assert detalhes["tir"].endswith("21/04/2026, feriado nacional (Tiradentes).")


def test_ignora_outras_categorias_valor_baixo_e_sem_data():
    df = despesas(
        despesa(categoria="Combustíveis e lubrificantes", valor=200.0, data=date(2026, 3, 14)),
        despesa(categoria=ESCRITORIO, valor=99.0, data=date(2026, 3, 14)),
        despesa(categoria=ESCRITORIO, valor=200.0, data=None),
    )
    assert REGRA.aplicar(df, PARAMS, Contexto()).is_empty()
