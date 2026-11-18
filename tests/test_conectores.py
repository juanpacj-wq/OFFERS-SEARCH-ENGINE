"""Pruebas de los conectores que no son VTEX, con respuestas simuladas."""

import json

import httpx
import pytest

from ofertas import motor
from ofertas.conectores import (
    alkosto,
    base,
    falabella,
    hp,
    ikea,
    lenovo,
    mercadolibre,
    rappi,
    samsung,
    woocommerce,
)
from ofertas.modelos import Oferta, Tienda, agrupar_por_ean

FALABELLA = Tienda(
    "falabella", "Falabella", "https://f.example", "falabella",
    busqueda="https://f.example/falabella-co/search?Ntt={q}",
)
HOMECENTER = Tienda(
    "homecenter", "Homecenter", "https://h.example", "falabella",
    busqueda="https://h.example/homecenter-co/search?Ntt={q}",
)
ALKOSTO = Tienda("alkosto", "Alkosto", "https://a.example", "alkosto")
LENOVO = Tienda(
    "lenovo", "Lenovo", "https://l.example/co/es", "lenovo",
    busqueda="https://api.l.example/buscar?text={q}&rows={n}",
)
HP = Tienda("hp", "HP", "https://hp.example", "hp", busqueda="https://hp.example/r/?q={q}")


def pagina_next(page_props):
    cuerpo = json.dumps({"props": {"pageProps": page_props}})
    return f'<html><script id="__NEXT_DATA__" type="application/json">{cuerpo}</script></html>'


async def correr(conector, tienda, manejador, consulta="tv", limite=50, **opciones):
    async with httpx.AsyncClient(transport=httpx.MockTransport(manejador)) as cliente:
        return await conector.buscar(cliente, tienda, consulta, limite, **opciones)


# --- utilidades -------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("$ 2.569.900", 2569900.0), (["1.299.900"], 1299900.0), (2315900, 2315900.0),
     ("19.900,50", 19900.0), ("", 0.0), (None, 0.0), ([], 0.0)],
)
def test_precio_de_texto(texto, esperado):
    assert base.precio_de_texto(texto) == esperado


def test_codigo_de_barras_solo_acepta_forma_de_gtin():
    assert base.codigo_de_barras("199276486547") == "199276486547"
    assert base.codigo_de_barras("D6RR8AT") is None
    assert base.codigo_de_barras("12345") is None


def test_pagina_sin_datos_incrustados_se_reporta_como_bloqueo():
    with pytest.raises(base.ErrorTienda, match="datos incrustados"):
        base.datos_de_next("<html>Access Denied</html>")


def test_empareja_upc_de_doce_digitos_con_ean_de_trece():
    a = Oferta("alkosto", "Alkosto", "x", "", 10.0, 10.0, "u", eans=["199276486547"])
    b = Oferta("jumbo", "Jumbo", "x", "", 9.0, 9.0, "u", eans=["0199276486547"])
    grupos = agrupar_por_ean([a, b])
    assert [o.tienda_id for o in next(iter(grupos.values()))] == ["jumbo", "alkosto"]


# --- Falabella y Homecenter -------------------------------------------------

PRODUCTO_FALABELLA = {
    "productId": "1", "displayName": "Portátil IdeaPad 3", "brand": "Lenovo",
    "url": "https://f.example/falabella-co/product/1/portatil", "sellerName": "Vendedor X",
    "mediaUrls": ["https://img.example/1"],
    "prices": [
        {"type": "cmrPrice", "crossed": False, "price": ["2.429.900"]},
        {"type": "eventPrice", "crossed": False, "price": ["2.569.900"]},
        {"type": "normalPrice", "crossed": True, "price": ["4.599.900"]},
    ],
}
PRODUCTO_HOMECENTER = {
    "productId": "3097627", "displayName": "Taladro Percutor", "brand": "Dewalt",
    "prices": [
        {"type": "INTERNET", "price": "2.315.900", "priceWithoutFormatting": 2315900},
        {"type": "NORMAL", "price": "3.089.900", "priceWithoutFormatting": 3089900},
    ],
}


def test_falabella_separa_precio_publico_de_lista_y_de_tarjeta():
    oferta = falabella.interpretar_producto(PRODUCTO_FALABELLA, FALABELLA)
    assert (oferta.precio, oferta.precio_lista, oferta.precio_tarjeta) == (
        2569900.0, 4599900.0, 2429900.0,
    )
    assert oferta.descuento_pct == 44.1
    assert oferta.existencias is None
    assert oferta.vendedor == "Vendedor X"


def test_falabella_solo_precio_normal_no_inventa_descuento():
    producto = {"displayName": "x", "prices": [{"type": "normalPrice", "price": ["100.000"]}]}
    oferta = falabella.interpretar_producto(producto, FALABELLA)
    assert (oferta.precio, oferta.descuento_pct, oferta.precio_tarjeta) == (100000.0, 0.0, None)
    assert falabella.interpretar_producto({"displayName": "x", "prices": []}, FALABELLA) is None


def test_homecenter_arma_la_url_del_producto():
    oferta = falabella.interpretar_producto(PRODUCTO_HOMECENTER, HOMECENTER)
    assert oferta.precio == 2315900.0
    assert oferta.url == "https://h.example/homecenter-co/product/3097627"


async def test_falabella_lee_resultados_en_las_tres_ubicaciones():
    formas = [
        {"results": [PRODUCTO_FALABELLA], "pagination": {"count": 1, "perPage": 48}},
        {"searchProps": {"searchData": {
            "results": [PRODUCTO_HOMECENTER], "pagination": {"count": 1, "perPage": 40}}}},
        {"searchProps": {"searchData": {"results": []}},
         "categoryProps": {"categoryData": {"results": {
             "results": [PRODUCTO_HOMECENTER], "pagination": {"count": 1, "perPage": 40}}}}},
    ]
    for forma in formas:
        ofertas, recibidos, total = await correr(
            falabella, HOMECENTER, lambda p, f=forma: httpx.Response(200, text=pagina_next(f))
        )
        assert (len(ofertas), recibidos, total) == (1, 1, 1)


async def test_falabella_pagina_solo_si_falta_media_pagina():
    paginas = []

    def manejador(peticion):
        paginas.append(peticion.url.params.get("page", "1"))
        forma = {"results": [PRODUCTO_FALABELLA] * 48, "pagination": {"count": 900, "perPage": 48}}
        return httpx.Response(200, text=pagina_next(forma))

    await correr(falabella, FALABELLA, manejador, limite=50)
    assert paginas == ["1"]
    paginas.clear()
    _, recibidos, total = await correr(falabella, FALABELLA, manejador, limite=100)
    assert paginas == ["1", "2"]
    assert (recibidos, total) == (96, 900)


# --- Alkosto, Ktronix y Alkomprar -------------------------------------------

PAGINA_ALKOSTO = """
<script>ACC.config = { algolia : { badgesStyles: [],
    applicationId : 'APP123', apiKey : 'LLAVE', indexName : 'indicePRD', } }</script>
"""
PRODUCTO_ALKOSTO = {
    "name_text_es": "Computador Portátil LENOVO Ideapad", "marca_text": "LENOVO",
    "lowestprice_double": 2299070.0, "pricevalue_cop_double": 4099000.0,
    "stocklevel_int": 5, "instockflag_boolean": True, "code_string": "199276486547",
    "url_es_string": "/computador/p/199276486547", "img-310wx310h_string": "https://img/x",
}


def test_alkosto_interpreta_producto():
    oferta = alkosto.interpretar_producto(PRODUCTO_ALKOSTO, ALKOSTO)
    assert (oferta.precio, oferta.precio_lista, oferta.existencias) == (2299070.0, 4099000.0, 5)
    assert oferta.url == "https://a.example/computador/p/199276486547"
    assert oferta.eans == ["199276486547"]


def test_alkosto_descarta_agotados():
    agotado = {**PRODUCTO_ALKOSTO, "instockflag_boolean": False}
    assert alkosto.interpretar_producto(agotado, ALKOSTO) is None
    assert alkosto.interpretar_producto(agotado, ALKOSTO, incluir_agotados=True).existencias == 0


def test_alkosto_configuracion_vacia_se_reporta():
    vacia = PAGINA_ALKOSTO.replace("APP123", "").replace("LLAVE", "").replace("indicePRD", "")
    with pytest.raises(base.ErrorTienda, match="configuración"):
        alkosto.leer_configuracion(vacia)


async def test_alkosto_guarda_la_configuracion_y_la_renueva_si_vence(tmp_path, monkeypatch):
    monkeypatch.setenv("OFERTAS_CACHE", str(tmp_path))
    visitas = {"pagina": 0, "buscador": 0}
    llave_valida = "LLAVE"

    def manejador(peticion):
        if peticion.url.host == "a.example":
            visitas["pagina"] += 1
            return httpx.Response(200, text=PAGINA_ALKOSTO.replace("LLAVE", llave_valida))
        visitas["buscador"] += 1
        assert peticion.url.host == "app123-dsn.algolia.net"
        assert peticion.url.path == "/1/indexes/indicePRD/query"
        if peticion.headers["X-Algolia-API-Key"] != llave_valida:
            return httpx.Response(403, json={"message": "Invalid API key"})
        assert json.loads(peticion.content)["query"] == "portatil"
        return httpx.Response(200, json={"hits": [PRODUCTO_ALKOSTO], "nbHits": 46})

    ofertas, recibidos, total = await correr(alkosto, ALKOSTO, manejador, "portatil")
    assert (len(ofertas), recibidos, total) == (1, 1, 46)
    await correr(alkosto, ALKOSTO, manejador, "portatil")
    assert visitas == {"pagina": 1, "buscador": 2}  # la segunda vez usó el archivo

    llave_valida = "NUEVA"  # la tienda cambió la llave: la guardada ya no sirve
    ofertas, _, _ = await correr(alkosto, ALKOSTO, manejador, "portatil")
    assert len(ofertas) == 1
    assert visitas == {"pagina": 2, "buscador": 4}


# --- Lenovo -----------------------------------------------------------------

PRODUCTO_LENOVO = {
    "productName": "E14_CO", "summary": 'ThinkPad E14 Gen 7 (14" AMD)',
    "webPrice": "11177368.00", "finalPrice": "6190061.00", "marketingStatus": "Available",
    "url": "/p/portatiles/thinkpad/21t0",
}


async def test_lenovo_interpreta_y_pide_la_cantidad_indicada():
    def manejador(peticion):
        assert peticion.url.params["rows"] == "10"
        cuerpo = {"data": [{"products": [PRODUCTO_LENOVO]}], "productCount": 133}
        return httpx.Response(200, json={"status": 200, "data": cuerpo})

    ofertas, recibidos, total = await correr(lenovo, LENOVO, manejador, "thinkpad", 10)
    assert (recibidos, total) == (1, 133)
    oferta = ofertas[0]
    assert oferta.nombre == 'ThinkPad E14 Gen 7 (14" AMD)'
    assert (oferta.precio, oferta.precio_lista, oferta.marca) == (6190061.0, 11177368.0, "Lenovo")
    assert oferta.url == "https://l.example/co/es/p/portatiles/thinkpad/21t0"
    assert oferta.categoria == "portatiles thinkpad"


def test_lenovo_descarta_no_disponibles_y_sin_precio():
    agotado = {**PRODUCTO_LENOVO, "marketingStatus": "Unavailable"}
    assert lenovo.interpretar_producto(agotado, LENOVO) is None
    assert lenovo.interpretar_producto({**PRODUCTO_LENOVO, "finalPrice": ""}, LENOVO) is None


async def test_lenovo_forma_inesperada():
    with pytest.raises(base.ErrorTienda, match="forma inesperada"):
        await correr(lenovo, LENOVO, lambda p: httpx.Response(200, json={"status": 500}))


# --- HP ---------------------------------------------------------------------

TARJETA_HP = """
<li class="item product product-item g-col-4">
 <div class="product-item-info simple" data-price-amount="8614000.00" data-brand="elite">
  <img data-src="https://img.example/d6.jpg" src="x.png"/>
  <div class="stock-messaging in-stock-messaging in_stock">Disponible</div>
  <a class="product-item-link" data-gtm-id="s-1" href="https://hp.example/laptop-d6rr8at.html">
   <h2 class="plp-h2-title stellar-title__small"> Portátil HP EliteBook 8 de 14&quot;,
      Intel Core Ultra 7 </h2></a>
  <span data-price-amount="9500000" data-price-type="oldPrice" class="price-wrapper"></span>
  <span data-price-amount="8614000" data-price-type="finalPrice" class="price-wrapper"></span>
 </div></li>
"""


def pagina_hp(*tarjetas):
    return '<body class="catalogsearch-result-index"><ol>' + "".join(tarjetas) + "</ol></body>"


async def test_hp_interpreta_la_tarjeta():
    manejador = lambda p: httpx.Response(200, text=pagina_hp(TARJETA_HP))  # noqa: E731
    ofertas, recibidos, total = await correr(hp, HP, manejador, "portatil")
    assert (recibidos, total) == (1, None)
    oferta = ofertas[0]
    assert oferta.nombre == 'Portátil HP EliteBook 8 de 14", Intel Core Ultra 7'
    assert (oferta.precio, oferta.precio_lista) == (8614000.0, 9500000.0)
    assert oferta.url == "https://hp.example/laptop-d6rr8at.html"
    assert oferta.imagen == "https://img.example/d6.jpg"


async def test_hp_descarta_agotados_y_detecta_pagina_ajena():
    agotada = TARJETA_HP.replace("in_stock", "out_of_stock")
    manejador = lambda p: httpx.Response(200, text=pagina_hp(agotada))  # noqa: E731
    ofertas, recibidos, _ = await correr(hp, HP, manejador)
    assert (ofertas, recibidos) == ([], 1)
    con_agotados, _, _ = await correr(hp, HP, manejador, incluir_agotados=True)
    assert con_agotados[0].existencias == 0
    with pytest.raises(base.ErrorTienda, match="no es la de resultados"):
        await correr(hp, HP, lambda p: httpx.Response(200, text="<html>Access Denied</html>"))


# --- Rappi ------------------------------------------------------------------

RAPPI = Tienda("rappi", "Rappi", "https://r.example", "rappi",
               busqueda="https://r.example/search?query={q}")
COMERCIO = {
    "storeName": "Turbo", "url": "https://r.example/tiendas/1",
    "products": [
        {"name": "Arroz Diana 10 kg", "price": 44320, "realPrice": 52140, "inStock": True,
         "isAvailable": True, "image": "https://img/a"},
        {"name": "Arroz agotado", "price": 5000, "realPrice": 5000, "inStock": False},
        {"name": "Arroz sin enlace", "price": 7300, "realPrice": 7300, "inStock": True},
    ],
}


def pagina_rappi():
    respaldo = {'@"search","arroz"': {"stores": [COMERCIO], "filters": []}}
    ld = {"@type": "ItemList", "itemListElement": [{"item": {
        "name": "Arroz Diana 10 kg", "url": "https://r.example/p/arroz-diana-10459"}}]}
    return (
        pagina_next({"fallback": respaldo})
        + f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        + '<script type="application/ld+json">no es json</script>'
    )


async def test_rappi_lee_comercios_precios_y_enlaces():
    manejador = lambda p: httpx.Response(200, text=pagina_rappi())  # noqa: E731
    ofertas, recibidos, total = await correr(rappi, RAPPI, manejador, "arroz")
    assert (len(ofertas), recibidos, total) == (2, 3, None)
    diana, sin_enlace = ofertas
    assert (diana.precio, diana.precio_lista, diana.descuento_pct) == (44320.0, 52140.0, 15.0)
    assert diana.vendedor == "Turbo"
    assert diana.url == "https://r.example/p/arroz-diana-10459"
    assert sin_enlace.url == "https://r.example/tiendas/1"
    con_agotados, _, _ = await correr(rappi, RAPPI, manejador, "arroz", incluir_agotados=True)
    assert len(con_agotados) == 3


async def test_rappi_sin_resultados_devuelve_vacio():
    manejador = lambda p: httpx.Response(200, text=pagina_next({"fallback": {}}))  # noqa: E731
    assert await correr(rappi, RAPPI, manejador) == ([], 0, None)


# --- Samsung ----------------------------------------------------------------

SAMSUNG = Tienda("samsung", "Samsung", "https://s.example/co", "samsung",
                 busqueda="https://api.s.example/search?query={q}&pageSize={n}&currentPage={p}")
PRODUCTO_SAMSUNG = {
    "code": "QN55Q7F/CO", "name": "Televisor QLED 55 pulgadas",
    "price": {"value": 2499900.0},
    "allPrices": [{"priceType": "RRP", "value": 3299900.0},
                  {"priceType": "SPECIAL", "value": 1999900.0}],
    "stock": {"stockLevel": 5, "stockLevelStatus": "inStock"},
    "picture": {"url": "https://img/tv"},
}


def test_samsung_usa_el_precio_de_venta_y_no_las_promociones_condicionadas():
    oferta = samsung.interpretar_producto(PRODUCTO_SAMSUNG, SAMSUNG)
    assert (oferta.precio, oferta.precio_lista, oferta.existencias) == (2499900.0, 3299900.0, 5)
    assert oferta.url == "https://s.example/co/search/?searchvalue=QN55Q7F%2FCO"
    agotado = {**PRODUCTO_SAMSUNG, "stock": {"stockLevel": 0, "stockLevelStatus": "outOfStock"}}
    assert samsung.interpretar_producto(agotado, SAMSUNG) is None


async def test_samsung_revisa_varias_paginas_por_la_mala_relevancia():
    paginas = []

    def manejador(peticion):
        paginas.append(peticion.url.params["currentPage"])
        assert peticion.url.params["pageSize"] == "100"
        assert "allPrices" in peticion.url.params["fields"]
        cuerpo = {"products": [PRODUCTO_SAMSUNG] * 100,
                  "pagination": {"totalResults": 354, "totalPages": 4}}
        return httpx.Response(200, json=cuerpo)

    _, recibidos, total = await correr(samsung, SAMSUNG, manejador, "televisor", 50)
    assert paginas == ["0", "1"]
    assert (recibidos, total) == (200, 354)


async def test_samsung_se_detiene_en_la_ultima_pagina():
    cuerpo = {"products": [PRODUCTO_SAMSUNG], "pagination": {"totalResults": 1, "totalPages": 1}}
    ofertas, recibidos, _ = await correr(
        samsung, SAMSUNG, lambda p: httpx.Response(200, json=cuerpo), "televisor"
    )
    assert (len(ofertas), recibidos) == (1, 1)


# --- MercadoLibre (formas tomadas de la documentación, sin verificar en vivo) ---

MELI = Tienda("mercadolibre", "MercadoLibre", "https://m.example", "mercadolibre")
DETALLE_MELI = {
    "id": "MCO1", "name": "Portátil Lenovo IdeaPad", "permalink": "https://m.example/p/MCO1",
    "buy_box_winner": {"price": 1899900, "original_price": 2499900, "currency_id": "COP"},
    "attributes": [{"id": "BRAND", "value_name": "Lenovo"},
                   {"id": "GTIN", "value_name": "199276486547"}],
    "pictures": [{"url": "https://img/m"}],
}


@pytest.fixture
def credenciales_meli(monkeypatch):
    monkeypatch.setenv("MELI_CLIENT_ID", "id")
    monkeypatch.setenv("MELI_CLIENT_SECRET", "secreto")
    mercadolibre._token.clear()


async def test_mercadolibre_sin_credenciales_explica_que_falta(monkeypatch):
    monkeypatch.delenv("MELI_CLIENT_ID", raising=False)
    monkeypatch.delenv("MELI_CLIENT_SECRET", raising=False)
    with pytest.raises(base.ErrorTienda, match="MELI_CLIENT_ID"):
        await correr(mercadolibre, MELI, lambda p: httpx.Response(500))


async def test_mercadolibre_pide_token_busca_y_lee_el_precio(credenciales_meli):
    def manejador(peticion):
        ruta = peticion.url.path
        if ruta == "/oauth/token":
            assert b"grant_type=client_credentials" in peticion.content
            return httpx.Response(200, json={"access_token": "TOKEN"})
        assert peticion.headers["Authorization"] == "Bearer TOKEN"
        if ruta == "/products/search":
            assert peticion.url.params["site_id"] == "MCO"
            return httpx.Response(200, json={
                "paging": {"total": 80},
                "results": [{"id": "MCO1"}, {"id": "MCO2"}, {"id": "MCO3"}],
            })
        if ruta == "/products/MCO1":
            return httpx.Response(200, json=DETALLE_MELI)
        if ruta == "/products/MCO2":  # sin vendedor ganador: no hay precio que mostrar
            return httpx.Response(200, json={**DETALLE_MELI, "buy_box_winner": None})
        return httpx.Response(404, json={})

    ofertas, recibidos, total = await correr(mercadolibre, MELI, manejador, "portatil")
    assert (len(ofertas), recibidos, total) == (1, 3, 80)
    oferta = ofertas[0]
    assert (oferta.precio, oferta.precio_lista, oferta.marca) == (1899900.0, 2499900.0, "Lenovo")
    assert oferta.eans == ["199276486547"]
    assert oferta.url == "https://m.example/p/MCO1"


async def test_mercadolibre_credenciales_rechazadas(credenciales_meli):
    with pytest.raises(base.ErrorTienda, match="rechazó las credenciales"):
        await correr(mercadolibre, MELI, lambda p: httpx.Response(401, json={}))


# --- WooCommerce ------------------------------------------------------------

WOO = Tienda("pcware", "PC Ware", "https://w.example", "woocommerce")
PRODUCTO_WOO = {
    "name": "Port&aacute;til HP Victus", "permalink": "https://w.example/portatil-hp",
    "brands": [{"name": "HP"}], "is_in_stock": True, "low_stock_remaining": 1,
    "images": [{"src": "https://w.example/a.jpg"}],
    "prices": {"price": "4299900", "regular_price": "5500000", "currency_code": "COP",
               "currency_minor_unit": 0},
}


async def test_woocommerce_interpreta_y_lee_el_total():
    def manejador(peticion):
        assert peticion.url.path == "/wp-json/wc/store/v1/products"
        assert peticion.url.params["search"] == "portatil hp"
        return httpx.Response(200, json=[PRODUCTO_WOO], headers={"X-WP-Total": "37"})

    ofertas, recibidos, total = await correr(woocommerce, WOO, manejador, "portatil hp")
    assert (recibidos, total) == (1, 37)
    oferta = ofertas[0]
    assert oferta.nombre == "Portátil HP Victus"
    assert (oferta.precio, oferta.precio_lista, oferta.marca) == (4299900.0, 5500000.0, "HP")
    assert oferta.existencias == 1


def test_woocommerce_respeta_la_unidad_menor_y_descarta_agotados():
    con_centavos = {**PRODUCTO_WOO, "prices": {"price": "1999900", "regular_price": "1999900",
                                               "currency_minor_unit": 2}}
    assert woocommerce.interpretar_producto(con_centavos, WOO).precio == 19999.0
    agotado = {**PRODUCTO_WOO, "is_in_stock": False}
    assert woocommerce.interpretar_producto(agotado, WOO) is None


async def test_woocommerce_api_deshabilitada_se_reporta():
    with pytest.raises(base.ErrorTienda, match="HTTP 403"):
        await correr(woocommerce, WOO, lambda p: httpx.Response(403, json={"code": "x"}))


# --- IKEA -------------------------------------------------------------------

IKEA = Tienda("ikea", "IKEA", "https://i.example/co/es", "ikea",
              busqueda="https://api.i.example/buscar?q={q}&size={n}")
PRODUCTO_IKEA = {
    "name": "SANDSBERG", "typeName": "Silla", "validDesignText": "blanco",
    "pipUrl": "https://i.example/co/es/p/sandsberg-10605424/", "onlineSellable": True,
    "homeDelivery": "HIGH_IN_STOCK", "mainImageUrl": "https://i.example/s.jpg",
    "categoryPath": [{"name": "Sillas y mesas"}, {"name": "Sillas de comedor"}],
    "salesPrice": {"currencyCode": "COP", "numeral": 69990.0},
}


async def test_ikea_arma_el_nombre_y_usa_la_categoria():
    cuerpo = {"searchResultPage": {"products": {"main": {
        "items": [{"product": PRODUCTO_IKEA}, {"otro": 1}], "max": 811}}}}
    ofertas, recibidos, total = await correr(
        ikea, IKEA, lambda p: httpx.Response(200, json=cuerpo), "silla"
    )
    assert (recibidos, total) == (1, 811)
    oferta = ofertas[0]
    assert oferta.nombre == "SANDSBERG Silla blanco"
    assert (oferta.precio, oferta.descuento_pct) == (69990.0, 0.0)
    assert "Sillas de comedor" in oferta.categoria
    assert motor.es_relevante(oferta, "silla comedor")


def test_ikea_descarta_lo_que_no_se_vende_en_linea():
    assert ikea.interpretar_producto({**PRODUCTO_IKEA, "onlineSellable": False}, IKEA) is None
    rebajado = {**PRODUCTO_IKEA, "salesPrice": {"numeral": 50000.0,
                                                "previous": {"numeral": 69990.0}}}
    assert ikea.interpretar_producto(rebajado, IKEA).precio_lista == 69990.0


# --- motor ------------------------------------------------------------------


async def test_motor_despacha_por_plataforma_y_usa_la_categoria_para_la_relevancia():
    def manejador(peticion):
        if peticion.url.host == "api.l.example":
            cuerpo = {"data": [{"products": [PRODUCTO_LENOVO]}], "productCount": 1}
            return httpx.Response(200, json={"data": cuerpo})
        forma = {"results": [PRODUCTO_FALABELLA], "pagination": {"count": 1, "perPage": 48}}
        return httpx.Response(200, text=pagina_next(forma))

    resultado = await motor.buscar(
        "portatil lenovo", [LENOVO, FALABELLA], transporte=httpx.MockTransport(manejador)
    )
    # "ThinkPad E14" no contiene "portatil", pero su categoría sí.
    assert {o.tienda_id for o in resultado.ofertas} == {"lenovo", "falabella"}
    assert not resultado.tiendas_fallidas

    ajena = await motor.buscar(
        "taladro percutor", [LENOVO, FALABELLA], transporte=httpx.MockTransport(manejador)
    )
    assert ajena.ofertas == []


async def test_motor_quita_productos_repetidos_por_la_tienda():
    forma = {"results": [PRODUCTO_FALABELLA] * 3, "pagination": {"count": 3, "perPage": 48}}
    transporte = httpx.MockTransport(lambda p: httpx.Response(200, text=pagina_next(forma)))
    resultado = await motor.buscar("portatil", [FALABELLA], transporte=transporte)
    assert len(resultado.ofertas) == 1
    assert resultado.tiendas[0].encontrados == 3


async def test_motor_aisla_un_conector_que_revienta():
    def manejador(peticion):
        return httpx.Response(200, json={"data": {"data": [{"products": [["no es un dict"]]}]}})

    resultado = await motor.buscar("x", [LENOVO], transporte=httpx.MockTransport(manejador))
    assert resultado.ofertas == []
    assert "formato inesperado" in resultado.tiendas_fallidas[0].error
