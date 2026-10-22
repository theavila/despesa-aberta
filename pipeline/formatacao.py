"""Formatação de valores e datas no padrão brasileiro."""

from datetime import date

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip
DIAS_DA_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]  # fmt: skip


def reais(valor: float) -> str:
    """1234.5 -> 'R$ 1.234,50'"""
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if valor < 0 else ''}R$ {texto}"


def numero(valor: float, casas: int = 1) -> str:
    """3.25 -> '3,2'"""
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def data_curta(d: date | None) -> str:
    """date(2026, 3, 9) -> '09/03/2026'"""
    return d.strftime("%d/%m/%Y") if d else "sem data"


def data_por_extenso(d: date) -> str:
    """date(2026, 10, 22) -> 'quinta-feira, 22 de outubro de 2026'"""
    return f"{DIAS_DA_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def cnpj_cpf(documento: str | None) -> str:
    """Formata 14 dígitos como CNPJ e 11 como CPF (parcialmente oculto)."""
    if not documento:
        return "não informado"
    if len(documento) == 14:
        d = documento
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(documento) == 11:
        # CPF de pessoa física: só os dígitos centrais, como no Portal da Transparência.
        return f"***.{documento[3:6]}.{documento[6:9]}-**"
    return documento
