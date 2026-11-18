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
    ) == ("modelo", 1.0)
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


def respuestas(peticion):
    """Simula la TRM, Samsung, Lenovo, IKEA y UPCitemdb."""
    host = peticion.url.host
    if host == "www.datos.gov.co":
        return httpx.Response(200, json=[{"valor": "4000"}])
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
            {"title": 'Samsung 55" Class Crystal UHD CU7000', "ean": "0887276", "model": "X",
             "offers": [
                 {"merchant": "A", "price": 340, "condition": "New", "updated_t": reciente},
                 {"merchant": "B", "price": 360, "condition": "New", "updated_t": reciente},
                 {"merchant": "C", "price": 99, "condition": "New", "updated_t": viejo},
                 {"merchant": "D", "price": 150, "condition": "Used", "updated_t": reciente},
             ]},
            {"title": "Sin ofertas vigentes", "offers": []},
        ]})
    return httpx.Response(404)


@pytest.fixture
def sin_esperas(monkeypatch):
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)

    monkeypatch.setattr(internacional.asyncio, "sleep", dormir)
    return esperas


async def test_cada_grupo_se_resuelve_con_la_fuente_que_le_corresponde(conexion, sin_esperas):
    async with cliente(respuestas) as c:
        referencias, avisos = await internacional.investigar(
            c, conexion, [S25, PORTATIL, SILLA, TV], profundo=True
        )
    assert avisos == []
    silla = referencias[id(SILLA)]
    assert (silla.coincidencia, silla.precio_usd, silla.fuentes) == (
        "exacto", 15.0, ["IKEA EE. UU."],
    )
    celular = referencias[id(S25)]
    # SM-S938B (Colombia) y SM-S938UZKAVZW (EE. UU.) son el mismo modelo con otro sufijo.
    assert (celular.coincidencia, celular.precio_usd) == ("modelo", 1299.99)
    assert referencias[id(PORTATIL)].fuentes == ["Lenovo EE. UU."]
    # El televisor lo resuelve UPCitemdb: mediana de ofertas nuevas y vigentes (340 y 360).
    tele = referencias[id(TV)]
    assert (tele.coincidencia, tele.precio_usd) == ("modelo", 350.0)
    assert tele.trm == 4000.0


async def test_lo_consultado_queda_en_cache_y_no_se_vuelve_a_pedir(conexion):
    visitas = []

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        await internacional.investigar(c, conexion, [SILLA])
        primera = len(visitas)
        referencias, _ = await internacional.investigar(c, conexion, [SILLA])
    assert len(visitas) == primera
    assert referencias[id(SILLA)].precio_usd == 15.0


async def test_upcitemdb_respeta_su_limite(conexion, sin_esperas):
    esperas = sin_esperas
    otro = grupo_de(oferta("Televisor LG 55 Pulgadas 55QNED74BSA", 2000000, "LG"))
    visitas = []

    def manejador(peticion):
        visitas.append(peticion.url.host)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        # Búsqueda normal: la primera consulta sale; la segunda no espera y se deja pasar.
        referencias, avisos = await internacional.investigar(c, conexion, [TV, otro])
        assert visitas.count("api.upcitemdb.com") == 1
        assert id(TV) in referencias and id(otro) not in referencias
        assert avisos == [] and esperas == []
        # Búsqueda profunda: espera lo necesario y sí consulta.
        await internacional.investigar(c, conexion, [otro], profundo=True)
    assert visitas.count("api.upcitemdb.com") == 2
    assert len(esperas) == 1 and 0 < esperas[0] <= internacional.PAUSA_UPC_SEGUNDOS


async def test_upcitemdb_sin_resultados_no_es_una_falla(conexion):
    def manejador(peticion):
        if peticion.url.host == "api.upcitemdb.com":
            return httpx.Response(404, json={"code": "NOT_FOUND"})
        return respuestas(peticion)

    async with cliente(manejador) as c:
        referencias, avisos = await internacional.investigar(c, conexion, [TV])
    assert referencias == {} and avisos == []


async def test_una_fuente_caida_se_avisa_y_no_tumba_las_demas(conexion):
    def manejador(peticion):
        if peticion.url.host == "api.shop.samsung.com":
            return httpx.Response(500)
        return respuestas(peticion)

    async with cliente(manejador) as c:
        referencias, avisos = await internacional.investigar(c, conexion, [S25, SILLA])
    assert id(SILLA) in referencias
    assert any("samsung: respondió HTTP 500" in a for a in avisos)


async def test_sin_trm_no_hay_comparacion_internacional(conexion):
    async with cliente(lambda p: httpx.Response(500)) as c:
        referencias, avisos = await internacional.investigar(c, conexion, [S25])
    assert referencias == {}
    assert "TRM" in avisos[0]
