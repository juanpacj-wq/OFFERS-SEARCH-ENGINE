"""Conector para Rappi: lee el JSON incrustado en su página de búsqueda.

Rappi es un domicilio, no una tienda única: cada resultado pertenece a un comercio
(Turbo, Éxito, La Rebaja) y el precio no incluye el envío. Sin sesión, la página
responde para una ubicación por defecto en Bogotá.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

import httpx

from ofertas.conectores.base import HTML, a_numero, datos_de_next, pedir
from ofertas.modelos import Oferta, Tienda

_RE_LD = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def _enlaces_por_nombre(html: str) -> dict[str, str]:
    """Los enlaces de producto solo vienen en los datos estructurados de la página."""
    enlaces: dict[str, str] = {}
    for bloque in _RE_LD.findall(html):
        try:
            datos = json.loads(bloque)
        except ValueError:
            continue
        if not isinstance(datos, dict):
            continue
        for elemento in datos.get("itemListElement") or []:
            item = elemento.get("item") if isinstance(elemento, dict) else None
            if isinstance(item, dict) and item.get("name") and item.get("url"):
                enlaces.setdefault(item["name"], item["url"])
    return enlaces


def _comercios(datos: dict) -> list[dict]:
    respaldo = ((datos.get("props") or {}).get("pageProps") or {}).get("fallback") or {}
    for valor in respaldo.values():
        if isinstance(valor, dict) and isinstance(valor.get("stores"), list):
            return valor["stores"]
    return []


def interpretar_producto(
    producto: dict,
    comercio: dict,
    tienda: Tienda,
    enlaces: dict[str, str] | None = None,
    incluir_agotados: bool = False,
) -> Oferta | None:
    precio = a_numero(producto.get("price"))
    if precio <= 0:
        return None
    disponible = bool(producto.get("inStock")) and producto.get("isAvailable", True)
    if not disponible and not incluir_agotados:
        return None
    nombre = (producto.get("name") or "").strip()
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=nombre,
        marca="",
        precio=precio,
        precio_lista=max(a_numero(producto.get("realPrice")), precio),
        url=(enlaces or {}).get(nombre) or comercio.get("url") or tienda.url_base,
        existencias=None if disponible else 0,
        vendedor=comercio.get("storeName"),
        imagen=producto.get("image"),
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
    comercios = _comercios(datos_de_next(respuesta.text))
    enlaces = _enlaces_por_nombre(respuesta.text)
    ofertas: list[Oferta] = []
    recibidos = 0
    for comercio in comercios:
        for producto in comercio.get("products") or []:
            recibidos += 1
            oferta = interpretar_producto(producto, comercio, tienda, enlaces, incluir_agotados)
            if oferta is not None:
                ofertas.append(oferta)
    return ofertas[:limite], recibidos, None
