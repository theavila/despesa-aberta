"""Leitura do `config.toml` e dos caminhos definidos por variáveis de ambiente."""

import os
import tomllib
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent


def caminho_config() -> Path:
    return Path(os.environ.get("SERENATA_CONFIG", RAIZ / "config.toml"))


def caminho_banco() -> Path:
    return Path(os.environ.get("SERENATA_DB", RAIZ / "data" / "serenata.duckdb"))


def carregar_config(caminho: Path | None = None) -> dict[str, Any]:
    with open(caminho or caminho_config(), "rb") as f:
        return tomllib.load(f)
