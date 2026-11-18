"""Conector para la tienda de HP Colombia: lee la página de resultados (Magento)."""

from __future__ import annotations

import html as html_lib
import re
from urllib.parse import quote

import httpx

from ofertas.conectores.base import HTML, ErrorTienda, a_numero, pedir
from ofertas.modelos import Oferta, Tienda

SEPARADOR = 'class="item product product-item'
_RE_NOMBRE = re.compile(r'<h2 class="plp-h2-title[^>]*>(.*?)</h2>', re.S)
_RE_ENLACE = re.compile(r'<a class="product-item-link"[^>]*?href="([^"]+)"')
_RE_IMAGEN = re.compile(r'data-src="([^"]+)"')
_RE_PRECIO = re.compile(r'data-price-amount="([\d.]+)"\s+data-price-type="(\w+)"')
_RE_PRECIO_TARJETA = re.compile(r'data-price-amount="([\d.]+)"')
_RE_ESPACIOS = re.compile(r"\s+")


def interpretar_producto(
    trozo: str, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    """Convierte el HTML de una tarjeta de producto en una `Oferta`."""
    nombre = _RE_NOMBRE.search(trozo)
    enlace = _RE_ENLACE.search(trozo)
    if not (nombre and enlace):
        return None
    precios = {tipo: a_numero(valor) for valor, tipo in _RE_PRECIO.findall(trozo)}
    precio = precios.get("finalPrice", 0.0)
    if precio <= 0:
        primero = _RE_PRECIO_TARJETA.search(trozo)
        precio = a_numero(primero.group(1)) if primero else 0.0
    if precio <= 0:
        return None
    disponible = "in_stock" in trozo
    if not disponible and not incluir_agotados:
        return None
    imagen = _RE_IMAGEN.search(trozo)
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=_RE_ESPACIOS.sub(" ", html_lib.unescape(nombre.group(1))).strip(),
        marca="HP",
        precio=precio,
        precio_lista=max(precios.get("oldPrice", 0.0), precio),
        url=html_lib.unescape(enlace.group(1)),
        existencias=None if disponible else 0,
        vendedor="HP",
        imagen=imagen.group(1) if imagen else None,
    )


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    respuesta = await pedir(
        cliente, tienda.busqueda.format(q=quote(consulta, safe="")), headers=HTML
    )
    pagina = respuesta.text
    if "catalogsearch" not in pagina:
        raise ErrorTienda("la página no es la de resultados (posible bloqueo antibot)")
    trozos = pagina.split(SEPARADOR)[1:]
    ofertas = [
        oferta
        for trozo in trozos[:limite]
        if (oferta := interpretar_producto(trozo, tienda, incluir_agotados)) is not None
    ]
    return ofertas, len(trozos), None
