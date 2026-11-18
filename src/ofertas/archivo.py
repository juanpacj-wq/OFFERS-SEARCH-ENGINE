"""Precios pasados de un producto según el archivo de Internet (Wayback Machine).

Para lo que solo vende una tienda no hay otra tienda con qué comparar, y el historial
propio tarda en llenarse. El archivo de Internet guarda copias antiguas de muchas
páginas de producto: si hace meses la misma página mostraba un precio parecido al de
hoy, el "antes" que anuncia la tienda está inflado.

No todas las páginas tienen copia (cerca de un tercio en las pruebas) y bajar una copia
toma varios segundos, así que esto se usa solo en la verificación a fondo.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir

URL_DISPONIBLE = "https://archive.org/wayback/available"
URL_COPIA = "https://web.archive.org/web/{marca}id_/{url}"
# Se buscan copias cercanas a estas antigüedades.
ANTIGUEDADES = (timedelta(days=90), timedelta(days=365))
# Una copia más reciente que esto puede ser de la misma promoción: no sirve de referencia.
MINIMO = timedelta(days=21)
VIGENCIA_CACHE = timedelta(days=30)
ESPERA = 20.0
_RE_LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_RE_META = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)="(?:product:price:amount|og:price:amount|price)"'
    r'[^>]+content="([\d.,]+)"'
)
_RE_ESTADO = re.compile(r'"(?:Price|sellingPrice|spotPrice)"\s*:\s*(\d+(?:\.\d+)?)')


def precio_en_pagina(html: str) -> float:
    """Precio de venta que mostraba una página de producto, o 0 si no se reconoce.

    Prueba, en orden, los datos estructurados (JSON-LD), las etiquetas meta de precio y
    el estado incrustado de las tiendas VTEX.
    """
    hallados: list[float] = []

    def recorrer(nodo) -> None:
        if isinstance(nodo, dict):
            if nodo.get("@type") in ("Offer", "AggregateOffer"):
                for clave in ("price", "lowPrice"):
                    valor = a_numero(nodo.get(clave))
                    if valor > 0:
                        hallados.append(valor)
            for valor in nodo.values():
                recorrer(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                recorrer(valor)

    for bloque in _RE_LD.findall(html):
        try:
            recorrer(json.loads(bloque))
        except ValueError:
            continue
    if hallados:
        return min(hallados)
    meta = _RE_META.search(html)
    if meta:
        valor = a_numero(meta.group(1).replace(",", ""))
        if valor > 0:
            return valor
    estado = [a_numero(v) for v in _RE_ESTADO.findall(html)]
    estado = [v for v in estado if v > 0]
    return min(estado) if estado else 0.0


async def _copia_cercana(cliente: httpx.AsyncClient, url: str, cuando: datetime) -> str | None:
    """Marca de tiempo (AAAAMMDDhhmmss) de la copia más cercana a `cuando`, si la hay."""
    respuesta = await pedir(
        cliente, URL_DISPONIBLE, params={"url": url, "timestamp": cuando.strftime("%Y%m%d")},
        timeout=ESPERA,
    )
    cercana = ((leer_json(respuesta) or {}).get("archived_snapshots") or {}).get("closest")
    if not cercana or str(cercana.get("status")) != "200":
        return None
    return cercana.get("timestamp")


async def consultar(
    cliente: httpx.AsyncClient, url: str, ahora: datetime | None = None
) -> list[dict]:
    """Precios que mostraba la página en copias antiguas: [{"fecha": ..., "precio": ...}]."""
    ahora = ahora or datetime.now(UTC)
    marcas: list[str] = []
    for antiguedad in ANTIGUEDADES:
        try:
            marca = await _copia_cercana(cliente, url, ahora - antiguedad)
        except ErrorTienda:
            continue
        if marca and marca not in marcas:
            fecha = datetime.strptime(marca[:8], "%Y%m%d").replace(tzinfo=UTC)
            if ahora - fecha >= MINIMO:
                marcas.append(marca)
    precios = []
    for marca in marcas:
        try:
            copia = await pedir(
                cliente, URL_COPIA.format(marca=marca, url=url),
                headers={"Accept": "text/html"}, timeout=ESPERA,
            )
        except ErrorTienda:
            continue
        precio = precio_en_pagina(copia.text)
        if precio > 0:
            precios.append({"fecha": f"{marca[:4]}-{marca[4:6]}-{marca[6:8]}", "precio": precio})
    return sorted(precios, key=lambda p: p["fecha"])


async def precios_pasados(
    cliente: httpx.AsyncClient, conexion: sqlite3.Connection, url: str
) -> list[dict]:
    """Como `consultar`, pero guardando el resultado un mes (también cuando no hay copias)."""
    fila = conexion.execute(
        "SELECT fecha, datos FROM cache_internacional WHERE fuente = 'archivo' AND consulta = ?",
        (url,),
    ).fetchone()
    if fila and datetime.now(UTC) - datetime.fromisoformat(fila["fecha"]) < VIGENCIA_CACHE:
        try:
            return json.loads(fila["datos"])
        except ValueError:
            pass
    try:
        precios = await asyncio.wait_for(consultar(cliente, url), ESPERA * 3)
    except (TimeoutError, ErrorTienda):
        return []
    except Exception:
        return []  # una copia rara no debe tumbar la verificación
    with conexion:
        conexion.execute(
            "INSERT INTO cache_internacional (fuente, consulta, fecha, datos)"
            " VALUES ('archivo', ?, ?, ?) ON CONFLICT (fuente, consulta) DO UPDATE SET"
            " fecha = excluded.fecha, datos = excluded.datos",
            (url, datetime.now(UTC).isoformat(), json.dumps(precios)),
        )
    return precios
