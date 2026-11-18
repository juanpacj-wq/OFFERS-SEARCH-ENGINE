"""Conector para IKEA Colombia: usa la API de su propio buscador."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir
from ofertas.modelos import Oferta, Tienda

MAX_RESULTADOS = 100


def interpretar_producto(
    producto: dict, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    venta = producto.get("salesPrice") or {}
    precio = a_numero(venta.get("numeral"))
    if precio <= 0:
        return None
    disponible = bool(producto.get("onlineSellable")) and (
        producto.get("homeDelivery") != "OUT_OF_STOCK"
    )
    if not disponible and not incluir_agotados:
        return None
    anterior = a_numero((venta.get("previous") or {}).get("numeral"))
    # En IKEA el nombre es el de la línea ("SANDSBERG"); el tipo dice qué es ("Silla").
    partes = [producto.get("name"), producto.get("typeName"), producto.get("validDesignText")]
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=" ".join(p.strip() for p in partes if p and p.strip()),
        marca="IKEA",
        precio=precio,
        precio_lista=max(anterior, precio),
        url=producto.get("pipUrl") or tienda.url_base,
        existencias=None if disponible else 0,
        moneda=venta.get("currencyCode") or "COP",
        vendedor="IKEA",
        modelo=str(producto.get("itemNoGlobal") or producto.get("itemNo") or "").strip(),
        imagen=producto.get("mainImageUrl"),
        # Solo los dos niveles más específicos: el primero ("Sillas y mesas") es tan
        # amplio que haría pasar una mesa por silla.
        categoria=" ".join(
            c.get("name") or "" for c in (producto.get("categoryPath") or [])[-2:]
        ),
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
        tienda.busqueda.format(q=quote(consulta, safe=""), n=min(limite, MAX_RESULTADOS)),
    )
    datos = leer_json(respuesta)
    principal = (
        (((datos.get("searchResultPage") or {}).get("products") or {}).get("main") or {})
        if isinstance(datos, dict)
        else None
    )
    elementos = principal.get("items") if isinstance(principal, dict) else None
    if not isinstance(elementos, list):
        raise ErrorTienda("el buscador devolvió un JSON con forma inesperada")
    productos = [e["product"] for e in elementos if isinstance(e.get("product"), dict)]
    ofertas = [
        oferta
        for producto in productos
        if (oferta := interpretar_producto(producto, tienda, incluir_agotados)) is not None
    ]
    return ofertas, len(productos), principal.get("max")
