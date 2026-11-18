import os

from ofertas.entorno import cargar_env


def test_carga_claves_e_ignora_vacias_y_comentarios(tmp_path, monkeypatch):
    for clave in ("OFERTAS_A", "OFERTAS_B", "OFERTAS_C", "OFERTAS_D"):
        monkeypatch.delenv(clave, raising=False)
    monkeypatch.setenv("OFERTAS_D", "del-sistema")
    archivo = tmp_path / ".env"
    archivo.write_text(
        "# comentario\nOFERTAS_A=123\nOFERTAS_B=\n export OFERTAS_C = \"con comillas\" \n"
        "OFERTAS_D=del-archivo\nlinea sin igual\n",
        encoding="utf-8",
    )
    cargadas = cargar_env(archivo)
    try:
        assert cargadas == ["OFERTAS_A", "OFERTAS_C"]
        assert os.environ["OFERTAS_A"] == "123"
        assert os.environ["OFERTAS_C"] == "con comillas"
        assert "OFERTAS_B" not in os.environ
        assert os.environ["OFERTAS_D"] == "del-sistema"
    finally:
        os.environ.pop("OFERTAS_A", None)
        os.environ.pop("OFERTAS_C", None)


def test_sin_archivo_no_falla(tmp_path):
    assert cargar_env(tmp_path / "no-existe.env") == []
