import httpx
import pytest

from ofertas.conectores import vtex
from ofertas.modelos import Tienda

TIENDA = Tienda("demo", "Demo", "https://demo.example")


def producto(nombre="Morral Totto Azul", marca="TOTTO", items=None, **extra):
    base = {
        "productId": "1",
        "productName": nombre,
        "brand": marca,
        "link": "https://demo.example/morral/p",
        "items": items if items is not None else [variante()],
    }
    base.update(extra)
    return base


def variante(ean="7701234567890", precio=80000.0, lista=100000.0, existencias=5, vendedor="Demo"):
    return {
        "itemId": "10",
        "ean": ean,
        "images": [{"imageUrl": "https://demo.example/img.jpg"}],
        "sellers": [
            {
                "sellerName": vendedor,
                "commertialOffer": {
                    "Price": precio,
                    "ListPrice": lista,
                    "AvailableQuantity": existencias,
                },
            }
        ],
    }


def test_interpreta_precio_descuento_y_codigo():
    oferta = vtex.interpretar_producto(producto(), TIENDA)
    assert oferta.precio == 80000.0
    assert oferta.precio_lista == 100000.0
    assert oferta.descuento_pct == 20.0
    assert oferta.ean == "7701234567890"
    assert oferta.url == "https://demo.example/morral/p"
    assert oferta.imagen == "https://demo.example/img.jpg"


def test_elige_la_variante_disponible_mas_barata():
    items = [
        variante(ean="111", precio=90000.0),
        variante(ean="222", precio=70000.0),
        variante(ean="333", precio=50000.0, existencias=0),
    ]
    oferta = vtex.interpretar_producto(producto(items=items), TIENDA)
    assert oferta.precio == 70000.0
    assert oferta.ean == "222"
    assert oferta.eans == ["111", "222", "333"]


def test_descarta_agotados_y_precio_cero():
    agotado = producto(items=[variante(existencias=0)])
    sin_precio = producto(items=[variante(precio=0.0, lista=0.0)])
    assert vtex.interpretar_producto(agotado, TIENDA) is None
    assert vtex.interpretar_producto(sin_precio, TIENDA) is None
    assert vtex.interpretar_producto(agotado, TIENDA, incluir_agotados=True) is not None


def test_sin_precio_de_lista_no_hay_descuento():
    oferta = vtex.interpretar_producto(producto(items=[variante(lista=0.0)]), TIENDA)
    assert oferta.precio_lista == oferta.precio
    assert oferta.descuento_pct == 0.0


def test_la_url_usa_el_dominio_publico_de_la_tienda():
    interno = producto(link="https://secure.demo.example/morral-azul/p", linkText="morral-azul")
    assert vtex.interpretar_producto(interno, TIENDA).url == "https://demo.example/morral-azul/p"


async def test_los_espacios_viajan_como_porcentaje_veinte():
    crudas = []

    def manejador(peticion):
        crudas.append(peticion.url.raw_path.decode())
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejador)) as cliente:
        await vtex.buscar(cliente, TIENDA, "aceite de girasol", 10)
    assert "ft=aceite%20de%20girasol" in crudas[0]


def test_producto_sin_items_no_revienta():
    assert vtex.interpretar_producto({"productName": "x"}, TIENDA) is None


async def _buscar(manejador, limite=50):
    async with httpx.AsyncClient(transport=httpx.MockTransport(manejador)) as cliente:
        return await vtex.buscar(cliente, TIENDA, "morral", limite)


async def test_buscar_lee_el_total_de_la_cabecera():
    def manejador(peticion):
        assert peticion.url.params["ft"] == "morral"
        return httpx.Response(206, json=[producto()], headers={"resources": "0-49/334"})

    ofertas, recibidos, total = await _buscar(manejador)
    assert len(ofertas) == 1
    assert recibidos == 1
    assert total == 334


async def test_buscar_pagina_de_a_cincuenta():
    rangos = []

    def manejador(peticion):
        desde, hasta = int(peticion.url.params["_from"]), int(peticion.url.params["_to"])
        rangos.append((desde, hasta))
        cuerpo = [producto(productId=str(i)) for i in range(desde, hasta + 1)]
        return httpx.Response(206, json=cuerpo, headers={"resources": f"{desde}-{hasta}/500"})

    ofertas, recibidos, _ = await _buscar(manejador, limite=120)
    assert rangos == [(0, 49), (50, 99), (100, 119)]
    assert recibidos == 120
    assert len(ofertas) == 120


@pytest.mark.parametrize(
    ("respuesta", "fragmento"),
    [
        (httpx.Response(403, text="Access Denied"), "HTTP 403"),
        (httpx.Response(200, text="<html>reto</html>"), "no devolvió JSON"),
        (httpx.Response(200, json={"error": "x"}), "forma inesperada"),
    ],
)
async def test_buscar_explica_por_que_fallo(respuesta, fragmento):
    with pytest.raises(vtex.ErrorTienda, match=fragmento):
        await _buscar(lambda peticion: respuesta)


async def test_buscar_traduce_el_tiempo_agotado():
    def manejador(peticion):
        raise httpx.ReadTimeout("lento")

    with pytest.raises(vtex.ErrorTienda, match="a tiempo"):
        await _buscar(manejador)
