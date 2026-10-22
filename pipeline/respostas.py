"""Direito de resposta: justificativas recebidas, uma por arquivo em `respostas/`.

Ficam versionadas no repositório (e não no banco) para que qualquer pessoa veja quando
e como cada resposta foi registrada.
"""

import re
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

PADRAO_CODIGO = r"^A-\d{4}-\d{5}$"


class Resposta(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    alerta: str = Field(pattern=PADRAO_CODIGO)
    recebida_em: date
    autor: str = Field(min_length=3, description="Quem enviou (ex.: 'Gabinete do parlamentar')")
    texto: str = Field(min_length=10)
    documento: HttpUrl | None = None


def carregar(pasta: Path) -> list[Resposta]:
    if not pasta.exists():
        return []
    respostas = []
    for arquivo in sorted(pasta.glob("*.toml")):
        with open(arquivo, "rb") as f:
            respostas.append(Resposta.model_validate(tomllib.load(f)))
    return sorted(respostas, key=lambda r: (r.alerta, r.recebida_em))


def _toml_texto(valor: str) -> str:
    return '"""\n' + valor.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') + '\n"""'


def registrar(pasta: Path, resposta: Resposta) -> Path:
    """Grava `respostas/<alerta>-<n>.toml` (um alerta pode ter mais de uma resposta)."""
    pasta.mkdir(parents=True, exist_ok=True)
    existentes = list(pasta.glob(f"{resposta.alerta}-*.toml"))
    numeros = [int(m.group(1)) for p in existentes if (m := re.search(r"-(\d+)\.toml$", p.name))]
    caminho = pasta / f"{resposta.alerta}-{max(numeros, default=0) + 1}.toml"
    linhas = [
        f'alerta = "{resposta.alerta}"',
        f"recebida_em = {resposta.recebida_em.isoformat()}",
        f"autor = {_toml_linha(resposta.autor)}",
        f"texto = {_toml_texto(resposta.texto)}",
    ]
    if resposta.documento:
        linhas.append(f"documento = {_toml_linha(str(resposta.documento))}")
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def _toml_linha(valor: str) -> str:
    return '"' + " ".join(valor.split()).replace("\\", "\\\\").replace('"', '\\"') + '"'


def como_dict(resposta: Resposta) -> dict[str, Any]:
    return resposta.model_dump(mode="json")
