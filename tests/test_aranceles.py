import httpx
import pytest

from ofertas import aranceles, historial
from ofertas.cli import main


@pytest.mark.parametrize(
    ("nombre", "categoria", "arancel"),
    [
        ("Computador Portátil LENOVO IdeaPad Slim 3", "computadores portátiles y tabletas", 0.0),
        ("Celular Samsung Galaxy S25 Ultra", "celulares", 0.0),
        ("Televisor Samsung 55 Pulgadas", "televisores", 0.11),
        ("Taladro Percutor Dewalt 20V", "herramientas eléctricas", 0.0),
        ("Tenis adidas Running Response", "calzado deportivo", 0.15),
        ("Camiseta Polo Hombre", "camisetas", 0.40),
        ("Nevera Haceb No Frost 448 Litros", "neveras", 0.15),
        ("Morral Totto Azul", "morrales y maletas", 0.15),
    ],
)
def test_categoria_y_arancel_por_nombre(nombre, categoria, arancel):
    hallada = aranceles.categoria_de(nombre)
    assert (hallada.nombre, hallada.arancel) == (categoria, arancel)
    valor, fuente = aranceles.arancel_de(nombre)
    assert valor == arancel
    assert "Banco Mundial WITS, 2023" in fuente


def test_gana_la_primera_palabra_y_lo_desconocido_no_tiene_arancel():
    # Es un morral (para portátil), no un portátil.
    assert aranceles.categoria_de("Morral para portátil 15 pulgadas").nombre == "morrales y maletas"
    assert aranceles.categoria_de("Arroz Diana 500 g") is None
    assert aranceles.arancel_de("Arroz Diana 500 g") is None


def test_las_subpartidas_no_se_repiten_y_las_palabras_tampoco():
    palabras = [p for c in aranceles.CATEGORIAS for p in c.palabras]
    assert len(palabras) == len(set(palabras))
    assert all(len(c.hs) == 6 and c.hs.isdigit() and 0 <= c.arancel <= 0.4
               for c in aranceles.CATEGORIAS)


def respuesta_wits(valor):
    return {"dataSets": [{"series": {"0:0:0:0:0": {"observations": {"0": [valor, 0, None]}}}}]}


async def test_actualizar_guarda_el_valor_mas_reciente_y_tiene_prioridad(tmp_path):
    pedidos = []

    def manejador(peticion):
        ruta = peticion.url.path
        pedidos.append(ruta)
        if "/product/852872/" in ruta:
            # El año más reciente aún no está publicado: responde el anterior.
            if ruta.split("/year/")[1].startswith(str(aranceles.datetime.now().year - 1)):
                return httpx.Response(404, text="{}Not Found - NoRecordsFound")
            return httpx.Response(200, json=respuesta_wits(5))
        return httpx.Response(404, text="{}Not Found - NoRecordsFound")

    with historial.abrir(tmp_path / "h.db") as conexion:
        async with httpx.AsyncClient(transport=httpx.MockTransport(manejador)) as cliente:
            resultados = await aranceles.actualizar(cliente, conexion)
        tele = next(r for r in resultados if r["hs"] == "852872")
        assert tele["tabla"] == 0.11 and tele["actual"]["arancel"] == 0.05
        assert next(r for r in resultados if r["hs"] == "847130")["actual"] is None
        # El valor guardado manda sobre la tabla; lo no hallado conserva la tabla.
        valor, fuente = aranceles.arancel_de("Televisor Samsung 55", conexion)
        assert valor == 0.05 and str(tele["actual"]["anio"]) in fuente
        assert aranceles.arancel_de("Portátil Lenovo", conexion)[0] == 0.0


def test_comando_aranceles_lista_la_tabla(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OFERTAS_DATOS", str(tmp_path))
    assert main(["aranceles"]) == 0
    salida = capsys.readouterr().out
    assert "852872  arancel de 11% para televisores (Banco Mundial WITS, 2023)" in salida
    assert "610910  arancel de 40% para camisetas" in salida
