from pipeline import db, estado

ALERTA = (
    "INSERT INTO alertas VALUES ('A-2026-00001', 'R02_duplicidade', 'd1', 100, 'x', true, ?, ?)"
)


def test_salvar_e_restaurar(tmp_path):
    origem = db.conectar(":memory:")
    agora = db.agora()
    origem.execute(ALERTA, [agora, agora])
    origem.execute(
        "INSERT INTO publicacoes VALUES ('x', 'A-2026-00001', ?, true, '1', 'u', 'texto', NULL)",
        [agora],
    )
    assert estado.salvar(origem, tmp_path) == {"alertas": 1, "publicacoes": 1, "cnpj_cache": 0}

    destino = db.conectar(":memory:")
    destino.execute(
        "INSERT INTO alertas VALUES ('A-2026-00099', 'R01_refeicao_alta', 'z', 1, 'y', true, ?, ?)",
        [agora, agora],
    )
    estado.restaurar(destino, tmp_path)
    assert destino.execute("SELECT codigo FROM alertas").fetchall() == [("A-2026-00001",)]
    assert db.escalar(destino, "SELECT texto FROM publicacoes") == "texto"


def test_restaurar_sem_arquivos_nao_apaga(tmp_path):
    con = db.conectar(":memory:")
    agora = db.agora()
    con.execute(ALERTA, [agora, agora])
    assert estado.restaurar(con, tmp_path / "vazia") == {}
    assert db.escalar(con, "SELECT count(*) FROM alertas") == 1
