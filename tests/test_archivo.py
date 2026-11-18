"""Precios pasados según el archivo de Internet, con el archivo simulado."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from ofertas import archivo, historial, veredicto
from ofertas.modelos import Oferta

AHORA = datetime(2026, 11, 18, tzinfo=UTC)
URL = "https://co.totto.com/morral-hanzo/p"


def pagina(precio):
    ld = {"@type": "Product", "offers": {"@type": "AggregateOffer", "lowPrice": precio,
                                         "offers": [{"@type": "Offer", "price": precio}]}}
    return f'<html><script type="application/ld+json">{json.dumps(ld)}</script></html>'


@pytest.mark.parametrize(
    ("html", "esperado"),
    [
        (pagina(89900), 89900.0),
        ('<meta property="product:price:amount" content="73900">', 73900.0),
        ('<script>{"sellingPrice":61337,"Price":61337.0,"spotPrice":0}</script>', 61337.0),
        ('<script type="application/ld+json">no es json</script>', 0.0),
        ("<html>sin precio</html>", 0.0),
    ],
)
def test_precio_en_pagina(html, esperado):
    assert archivo.precio_en_pagina(html) == esperado


def archivo_simulado(copias: dict[str, int], visitas: list | None = None):
    """`copias` asocia la marca de tiempo de cada copia con el precio que mostraba."""

    def manejador(peticion):
        if visitas is not None:
            visitas.append(peticion.url.host)
        if peticion.url.host == "archive.org":
            pedida = peticion.url.params["timestamp"]
            if not copias:
                return httpx.Response(200, json={"archived_snapshots": {}})
            cercana = min(copias, key=lambda m: abs(int(m[:8]) - int(pedida)))
            return httpx.Response(200, json={"archived_snapshots": {"closest": {
                "timestamp": cercana, "status": "200", "available": True}}})
        marca = peticion.url.path.split("/")[2][:14]
        return httpx.Response(200, text=pagina(copias[marca]))

    return httpx.AsyncClient(transport=httpx.MockTransport(manejador))


async def test_consulta_las_copias_de_hace_tres_meses_y_un_ano():
    copias = {"20260816120000": 89900, "20251120120000": 99900}
    async with archivo_simulado(copias) as cliente:
        precios = await archivo.consultar(cliente, URL, AHORA)
    assert precios == [
        {"fecha": "2025-11-20", "precio": 99900.0},
        {"fecha": "2026-08-16", "precio": 89900.0},
    ]


async def test_una_copia_reciente_no_sirve_de_referencia():
    """Una copia de hace una semana puede ser de la misma promoción."""
    async with archivo_simulado({"20261112120000": 77994}) as cliente:
        assert await archivo.consultar(cliente, URL, AHORA) == []
    async with archivo_simulado({}) as cliente:
        assert await archivo.consultar(cliente, URL, AHORA) == []


async def test_el_resultado_se_guarda_tambien_cuando_no_hay_copias(tmp_path):
    visitas = []
    with historial.abrir(tmp_path / "h.db") as conexion:
        async with archivo_simulado({}, visitas) as cliente:
            assert await archivo.precios_pasados(cliente, conexion, URL) == []
            primera = len(visitas)
            assert await archivo.precios_pasados(cliente, conexion, URL) == []
    assert primera > 0 and len(visitas) == primera


async def test_si_el_archivo_falla_se_sigue_sin_el(tmp_path):
    with historial.abrir(tmp_path / "h.db") as conexion:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda p: httpx.Response(429))
        ) as cliente:
            assert await archivo.precios_pasados(cliente, conexion, URL) == []


def test_el_veredicto_usa_la_copia_antigua_contra_el_precio_de_lista():
    """Lo que solo vende una tienda: anuncia 40% sobre $129.990, pero en abril valía $89.900."""
    morral = Oferta("totto", "Totto", "Morral Hanzo", "Totto", 77994.0, 129990.0, URL)
    juicio = veredicto.evaluar(morral, [], archivo=[{"fecha": "2026-04-16", "precio": 89900.0}])
    assert juicio.clase == "descuento_real"
    assert juicio.confianza == "media"
    assert juicio.precio_real == 89900
    assert juicio.ahorro_real_pct == 13.2
    assert juicio.lista_inflada_pct == 44.6
    assert "lo que esta misma página mostraba el 2026-04-16" in juicio.texto
    assert "no el 40% que anuncia la tienda" in juicio.texto
    assert "es una copia antigua de la página" in juicio.texto

    igual = Oferta("totto", "Totto", "Morral Hanzo", "Totto", 89900.0, 129990.0, URL)
    juicio = veredicto.evaluar(igual, [], archivo=[{"fecha": "2026-04-16", "precio": 89900.0}])
    assert juicio.clase == "oferta_falsa"

    # Si hay tiendas con el mismo producto, esa evidencia va primero.
    otras = [Oferta(f"t{i}", f"T{i}", "Morral Hanzo", "Totto", p, p, "u")
             for i, p in enumerate((80000.0, 81000.0, 82000.0))]
    juicio = veredicto.evaluar(morral, otras, archivo=[{"fecha": "2026-04-16", "precio": 89900.0}])
    assert (juicio.confianza, juicio.precio_real) == ("fuerte", 81000)
    assert "Otra referencia: $89.900" in juicio.texto
