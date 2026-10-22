"""Feriados nacionais (Lei 662/1949, Lei 6.802/1980, Lei 14.759/2023 e Sexta-feira Santa)."""

from datetime import date, timedelta
from functools import cache

FIXOS = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (12, 25): "Natal",
}


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


@cache
def feriados_nacionais(ano: int) -> dict[date, str]:
    feriados = {date(ano, m, d): nome for (m, d), nome in FIXOS.items()}
    if ano >= 2024:
        feriados[date(ano, 11, 20)] = "Dia Nacional de Zumbi e da Consciência Negra"
    feriados[pascoa(ano) - timedelta(days=2)] = "Sexta-feira Santa"
    return feriados


def feriado(d: date) -> str | None:
    return feriados_nacionais(d.year).get(d)
