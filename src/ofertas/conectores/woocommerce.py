"""Conector para tiendas WooCommerce que tienen abierta su API de tienda (Store API).

No todas la exponen: Ara, por ejemplo, la tiene deshabilitada y responde 403.
"""

from __future__ import annotations

import html
from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir
from ofertas.modelos import Oferta, Tienda

RUTA = "/wp-json/wc/store/v1/products"
MAX_POR_PAGINA = 100


def interpretar_producto(
    producto: dict, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    precios = producto.get("prices") or {}
    # Los precios llegan en la unidad menor de la moneda (centavos si los hubiera).
    divisor = 10 ** int(a_numero(precios.get("currency_minor_unit")))
    precio = a_numero(precios.get("price")) / divisor
    if precio <= 0:
        return None
    disponible = bool(producto.get("is_in_stock"))
    if not disponible and not incluir_agotados:
        return None
    marcas = producto.get("brands") or []
    imagenes = producto.get("images") or []
    restantes = producto.get("low_stock_remaining")
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=html.unescape(producto.get("name") or "").strip(),
        marca=html.unescape(marcas[0].get("name") or "") if marcas else "",
        precio=precio,
        precio_lista=max(a_numero(precios.get("regular_price")) / divisor, precio),
        url=producto.get("permalink") or tienda.url_base,
        existencias=(restantes if isinstance(restantes, int) else None) if disponible else 0,
        moneda=precios.get("currency_code") or "COP",
        imagen=imagenes[0].get("src") if imagenes else None,
    )


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    respuesta = await pedir(
        cliente,
        f"{tienda.url_base}{RUTA}?search={quote(consulta, safe='')}"
        f"&per_page={min(limite, MAX_POR_PAGINA)}",
    )
    productos = leer_json(respuesta)
    if not isinstance(productos, list):
        raise ErrorTienda("la API de la tienda devolvió un JSON con forma inesperada")
    ofertas = [
        oferta
        for producto in productos
        if (oferta := interpretar_producto(producto, tienda, incluir_agotados)) is not None
    ]
    total = respuesta.headers.get("X-WP-Total", "")
    return ofertas, len(productos), int(total) if total.isdigit() else None
