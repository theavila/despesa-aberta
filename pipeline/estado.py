"""Estado que não pode ser recriado a partir das fontes oficiais.

Despesas e parlamentares são baixados de novo a cada execução; já os códigos dos
alertas, o log de publicações e o cache de CNPJ precisam sobreviver entre execuções
(no GitHub Actions, num branch `data`). Ficam em Parquet, um arquivo por tabela.
"""

from pathlib import Path

import duckdb

TABELAS = ["alertas", "publicacoes", "cnpj_cache"]


def salvar(con: duckdb.DuckDBPyConnection, pasta: Path) -> dict[str, int]:
    pasta.mkdir(parents=True, exist_ok=True)
    contagem = {}
    for tabela in TABELAS:
        arquivo = (pasta / f"{tabela}.parquet").as_posix()
        # Ordem fixa: arquivos idênticos quando nada mudou (diffs limpos no git).
        con.execute(f"COPY (SELECT * FROM {tabela} ORDER BY ALL) TO '{arquivo}' (FORMAT parquet)")
        contagem[tabela] = con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]
    return contagem


def restaurar(con: duckdb.DuckDBPyConnection, pasta: Path) -> dict[str, int]:
    """Substitui o conteúdo das tabelas pelo dos arquivos que existirem na pasta."""
    contagem = {}
    for tabela in TABELAS:
        arquivo = pasta / f"{tabela}.parquet"
        if not arquivo.exists():
            continue
        con.execute(f"DELETE FROM {tabela}")
        con.execute(f"INSERT INTO {tabela} SELECT * FROM read_parquet('{arquivo.as_posix()}')")
        contagem[tabela] = con.execute(f"SELECT count(*) FROM {tabela}").fetchall()[0][0]
    return contagem
