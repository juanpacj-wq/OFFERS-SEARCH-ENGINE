"""Investigación del precio internacional, con las fuentes simuladas."""

import time

import httpx
import pytest

from ofertas import historial, identidad, internacional
from ofertas.modelos import Oferta

TRM = 4000.0


def oferta(nombre, precio, marca="SAMSUNG", tienda="a", modelo="", ean=None):
    return Oferta(tienda, tienda.upper(), nombre, marca, precio, precio, f"https://{tienda}/p",
                  modelo=modelo, eans=[ean] if ean else [])


def grupo_de(*ofertas):
    (grupo,) = identidad.agrupar(list(ofertas))
    return grupo


S25 = grupo_de(oferta("Celular Samsung Galaxy S25 Ultra 5G 256Gb Titanio Negro SM-S938B", 4600000))
TV = grupo_de(oferta("Televisor Samsung 55 Pulgadas Smarttv 4K Un55cu7000kxzl Negro", 1600000))
PORTATIL = grupo_de(oferta(
    "Computador Portátil LENOVO IdeaPad Slim 3 14 Pulgadas Intel Core 5 RAM 8GB SSD 512GB Azul",
    2300000, "LENOVO", modelo="83RQ003ELM",
))
SILLA = grupo_de(oferta("SANDSBERG Silla blanco", 69990, "IKEA", modelo="10605424"))


@pytest.fixture
def conexion(tmp_path):
    con = historial.conectar(tmp_path / "h.db")
    yield con
    con.close()


def cliente(manejador):
    return httpx.AsyncClient(transport=httpx.MockTransport(manejador))


# --- qué se busca afuera ----------------------------------------------------


def test_la_consulta_lleva_marca_familia_y_capacidad_sin_codigos_regionales():
    assert internacional.consulta_para(S25) == "samsung galaxy s25 ultra 256gb"
    assert internacional.consulta_para(PORTATIL) == "lenovo ideapad slim 3 512gb"
    assert "un55cu7000kxzl" not in internacional.consulta_para(TV)


def test_la_consulta_por_modelo_quita_el_sufijo_de_pais():
    assert internacional.consulta_por_modelo(TV) == "UN55CU7000"
    assert internacional.consulta_por_modelo(S25) is None  # código corto: no lleva sufijo
    assert internacional.consulta_por_modelo(SILLA) is None


def test_no_se_investiga_lo_barato_ni_lo_que_no_tiene_marca():
    arroz = grupo_de(oferta("Arroz Diana 500 g", 2100, "Diana"))
    generico = grupo_de(oferta("Televisor 55 pulgadas", 1500000, ""))
    assert not internacional.vale_la_pena(arroz)
    assert not internacional.vale_la_pena(generico)
    assert internacional.vale_la_pena(S25)


# --- calificación -----------------------------------------------------------


def candidato(titulo, usd, **extra):
    return {"fuente": "Prueba", "titulo": titulo, "precio_usd": usd, "url": "u", **extra}


def test_exacto_por_codigo_de_barras_o_por_articulo_del_fabricante():
    con_ean = grupo_de(oferta("Consola X", 2000000, "ACME", ean="0045496452308"))
    assert internacional.calificar(con_ean, candidato("ACME Console X", 400, ean="45496452308"),
                                   TRM) == ("exacto", 1.0)
    assert internacional.calificar(SILLA, candidato("IKEA SANDSBERG Chair", 15, exacto=True),
                                   TRM) == ("exacto", 1.0)


def test_mismo_modelo_tolera_sufijo_y_reconoce_el_codigo_de_familia():
    assert internacional.calificar(
        S25, candidato("Samsung Galaxy S25 Ultra", 1000, codigo="SM-S938BZKD"), TRM
    ) == ("modelo", 1.0)
    assert internacional.calificar(
        TV, candidato('Samsung 55" Class Crystal UHD CU7000', 350), TRM
    ) == ("modelo", 0.9)
    # Mismo modelo con el sufijo de otro país.
    assert internacional.calificar(
        TV, candidato("Samsung 55 Crystal UHD", 380, codigo="UN55CU7000FXZA"), TRM
    ) == ("modelo", 0.95)
    assert internacional.calificar(
        TV, candidato("Samsung 55 Crystal UHD", 380, codigo="UN55U8000FFXZA"), TRM
    ) is None
    # El mismo código de familia en otro tamaño es otro televisor.
    assert internacional.calificar(
        TV, candidato('Samsung 65" Class Crystal UHD CU7000', 350), TRM
    ) is None


def test_equivalente_exige_marca_variante_capacidad_y_procesador():
    assert internacional.calificar(
        S25, candidato("Samsung Galaxy S25 Ultra 256GB (Unlocked)", 1100), TRM
    )[0] == "equivalente"
    rechazados = [
        candidato("Samsung Galaxy S25 256GB (Unlocked)", 900),  # no es el Ultra
        candidato("Samsung Galaxy S25 Ultra 512GB (Unlocked)", 1100),  # otra capacidad
        candidato("Apple iPhone 16 Pro Max 256GB", 1100),  # otra marca
        candidato("Samsung Galaxy S25 Ultra Silicone Case 256GB", 1000),  # accesorio
        candidato("Samsung Galaxy S25 Ultra 256GB", 30),  # precio de otra cosa
        candidato("Samsung Galaxy S25 Ultra 256GB", 9000),
    ]
    assert [internacional.calificar(S25, c, TRM) for c in rechazados] == [None] * 6
    assert internacional.calificar(
        PORTATIL, candidato("Lenovo IdeaPad Slim 3 14 Intel Core i7 8GB 512GB", 500), TRM
    ) is None  # otro procesador
    assert internacional.calificar(
        PORTATIL, candidato("Lenovo IdeaPad Slim 3 14 Intel Core 5 16GB 512GB", 500), TRM
    ) is None  # otra memoria
    assert internacional.calificar(
        PORTATIL, candidato("Lenovo IdeaPad Slim 3 14 Core 5 8GB RAM 512GB SSD", 500), TRM
    )[0] == "equivalente"


def test_las_palabras_en_espanol_no_impiden_reconocer_el_equivalente():
    impresora = grupo_de(oferta(
        "Impresora Fotográfica Portátil HP Sprocket 2x3 Con Conexión Bluetooth", 559900, "HP"
    ))
    candidatos = [
        candidato("HP Sprocket Portable 2X3 Inch Instant Photo Printer (Blush Pink)", 89.99),
        candidato("HP Sprocket Select Portable Photo Printer 2X3", 99.99),
        candidato("HP Sprocket 2X3 Premium Zink Photo Paper (50 Sheets)", 22.50),  # papel
        candidato("HP Sprocket 2X3 Photo Printer Gift Bundle", 139.99),  # paquete
        candidato("HP DeskJet 2755e Wireless Printer", 84.99),  # otra línea
    ]
    # Sin vocabulario, "fotografica" y "conexion" hunden la coincidencia.
    assert internacional.calificar(impresora, candidatos[0], TRM) is None
    referencia = internacional.resumir(impresora, candidatos, TRM)
    assert (referencia.coincidencia, referencia.candidatos) == ("equivalente", 2)
    assert referencia.precio_usd == 94.99
    assert not referencia.confiable


def test_una_sola_palabra_en_comun_no_basta():
    celular = grupo_de(oferta("Celular Samsung Galaxy A16 128GB", 700000))
    assert internacional.resumir(celular, [candidato("Samsung Galaxy Buds 3", 150)], TRM) is None


def test_el_sufijo_regional_no_basta_si_cambia_la_configuracion():
    hp = grupo_de(oferta(
        'Computador Portátil HP 15" Pulgadas 15-fd0131la - Intel Core i3 - RAM 8GB - SSD 512GB',
        2000000, "HP",
    ))
    otra_capacidad = candidato("HP 15-Fd0133wm 15.6 Laptop Intel i3 8GB RAM 256GB SSD", 402.60)
    misma = candidato("HP 15-Fd0139wm 15.6 Laptop Intel i3 8GB RAM 512GB SSD", 430.00)
    assert internacional.calificar(hp, otra_capacidad, TRM) is None
    assert internacional.calificar(hp, misma, TRM) == ("modelo", 0.95)


def test_resumir_prefiere_la_coincidencia_mas_segura_y_usa_la_mediana():
    candidatos = [
        candidato("Samsung Galaxy S25 Ultra 256GB (Verizon)", 1300, codigo="SM-S938BZKA"),
        candidato("Samsung Galaxy S25 Ultra 256GB", 1100, codigo="SM-S938BZTD"),
        candidato("Samsung Galaxy S25 Ultra 256GB (Unlocked)", 700),  # solo equivalente
        candidato("Samsung Galaxy S25 Ultra Case", 30),
    ]
    referencia = internacional.resumir(S25, candidatos, TRM)
    assert (referencia.coincidencia, referencia.precio_usd, referencia.candidatos) == (
        "modelo", 1200.0, 2,
    )
    assert referencia.confiable
    solo_equivalente = internacional.resumir(S25, candidatos[2:], TRM)
    assert (solo_equivalente.coincidencia, solo_equivalente.confiable) == ("equivalente", False)
    assert internacional.resumir(S25, candidatos[3:], TRM) is None


# --- tasa de cambio ---------------------------------------------------------


async def test_trm_oficial_se_guarda_por_dia(conexion):
    visitas = []

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return httpx.Response(200, json=[{"valor": "3309.55"}])

    async with cliente(manejador) as c:
        assert await internacional.obtener_trm(c, conexion) == 3309.55
        assert await internacional.obtener_trm(c, conexion) == 3309.55
    assert visitas == ["www.datos.gov.co"]


async def test_trm_usa_el_respaldo_y_si_todo_falla_no_inventa(conexion):
    def manejador(peticion):
        if peticion.url.host == "www.datos.gov.co":
            return httpx.Response(503)
        return httpx.Response(200, json={"rates": {"COP": 3320.1}})

    async with cliente(manejador) as c:
        assert await internacional.obtener_trm(c, conexion) == 3320.1

    conexion.execute("DELETE FROM ajustes")
    async with cliente(lambda p: httpx.Response(500)) as c:
        assert await internacional.obtener_trm(c, conexion) is None


# --- fuentes ----------------------------------------------------------------


def tarjeta_bing(titulo, precio, enlace="/shop/productdetails?q=x&amp;goid=1"):
    return (
        f'<li class="br-item br-allowCrdovrflw"><a class="br-titlelink sj_spcls" href="{enlace}">'
        f'<div class="br-title br-freeGridFontChange"><span title="{titulo}">{titulo[:20]}…</span>'
        f'</div></a><div class="br-price"><div class="pd-price br-standardPrice promoted">'
        f'<div class="resp-one-line" id="r1">${precio}</div></div></div></li>'
    )


BING = {
    # El televisor aparece con el sufijo de EE. UU., junto a un paquete y un repuesto.
    "samsung UN55CU7000": [
        tarjeta_bing("Samsung UN55CU7000FXZA - 55Inch - Led - 3840X2160", "379.99"),
        tarjeta_bing("Samsung UN55CU7000FXZA 55 Crystal UHD 4K Smart TV", "389.99"),
        tarjeta_bing("SAMSUNG UN55CU7000 55 Inch TV Bundle With HDMI Cable", "786.49"),
        tarjeta_bing("Remote Control for Samsung UN55CU7000", "18.21"),
    ],
    "dewalt DWA6HLDFT": [
        tarjeta_bing("DEWALT Drill Bit Holder Extension, Impact Ready (DWA6HLDFT)", "12.00"),
    ],
}


def respuestas(peticion):
    """Simula la TRM, Bing Shopping, Samsung, Lenovo, IKEA y UPCitemdb."""
    host = peticion.url.host
    if host == "www.datos.gov.co":
        return httpx.Response(200, json=[{"valor": "4000"}])
    if host == "www.bing.com":
        assert peticion.url.params["setmkt"] == "en-US"
        tarjetas = BING.get(peticion.url.params["q"], [])
        return httpx.Response(200, text="<html><ul>" + "".join(tarjetas) + "</ul></html>")
    if host == "api.shop.samsung.com":
        if peticion.url.params["query"] != "galaxy s25 ultra 256gb":
            return httpx.Response(200, json={"products": []})
        return httpx.Response(200, json={"products": [
            {"code": "SM-S938UZKAVZW", "name": "Galaxy S25 Ultra 256GB (Verizon)",
             "price": {"value": 1299.99}},
            {"code": "EF-PS938", "name": "Galaxy S25 Ultra Silicone Case",
             "price": {"value": 29.99}},
        ]})
    if host == "openapi.lenovo.com":
        assert peticion.headers["Referer"] == "https://www.lenovo.com/us/en/"
        return httpx.Response(200, json={"data": {"data": [{"products": [
            {"productCode": "83KD000KUS", "summary": "IdeaPad Slim 3 14 Core 5 8GB 512GB",
             "finalPrice": "549.99", "currencyCode": "USD", "url": "/p/laptops/x"},
        ]}]}})
    if host == "sik.search.blue.cdtapps.com":
        assert peticion.url.params["q"] == "10605424"
        return httpx.Response(200, json={"searchResultPage": {"products": {"main": {"items": [
            {"product": {"itemNoGlobal": "10605424", "name": "SANDSBERG", "typeName": "Chair",
                         "salesPrice": {"numeral": 15.0, "currencyCode": "USD"},
                         "pipUrl": "https://ikea/us/p"}},
            {"product": {"itemNoGlobal": "999", "name": "OTRA", "typeName": "Chair",
                         "salesPrice": {"numeral": 99.0, "currencyCode": "USD"}}},
        ]}}}})
    if host == "api.upcitemdb.com":
        reciente, viejo = time.time() - 86400, time.time() - 3 * 365 * 86400
        return httpx.Response(200, json={"items": [
            {"title": "LG 55QNED74 55 Inch QNED 4K TV", "ean": "0195174", "model": "55QNED74URA",
             "offers": [
                 {"merchant": "A", "price": 540, "condition": "New", "updated_t": reciente},
                 {"merchant": "B", "price": 560, "condition": "New", "updated_t": reciente},
                 {"merchant": "C", "price": 99, "condition": "New", "updated_t": viejo},
                 {"merchant": "D", "price": 150, "condition": "Used", "updated_t": reciente},
             ]},
            {"title": "Sin ofertas vigentes", "offers": []},
        ]})
    return httpx.Response(404)


LG = grupo_de(oferta("Televisor LG 55 Pulgadas QNED 55QNED74BSA", 2000000, "LG"))
PORTABROCAS = grupo_de(oferta(
    "Portabrocas Magnético para Taladro Percutor de 15.24 cm", 69900, "DEWALT",
    modelo="DWA6HLDFT",
))


@pytest.fixture
def sin_esperas(monkeypatch):
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)

    monkeypatch.setattr(internacional.asyncio, "sleep", dormir)
    return esperas


def test_las_consultas_generales_van_de_la_mas_precisa_a_la_mas_amplia():
    assert internacional.consultas_generales(TV) == ["samsung UN55CU7000", "samsung smarttv"]
    assert internacional.consultas_generales(S25) == [
        "samsung SM-S938B", "samsung galaxy s25 ultra 256gb",
    ]
    assert internacional.consultas_generales(PORTATIL)[-1] == "lenovo ideapad slim 3 512gb core i5"


async def test_bing_lee_titulo_precio_y_enlace():
    async with cliente(respuestas) as c:
        candidatos = await internacional.fuente_bing(c, TV, "samsung UN55CU7000")
    assert len(candidatos) == 4
    assert candidatos[0] == {
        "fuente": "Bing Shopping (comercios de EE. UU.)",
        "titulo": "Samsung UN55CU7000FXZA - 55Inch - Led - 3840X2160",
        "precio_usd": 379.99,
        "url": "https://www.bing.com/shop/productdetails?q=x&goid=1",
    }


def test_un_anuncio_que_solo_menciona_el_modelo_no_cuenta():
    assert internacional.calificar(
        TV, candidato("SAMSUNG UN55CU7000 55 Inch TV Bundle With HDMI Cable", 400), TRM
    ) is None
    assert internacional.calificar(
        TV, candidato("Remote Control for Samsung UN55CU7000", 300), TRM
    ) is None
    # El mismo modelo vale aunque el nombre de afuera use otras palabras.
    assert internacional.calificar(
        PORTABROCAS, candidato("DEWALT Drill Bit Holder Extension (DWA6HLDFT)", 12), TRM
    ) == ("modelo", 1.0)


async def test_cada_grupo_se_resuelve_con_la_fuente_que_le_corresponde(conexion):
    visitas = []

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        referencias, avisos = await internacional.investigar(
            c, conexion, [S25, PORTATIL, SILLA, TV, PORTABROCAS]
        )
    assert avisos == []
    silla = referencias[id(SILLA)]
    assert (silla.coincidencia, silla.precio_usd, silla.fuentes) == (
        "exacto", 15.0, ["IKEA EE. UU."],
    )
    # SM-S938B (Colombia) y SM-S938UZKAVZW (EE. UU.) son el mismo modelo con otro sufijo.
    celular = referencias[id(S25)]
    assert (celular.coincidencia, celular.precio_usd) == ("modelo", 1299.99)
    assert referencias[id(PORTATIL)].fuentes == ["Lenovo EE. UU."]
    # El televisor sale de Bing: mediana de los dos anuncios del mismo modelo, sin el
    # paquete ni el control remoto.
    tele = referencias[id(TV)]
    assert (tele.coincidencia, tele.precio_usd, tele.candidatos) == ("modelo", 384.99, 2)
    assert tele.fuentes == ["Bing Shopping (comercios de EE. UU.)"]
    assert referencias[id(PORTABROCAS)].precio_usd == 12.0
    # En una búsqueda normal no se toca UPCitemdb, que es lento.
    assert "api.upcitemdb.com" not in visitas


async def test_lo_consultado_queda_en_cache_y_no_se_vuelve_a_pedir(conexion):
    visitas = []

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        await internacional.investigar(c, conexion, [SILLA, TV])
        primera = len(visitas)
        referencias, _ = await internacional.investigar(c, conexion, [SILLA, TV])
    assert len(visitas) == primera
    assert referencias[id(SILLA)].precio_usd == 15.0
    # A IKEA le basta su propia tienda: no se pregunta a Bing por la silla.
    assert visitas.count("www.bing.com") == 1


async def test_upcitemdb_solo_en_modo_profundo_y_respetando_su_limite(conexion, sin_esperas):
    visitas = []
    otro = grupo_de(oferta("Televisor LG 65 Pulgadas QNED 65QNED74BSA", 3000000, "LG"))

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        referencias, _ = await internacional.investigar(c, conexion, [LG])
        assert referencias == {} and "api.upcitemdb.com" not in visitas

        referencias, avisos = await internacional.investigar(
            c, conexion, [LG, otro], profundo=True
        )
    assert avisos == []
    assert visitas.count("api.upcitemdb.com") == 2
    # Mediana de las ofertas nuevas y vigentes (540 y 560); la vieja y la usada no cuentan.
    assert referencias[id(LG)].precio_usd == 550.0
    # La primera consulta sale de inmediato; la segunda espera su turno.
    assert len(sin_esperas) == 1
    assert 0 < sin_esperas[0] <= internacional.PAUSA_UPC_SEGUNDOS


async def test_upcitemdb_sin_resultados_no_es_una_falla(conexion, sin_esperas):
    def manejador(peticion):
        if peticion.url.host == "api.upcitemdb.com":
            return httpx.Response(404, json={"code": "NOT_FOUND"})
        return respuestas(peticion)

    async with cliente(manejador) as c:
        referencias, avisos = await internacional.investigar(c, conexion, [LG], profundo=True)
    assert referencias == {} and avisos == []


async def test_upcitemdb_excedido_se_avisa_una_vez_y_no_se_insiste(conexion, sin_esperas):
    visitas = []
    otro = grupo_de(oferta("Televisor LG 65 Pulgadas QNED 65QNED74BSA", 3000000, "LG"))

    def manejador(peticion):
        visitas.append(peticion.url.host)
        if peticion.url.host == "api.upcitemdb.com":
            return httpx.Response(429, json={"code": "TOO_FAST"})
        return respuestas(peticion)

    async with cliente(manejador) as c:
        _, avisos = await internacional.investigar(c, conexion, [LG, otro], profundo=True)
    assert avisos == ["UPCitemdb alcanzó su límite de consultas; se usaron las demás fuentes."]
    assert visitas.count("api.upcitemdb.com") == 1


async def test_una_fuente_caida_se_avisa_y_no_tumba_las_demas(conexion):
    def manejador(peticion):
        if peticion.url.host == "api.shop.samsung.com":
            return httpx.Response(500)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        referencias, avisos = await internacional.investigar(c, conexion, [TV, SILLA])
    assert id(SILLA) in referencias
    assert referencias[id(TV)].fuentes == ["Bing Shopping (comercios de EE. UU.)"]
    assert any("samsung: respondió HTTP 500" in a for a in avisos)


async def test_sin_trm_no_hay_comparacion_internacional(conexion):
    async with cliente(lambda p: httpx.Response(500)) as c:
        referencias, avisos = await internacional.investigar(c, conexion, [S25])
    assert referencias == {}
    assert "TRM" in avisos[0]
