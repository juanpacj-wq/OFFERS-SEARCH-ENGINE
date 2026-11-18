"""Conector para tiendas VTEX: consulta el catálogo público en JSON, sin navegador."""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir
from ofertas.modelos import Oferta, Tienda

__all__ = ["ErrorTienda", "buscar", "interpretar_producto"]

RUTA_BUSQUEDA = "/api/catalog_system/pub/products/search"
# VTEX rechaza rangos de más de 50 productos por petición.
TAMANO_PAGINA = 50
_RE_TOTAL = re.compile(r"/(\d+)\s*$")


def _mejor_variante(producto: dict, incluir_agotados: bool) -> dict | None:
    """Elige la combinación variante y vendedor más barata de un producto."""
    mejor: dict | None = None
    for item in producto.get("items") or []:
        for vendedor in item.get("sellers") or []:
            oferta = vendedor.get("commertialOffer") or {}
            precio = a_numero(oferta.get("Price"))
            existencias = int(a_numero(oferta.get("AvailableQuantity")))
            if precio <= 0:
                continue
            if existencias <= 0 and not incluir_agotados:
                continue
            candidato = {
                "precio": precio,
                "precio_lista": a_numero(oferta.get("ListPrice")) or precio,
                "existencias": existencias,
                "ean": (item.get("ean") or "").strip() or None,
                "vendedor": vendedor.get("sellerName"),
                "imagen": ((item.get("images") or [{}])[0]).get("imageUrl"),
            }
            # A igual precio se prefiere la variante que sí tiene existencias.
            clave = (existencias <= 0, precio)
            if mejor is None or clave < mejor["_clave"]:
                candidato["_clave"] = clave
                mejor = candidato
    return mejor


def interpretar_producto(
    producto: dict, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    """Convierte un producto del catálogo VTEX en una `Oferta`, o None si no se vende."""
    variante = _mejor_variante(producto, incluir_agotados)
    if variante is None:
        return None
    eans = []
    for item in producto.get("items") or []:
        ean = (item.get("ean") or "").strip()
        if ean and ean not in eans:
            eans.append(ean)
    # Algunas tiendas publican el enlace con un dominio interno (Carulla usa
    # secure.carulla.com); la ruta sobre el dominio público es la que sirve.
    if producto.get("linkText"):
        url = f"{tienda.url_base}/{producto['linkText']}/p"
    else:
        url = producto.get("link") or ""
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=(producto.get("productName") or "").strip(),
        marca=(producto.get("brand") or "").strip(),
        precio=variante["precio"],
        precio_lista=variante["precio_lista"],
        url=url,
        existencias=variante["existencias"],
        ean=variante["ean"],
        eans=eans,
        vendedor=variante["vendedor"],
        imagen=variante["imagen"],
    )


def _total_desde_cabecera(respuesta: httpx.Response) -> int | None:
    """VTEX informa el total en la cabecera `resources`, con la forma `0-49/334`."""
    coincidencia = _RE_TOTAL.search(respuesta.headers.get("resources", ""))
    return int(coincidencia.group(1)) if coincidencia else None


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = TAMANO_PAGINA,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    """Busca `consulta` en una tienda VTEX.

    Devuelve las ofertas, cuántos productos entregó la tienda y el total que la
    tienda dice tener para esa búsqueda (None si no lo informa).
    """
    ofertas: list[Oferta] = []
    recibidos = 0
    total: int | None = None
    desde = 0
    while desde < limite:
        hasta = min(desde + TAMANO_PAGINA, limite) - 1
        # Se arma a mano: VTEX responde 400 si el espacio llega como "+" y no como "%20".
        # El 206 es su respuesta normal cuando hay más resultados que los pedidos.
        respuesta = await pedir(
            cliente,
            f"{tienda.url_base}{RUTA_BUSQUEDA}"
            f"?ft={quote(consulta, safe='')}&_from={desde}&_to={hasta}",
        )
        productos = leer_json(respuesta)
        if not isinstance(productos, list):
            raise ErrorTienda("devolvió un JSON con forma inesperada")
        total = _total_desde_cabecera(respuesta) or total
        recibidos += len(productos)
        for producto in productos:
            oferta = interpretar_producto(producto, tienda, incluir_agotados)
            if oferta is not None:
                ofertas.append(oferta)
        if len(productos) < hasta - desde + 1:
            break
        if total is not None and hasta + 1 >= total:
            break
        desde = hasta + 1
    return ofertas, recibidos, total
