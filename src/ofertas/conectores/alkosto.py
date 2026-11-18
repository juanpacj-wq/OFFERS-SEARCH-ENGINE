"""Conector para Alkosto, Ktronix y Alkomprar: consultan su índice de búsqueda Algolia.

Las tres tiendas publican en cada página la configuración del buscador (aplicación,
llave de solo búsqueda e índice), la misma que usa el navegador de cualquier visitante.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

from ofertas.conectores.base import (
    HTML,
    ErrorTienda,
    a_numero,
    codigo_de_barras,
    leer_json,
    pedir,
)
from ofertas.modelos import Oferta, Tienda

# Solo las páginas de búsqueda y de categoría traen la configuración, y pesan más de
# 1 MB: por eso se guarda en disco unas horas en vez de leerla en cada búsqueda.
RUTA_CONFIGURACION = "/search?text=tv"
VIGENCIA_SEGUNDOS = 6 * 3600
MAX_RESULTADOS = 200
_RE_BLOQUE = re.compile(r"algolia\s*:\s*\{(.{0,4000}?)indexName\s*:\s*'([^']+)'", re.S)
_RE_APLICACION = re.compile(r"applicationId\s*:\s*'([^']+)'")
_RE_LLAVE = re.compile(r"apiKey\s*:\s*'([^']+)'")


def _archivo(tienda: Tienda) -> Path:
    carpeta = Path(os.environ.get("OFERTAS_CACHE") or Path.home() / ".cache" / "ofertas")
    return carpeta / f"buscador-{tienda.id}.json"


def leer_configuracion(html: str) -> tuple[str, str, str]:
    """Saca de la página la aplicación, la llave de búsqueda y el nombre del índice."""
    bloque = _RE_BLOQUE.search(html)
    aplicacion = _RE_APLICACION.search(bloque.group(1)) if bloque else None
    llave = _RE_LLAVE.search(bloque.group(1)) if bloque else None
    if not (bloque and aplicacion and llave):
        raise ErrorTienda("la página no trae la configuración del buscador")
    return aplicacion.group(1), llave.group(1), bloque.group(2)


def interpretar_producto(
    producto: dict, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    """Convierte un resultado del índice en una `Oferta`."""
    lista = a_numero(producto.get("pricevalue_cop_double") or producto.get("baseprice_cop_string"))
    precio = (
        a_numero(producto.get("lowestprice_double"))
        or a_numero(producto.get("discountprice_double"))
        or lista
    )
    if precio <= 0:
        return None
    existencias = int(a_numero(producto.get("stocklevel_int")))
    disponible = bool(producto.get("instockflag_boolean")) and existencias > 0
    if not disponible and not incluir_agotados:
        return None
    marcas = producto.get("brand_string_mv") or []
    ean = codigo_de_barras(producto.get("code_string"))
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=(producto.get("name_text_es") or "").strip(),
        marca=(producto.get("marca_text") or (marcas[0] if marcas else "")).strip(),
        precio=precio,
        precio_lista=max(lista, precio),
        url=tienda.url_base + (producto.get("url_es_string") or ""),
        existencias=existencias if disponible else 0,
        ean=ean,
        eans=[ean] if ean else [],
        imagen=producto.get("img-310wx310h_string"),
        modelo=str(
            (producto.get("linea-modelo_string_mv") or producto.get(
                "linea-modelo-referencia_string_mv") or [""])[0]
        ).strip(),
    )


async def _configuracion(
    cliente: httpx.AsyncClient, tienda: Tienda, renovar: bool = False
) -> tuple[str, str, str]:
    archivo = _archivo(tienda)
    if not renovar:
        try:
            guardado = json.loads(archivo.read_text(encoding="utf-8"))
            if time.time() - guardado["momento"] < VIGENCIA_SEGUNDOS:
                return tuple(guardado["configuracion"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    respuesta = await pedir(cliente, tienda.url_base + RUTA_CONFIGURACION, headers=HTML)
    configuracion = leer_configuracion(respuesta.text)
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(
            json.dumps({"momento": time.time(), "configuracion": configuracion}),
            encoding="utf-8",
        )
    except OSError:
        pass  # Sin caché el motor sigue funcionando, solo más lento.
    return configuracion


async def _consultar(
    cliente: httpx.AsyncClient, configuracion: tuple[str, str, str], consulta: str, limite: int
) -> httpx.Response:
    aplicacion, llave, indice = configuracion
    return await pedir(
        cliente,
        f"https://{aplicacion}-dsn.algolia.net/1/indexes/{indice}/query",
        metodo="POST",
        headers={"X-Algolia-Application-Id": aplicacion, "X-Algolia-API-Key": llave},
        json={"query": consulta, "hitsPerPage": min(limite, MAX_RESULTADOS)},
    )


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    try:
        respuesta = await _consultar(
            cliente, await _configuracion(cliente, tienda), consulta, limite
        )
    except ErrorTienda:
        # La llave guardada pudo vencer: se lee de nuevo de la tienda y se reintenta.
        respuesta = await _consultar(
            cliente, await _configuracion(cliente, tienda, renovar=True), consulta, limite
        )
    datos = leer_json(respuesta)
    productos = datos.get("hits") if isinstance(datos, dict) else None
    if not isinstance(productos, list):
        raise ErrorTienda("el buscador devolvió un JSON con forma inesperada")
    ofertas = [
        oferta
        for producto in productos
        if (oferta := interpretar_producto(producto, tienda, incluir_agotados)) is not None
    ]
    return ofertas, len(productos), datos.get("nbHits")
