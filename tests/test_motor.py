import httpx
import pytest

from ofertas import motor
from ofertas.cli import main, pesos, presentar
from ofertas.modelos import Oferta, Tienda, agrupar_por_ean
from ofertas.tiendas import TIENDAS, seleccionar

A = Tienda("a", "Tienda A", "https://a.example")
B = Tienda("b", "Tienda B", "https://b.example")
C = Tienda("c", "Tienda C", "https://c.example")


def prod(nombre, precio, lista=None, ean="", marca="ACME"):
    return {
        "productName": nombre,
        "brand": marca,
        "link": "https://x.example/p",
        "items": [
            {
                "ean": ean,
                "sellers": [
                    {
                        "sellerName": "v",
                        "commertialOffer": {
                            "Price": precio,
                            "ListPrice": lista or precio,
                            "AvailableQuantity": 3,
                        },
                    }
                ],
            }
        ],
    }


CATALOGO = {
    "a.example": [
        prod("Audífonos Sony WH-1000", 900000, 1200000, ean="490"),
        prod("Estuche para audífonos", 20000),
    ],
    "b.example": [prod("Audifonos SONY wh-1000", 850000, ean="490")],
}


def transporte():
    def manejador(peticion):
        if peticion.url.host == "c.example":
            return httpx.Response(403, text="Access Denied")
        return httpx.Response(200, json=CATALOGO[peticion.url.host])

    return httpx.MockTransport(manejador)


def oferta(nombre, marca=""):
    return Oferta("a", "A", nombre, marca, 1.0, 1.0, "u")


@pytest.mark.parametrize(
    ("nombre", "consulta", "esperado"),
    [
        ("Audífonos Sony WH-1000", "audifonos sony", True),
        ("AUDIFONOS inalámbricos", "Audífonos", True),
        ("Camiseta deportiva", "camisetas", True),
        ("Estuche para audífonos", "audifonos sony", False),
        ("Morral", "morral totto", False),
    ],
)
def test_relevancia(nombre, consulta, esperado):
    assert motor.es_relevante(oferta(nombre), consulta) is esperado


def test_relevancia_cuenta_la_marca():
    assert motor.es_relevante(oferta("Morral escolar", "TOTTO"), "morral totto")


async def test_busca_filtra_y_ordena_por_precio():
    resultado = await motor.buscar("audifonos sony", [A, B], transporte=transporte())
    assert [o.precio for o in resultado.ofertas] == [850000, 900000]
    assert [o.tienda_id for o in resultado.ofertas] == ["b", "a"]


async def test_una_tienda_caida_no_tumba_la_busqueda():
    resultado = await motor.buscar("audifonos sony", [A, B, C], transporte=transporte())
    assert len(resultado.ofertas) == 2
    assert [t.tienda_id for t in resultado.tiendas_fallidas] == ["c"]
    assert "403" in resultado.tiendas_fallidas[0].error
    estado_a = resultado.tiendas_consultadas[0]
    assert (estado_a.encontrados, estado_a.relevantes) == (2, 1)


async def test_filtros_de_descuento_precio_y_orden():
    sin_filtro = await motor.buscar("audifonos", [A, B], filtrar=False, transporte=transporte())
    assert len(sin_filtro.ofertas) == 3
    rebajados = await motor.buscar(
        "audifonos sony", [A, B], descuento_minimo=10, transporte=transporte()
    )
    assert [o.tienda_id for o in rebajados.ofertas] == ["a"]
    baratos = await motor.buscar(
        "audifonos sony", [A, B], precio_maximo=870000, transporte=transporte()
    )
    assert [o.tienda_id for o in baratos.ofertas] == ["b"]
    por_descuento = await motor.buscar(
        "audifonos sony", [A, B], orden="descuento", transporte=transporte()
    )
    assert por_descuento.ofertas[0].tienda_id == "a"


async def test_empareja_por_codigo_de_barras_y_presenta():
    resultado = await motor.buscar("audifonos sony", [A, B, C], transporte=transporte())
    grupos = agrupar_por_ean(resultado.ofertas)
    assert list(grupos) == ["490"]
    assert [o.tienda_id for o in grupos["490"]] == ["b", "a"]

    texto = presentar(resultado, 10)
    assert "$850.000" in texto
    assert "25%" in texto
    assert "Mismo producto en varias tiendas" in texto
    assert "FALLÓ" in texto
    assert chr(0x2014) not in texto

    datos = resultado.a_dict()
    assert datos["ofertas"][0]["descuento_pct"] == 0.0
    assert datos["mismo_producto"][0]["ean"] == "490"
    assert datos["tiendas_fallidas"][0]["tienda_id"] == "c"


def test_un_solo_codigo_no_forma_grupo():
    assert agrupar_por_ean([oferta("x")]) == {}


def test_pesos():
    assert pesos(1234567.4) == "$1.234.567"
    assert pesos(900) == "$900"


def test_seleccionar_tiendas():
    assert [t.id for t in seleccionar(["totto", "nike"])] == ["totto", "nike"]
    assert len(TIENDAS) == 57
    assert len(seleccionar(None)) == 47
    assert "mercadolibre" not in {t.id for t in seleccionar(None)}
    assert "amazon" not in {t.id for t in seleccionar(None)}
    assert len(seleccionar(None, con_navegador=True)) == 57
    assert [t.id for t in seleccionar(["amazon"])] == ["amazon"]
    with pytest.raises(ValueError, match="desconocida"):
        seleccionar(["noexiste"])


def test_cli_valida_entradas(capsys):
    assert main(["buscar", "x", "--tiendas", "noexiste"]) == 2
    assert main(["buscar", "   "]) == 2
    assert main(["buscar", "x", "--max", "0"]) == 2
    assert main(["tiendas"]) == 0
    salida = capsys.readouterr().out
    assert "olimpica" in salida
    assert "MercadoLibre" in salida


@pytest.mark.parametrize(
    ("nombre", "consulta", "relevante"),
    [
        ("Broca para Taladro Percutor para Mampostería", "taladro percutor", False),
        ("Taladro Percutor Inalámbrico 20V", "taladro percutor", True),
        ("Funda Urban para Portátil 15,6", "portatil", False),
        ("Cargador de Corriente para Portatil", "portatil", False),
        ("Soporte para televisores de 32 a 55", "televisor 55", False),
        ("Funda para portátil", "funda portatil", True),
        ("Morral para portátil", "morral", True),
        ("Tenis para hombre", "tenis hombre", True),
    ],
)
def test_los_accesorios_de_lo_buscado_no_son_relevantes(nombre, consulta, relevante):
    assert motor.es_relevante(oferta(nombre), consulta) is relevante


async def test_una_tienda_que_cae_por_la_red_se_reintenta_al_final():
    intentos = {"a.example": 0, "b.example": 0}

    def manejador(peticion):
        intentos[peticion.url.host] += 1
        if peticion.url.host == "a.example" and intentos["a.example"] <= 2:
            raise httpx.ConnectError("ráfaga de red")
        if peticion.url.host == "b.example":
            raise httpx.ConnectError("caída de verdad")
        return httpx.Response(200, json=CATALOGO["a.example"])

    resultado = await motor.buscar(
        "audifonos sony", [A, B], transporte=httpx.MockTransport(manejador)
    )
    # A falló dos veces (petición y su reintento inmediato) y respondió en la segunda vuelta.
    assert [t.tienda_id for t in resultado.tiendas_consultadas] == ["a"]
    assert len(resultado.ofertas) == 1
    # B sigue caída: queda reportada, con cuatro intentos en total y no más.
    assert resultado.tiendas_fallidas[0].tienda_id == "b"
    assert intentos["b.example"] == 4


async def test_un_rechazo_de_la_tienda_no_se_reintenta():
    visitas = []

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return httpx.Response(403, text="Access Denied")

    resultado = await motor.buscar("x", [C], transporte=httpx.MockTransport(manejador))
    assert "403" in resultado.tiendas_fallidas[0].error
    assert len(visitas) == 1
