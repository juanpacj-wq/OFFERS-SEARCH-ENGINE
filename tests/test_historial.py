from datetime import UTC, datetime, timedelta

import httpx
import pytest

from ofertas import historial
from ofertas.cli import main
from ofertas.modelos import Oferta, Resultado

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def oferta(precio, lista=None, url="https://t.example/tv-55/p?utm=x#frag", tienda="t"):
    return Oferta(tienda, "Tienda T", "Televisor 55", "ACME", precio, lista or precio, url,
                  ean="7700000000001")


def resultado(*ofertas, consulta="televisor"):
    return Resultado(consulta, list(ofertas), [])


@pytest.fixture
def conexion(tmp_path):
    con = historial.conectar(tmp_path / "h.db")
    yield con
    con.close()


def test_la_clave_ignora_parametros_y_mayusculas():
    a = oferta(1, url="https://T.example/TV-55/p?utm=1#x")
    b = oferta(1, url="https://t.example/tv-55/p/")
    assert historial.clave_de(a) == historial.clave_de(b) == "t.example/tv-55/p"


def test_primera_vez_no_hay_contexto(conexion):
    assert historial.contexto_de(conexion, oferta(100)) is None


def test_registra_y_no_repite_el_mismo_precio_en_pocas_horas(conexion):
    assert historial.registrar(conexion, resultado(oferta(100)), T0) == 1
    assert historial.registrar(conexion, resultado(oferta(100)), T0 + timedelta(hours=1)) == 0
    assert historial.registrar(conexion, resultado(oferta(90)), T0 + timedelta(hours=2)) == 1
    assert historial.registrar(conexion, resultado(oferta(90)), T0 + timedelta(hours=9)) == 1
    contexto = historial.contexto_de(conexion, oferta(90))
    assert (contexto.veces, contexto.minimo, contexto.maximo) == (3, 90, 100)
    assert contexto.ultimo_precio == 90


def test_productos_iguales_de_tiendas_distintas_no_se_mezclan(conexion):
    historial.registrar(conexion, resultado(oferta(100), oferta(80, tienda="u")), T0)
    assert historial.contexto_de(conexion, oferta(1)).minimo == 100
    assert historial.contexto_de(conexion, oferta(1, tienda="u")).minimo == 80


def test_lectura_minimo_historico_y_cambio(conexion):
    historial.registrar(conexion, resultado(oferta(100)), T0)
    actual = oferta(80)
    lectura = historial.leer(actual, historial.contexto_de(conexion, actual))
    assert "el precio más bajo registrado" in lectura
    assert "bajó 20%" in lectura
    cara = oferta(120)
    lectura = historial.leer(cara, historial.contexto_de(conexion, cara))
    assert "se ha visto más barato: $100" in lectura
    assert "subió 20%" in lectura


def test_lectura_detecta_un_descuento_que_nunca_se_vio(conexion):
    for dia in range(4):
        momento = T0 + timedelta(days=3 * dia)
        historial.registrar(conexion, resultado(oferta(100 + dia, 200)), momento)
    actual = oferta(100, 200)
    lectura = historial.leer(actual, historial.contexto_de(conexion, actual))
    assert "descuento dudoso: nunca se vio a $200" in lectura
    assert "máximo registrado es $103" in lectura


def test_lectura_confirma_el_precio_de_lista_cuando_si_se_vio(conexion):
    historial.registrar(conexion, resultado(oferta(200)), T0)
    for dia in (4, 8, 12):
        historial.registrar(conexion, resultado(oferta(150, 200)), T0 + timedelta(days=dia))
    actual = oferta(150, 200)
    assert "sí se llegó a ver" in historial.leer(actual, historial.contexto_de(conexion, actual))


def test_con_poco_historial_no_juzga_el_descuento(conexion):
    historial.registrar(conexion, resultado(oferta(100, 200)), T0)
    actual = oferta(100, 200)
    lectura = historial.leer(actual, historial.contexto_de(conexion, actual))
    assert "dudoso" not in lectura and "llegó a ver" not in lectura


def test_anotar_usa_lo_previo_a_la_busqueda_actual(conexion):
    historial.registrar(conexion, resultado(oferta(100)), T0)
    actual = resultado(oferta(90), oferta(50, url="https://t.example/otro/p"))
    historial.anotar(conexion, actual)
    assert actual.ofertas[0].historial["veces_visto"] == 1
    assert actual.ofertas[0].historial["precio_anterior"] == 100
    assert actual.ofertas[1].historial is None
    assert actual.a_dict()["ofertas"][0]["historial"]["minimo_visto"] == 100


def test_buscar_productos_por_palabras(conexion):
    historial.registrar(conexion, resultado(oferta(100)), T0)
    historial.registrar(conexion, resultado(oferta(90)), T0 + timedelta(days=1))
    (producto,) = historial.buscar_productos(conexion, "televisor acme")
    assert (producto["veces"], producto["minimo"], producto["maximo"]) == (2, 90, 100)
    assert [o["precio"] for o in producto["observaciones"]] == [100, 90]
    assert historial.buscar_productos(conexion, "nevera") == []


def test_seguimientos_crear_listar_anotar_y_quitar(conexion):
    nuevo = historial.seguir(conexion, " televisor 55 ", ["olimpica", "jumbo"], 1500000, T0)
    assert (nuevo.consulta, nuevo.tiendas, nuevo.precio_objetivo) == (
        "televisor 55", ["olimpica", "jumbo"], 1500000,
    )
    historial.anotar_revision(conexion, nuevo, oferta(1400000), T0)
    (guardado,) = historial.seguimientos(conexion)
    assert (guardado.ultimo_precio, guardado.ultima_tienda) == (1400000, "Tienda T")
    historial.anotar_revision(conexion, guardado, None, T0 + timedelta(days=1))
    assert historial.seguimientos(conexion)[0].ultimo_precio == 1400000
    assert historial.dejar_de_seguir(conexion, nuevo.id)
    assert not historial.dejar_de_seguir(conexion, nuevo.id)


# --- comando ----------------------------------------------------------------


@pytest.fixture
def tienda_simulada(tmp_path, monkeypatch):
    """Apunta el historial a una carpeta temporal y simula la tienda Totto."""
    monkeypatch.setenv("OFERTAS_DATOS", str(tmp_path))
    precio = {"valor": 100000}

    def manejador(peticion):
        producto = {
            "productName": "Morral Totto Azul", "brand": "Totto", "linkText": "morral-azul",
            "items": [{"ean": "770", "sellers": [{"sellerName": "Totto", "commertialOffer": {
                "Price": precio["valor"], "ListPrice": 150000, "AvailableQuantity": 3}}]}],
        }
        return httpx.Response(200, json=[producto])

    real = httpx.AsyncClient

    def cliente_simulado(**opciones):
        opciones.pop("verify", None)
        opciones["transport"] = httpx.MockTransport(manejador)
        return real(**opciones)

    monkeypatch.setattr(httpx, "AsyncClient", cliente_simulado)
    return precio


def test_buscar_guarda_y_la_segunda_vez_muestra_el_historial(tienda_simulada, capsys):
    assert main(["buscar", "morral totto", "--tiendas", "totto"]) == 0
    assert "Historial" not in capsys.readouterr().out
    tienda_simulada["valor"] = 80000
    assert main(["buscar", "morral totto", "--tiendas", "totto"]) == 0
    salida = capsys.readouterr().out
    assert "Historial (visto 1 vez desde" in salida
    assert "bajó 20% frente a $100.000" in salida
    assert main(["historial", "morral"]) == 0
    salida = capsys.readouterr().out
    assert "mínimo $80.000, máximo $100.000" in salida


def test_sin_historial_no_guarda_nada(tienda_simulada, capsys):
    assert main(["buscar", "morral totto", "--tiendas", "totto", "--sin-historial"]) == 0
    capsys.readouterr()
    assert main(["historial", "morral"]) == 0
    assert "No hay precios guardados" in capsys.readouterr().out


def test_seguir_revisar_y_dejar(tienda_simulada, capsys):
    assert main(["seguir", "morral totto", "--objetivo", "90000", "--tiendas", "totto"]) == 0
    assert main(["seguir", "x", "--tiendas", "noexiste"]) == 2
    assert main(["seguir", "x", "--objetivo", "0"]) == 2
    capsys.readouterr()

    assert main(["revisar"]) == 0
    salida = capsys.readouterr().out
    assert "$100.000 en Totto" in salida and "LLEGÓ" not in salida

    tienda_simulada["valor"] = 85000
    assert main(["revisar"]) == 0
    salida = capsys.readouterr().out
    assert "¡LLEGÓ AL OBJETIVO!" in salida
    assert "bajó 15.0% frente a $100.000" in salida

    assert main(["seguimientos"]) == 0
    assert "objetivo $90.000" in capsys.readouterr().out
    assert main(["dejar", "1"]) == 0
    assert main(["dejar", "1"]) == 2
    capsys.readouterr()
    assert main(["revisar"]) == 0
    assert "No sigues ninguna búsqueda" in capsys.readouterr().out
