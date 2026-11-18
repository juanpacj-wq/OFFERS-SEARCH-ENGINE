"""Pruebas contra las tiendas reales. Se corren aparte: `uv run pytest -m red`."""

import asyncio
import os

import pytest

from ofertas import motor
from ofertas.conectores import mercadolibre, navegador
from ofertas.conectores.base import ErrorTienda
from ofertas.tiendas import TIENDAS

# Éxito está detrás de un antibot que rechaza por rachas (HTTP 403 o conexión cortada)
# tras varias consultas seguidas. El motor no lo evade: lo reporta en la cobertura.
INESTABLES = {"exito"}
FALLAS_DE_RED = ("no respondió a tiempo", "falla de red")

# Un término que cada tienda debería tener en su catálogo.
TERMINOS = {
    "olimpica": "arroz",
    "jumbo": "arroz",
    "carulla": "arroz",
    "pepeganga": "juguete",
    "panamericana": "cuaderno",
    "velez": "zapatos",
    "arturocalle": "camisa",
    "nike": "air",
    "totto": "morral",
    "falabella": "televisor",
    "homecenter": "taladro",
    "alkosto": "televisor",
    "ktronix": "televisor",
    "alkomprar": "televisor",
    "lenovo": "thinkpad",
    "hp": "impresora",
    "exito": "televisor",
    "rappi": "arroz",
    "samsung": "televisor",
    "d1": "arroz",
    "colsubsidio": "arroz",
    "locatel": "crema",
    "easy": "taladro",
    "homesentry": "silla",
    "haceb": "nevera",
    "spring": "colchon",
    "tigo": "iphone",
    "levis": "jean",
    "americanino": "jean",
    "chevignon": "chaqueta",
    "mattelsa": "camiseta",
    "offcorss": "camiseta",
    "pilatos": "camiseta",
    "studiof": "blusa",
    "tennis": "camiseta",
    "larebaja": "crema",
    "agaval": "televisor",
    "electrojaponesa": "televisor",
    "electrobello": "televisor",
    "oportunidades": "televisor",
    "reebok": "tenis",
    "calzatodo": "tenis",
    "bosi": "zapatos",
    "cromantic": "labial",
    "mercadolibre": "portatil lenovo",
    "pcware": "portatil",
    "tauro": "portatil",
    "ikea": "silla",
    "amazon": "laptop lenovo",
    "dafiti": "tenis",
    "decathlon": "bicicleta",
    "farmatodo": "crema",
    "makro": "arroz",
    "lg": "televisor",
    "pricesmart": "arroz",
    "claro": "celular",
    "meli_oficial": "portatil lenovo",
}


@pytest.mark.red
@pytest.mark.parametrize("tienda", TIENDAS, ids=lambda t: t.id)
async def test_la_tienda_responde_con_ofertas(tienda):
    if tienda.id == "mercadolibre" and mercadolibre.credenciales() is None:
        pytest.skip("faltan MELI_CLIENT_ID y MELI_CLIENT_SECRET")
    if tienda.plataforma == "navegador" and os.environ.get("OFERTAS_PRUEBA_NAVEGADOR") != "1":
        pytest.skip("abre una ventana de Edge; actívala con OFERTAS_PRUEBA_NAVEGADOR=1")
    async with motor.crear_cliente() as cliente:
        try:
            try:
                ofertas, recibidos, _ = await motor.CONECTORES[tienda.plataforma](
                    cliente, tienda, TERMINOS[tienda.id], 10
                )
            except ErrorTienda as exc:
                # Una conexión caída es un tropiezo de la red del equipo, no de la tienda:
                # se espera un momento y se prueba una vez más antes de darla por fallida.
                if not any(m in str(exc) for m in FALLAS_DE_RED) or tienda.id in INESTABLES:
                    raise
                await asyncio.sleep(5)
                ofertas, recibidos, _ = await motor.CONECTORES[tienda.plataforma](
                    cliente, tienda, TERMINOS[tienda.id], 10
                )
        except ErrorTienda as exc:
            if tienda.id in INESTABLES:
                pytest.xfail(f"{tienda.nombre} bloquea de forma intermitente: {exc}")
            raise
        finally:
            await navegador.cerrar()
    assert recibidos > 0
    assert ofertas, "la tienda respondió, pero sin ningún producto con precio y existencias"
    assert all(o.precio > 0 and o.url.startswith("http") for o in ofertas)


@pytest.mark.red
async def test_mercadolibre_sin_credenciales_lo_dice_y_no_tumba_la_busqueda(monkeypatch):
    monkeypatch.delenv("MELI_CLIENT_ID", raising=False)
    monkeypatch.delenv("MELI_CLIENT_SECRET", raising=False)
    tiendas = [t for t in TIENDAS if t.id in ("mercadolibre", "totto")]
    resultado = await motor.buscar("morral", tiendas, limite_por_tienda=5)
    assert [t.tienda_id for t in resultado.tiendas_fallidas] == ["mercadolibre"]
    assert "sin configurar" in resultado.tiendas_fallidas[0].error
    assert resultado.ofertas


@pytest.mark.red
async def test_mercadolibre_rechaza_credenciales_falsas(monkeypatch):
    monkeypatch.setenv("MELI_CLIENT_ID", "0000000000000000")
    monkeypatch.setenv("MELI_CLIENT_SECRET", "credencial-de-prueba-invalida")
    mercadolibre._token.clear()
    tienda = next(t for t in TIENDAS if t.id == "mercadolibre")
    resultado = await motor.buscar("morral", [tienda])
    assert "rechazó las credenciales" in resultado.tiendas_fallidas[0].error
