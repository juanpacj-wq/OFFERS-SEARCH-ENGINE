"""Conector para la tienda de Lenovo Colombia: usa la API de su propio buscador."""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir
from ofertas.modelos import Oferta, Tienda

MAX_RESULTADOS = 60
_RE_ETIQUETA = re.compile(r"<[^>]+>")


def interpretar_producto(
    producto: dict, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    precio = a_numero(producto.get("finalPrice"))
    if precio <= 0:
        return None
    disponible = producto.get("marketingStatus") == "Available"
    if not disponible and not incluir_agotados:
        return None
    nombre = producto.get("summary") or producto.get("description") or producto.get("productName")
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=_RE_ETIQUETA.sub("", nombre or "").strip(),
        marca="Lenovo",
        precio=precio,
        precio_lista=max(a_numero(producto.get("webPrice")), precio),
        url=f"{tienda.url_base}{producto.get('url') or ''}",
        existencias=None if disponible else 0,
        vendedor="Lenovo",
        modelo=str(producto.get("productCode") or "").strip(),
        # La ruta trae la categoría en español: /p/portatiles/thinkpad/thinkpad-e/...
        categoria=" ".join((producto.get("url") or "").split("/")[2:-1]).replace("-", " "),
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
        headers={"Referer": "https://www.lenovo.com/co/es/", "Origin": "https://www.lenovo.com"},
    )
    datos = leer_json(respuesta)
    cuerpo = datos.get("data") if isinstance(datos, dict) else None
    if not isinstance(cuerpo, dict):
        raise ErrorTienda("el buscador devolvió un JSON con forma inesperada")
    productos = [p for grupo in cuerpo.get("data") or [] for p in grupo.get("products") or []]
    ofertas = [
        oferta
        for producto in productos
        if (oferta := interpretar_producto(producto, tienda, incluir_agotados)) is not None
    ]
    return ofertas, len(productos), cuerpo.get("productCount")
