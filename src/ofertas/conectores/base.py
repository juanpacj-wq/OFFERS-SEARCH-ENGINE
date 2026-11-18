"""Utilidades comunes a todos los conectores."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

HTML = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "es-CO,es;q=0.9"}
_RE_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class ErrorTienda(Exception):
    """La tienda no respondió con datos utilizables."""


def a_numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def precio_de_texto(texto: Any) -> float:
    """Convierte un precio escrito a la colombiana: "$ 2.569.900" pasa a 2569900."""
    if isinstance(texto, list):
        texto = texto[0] if texto else ""
    if isinstance(texto, (int, float)):
        return float(texto)
    entero = str(texto or "").split(",")[0]
    digitos = re.sub(r"\D", "", entero)
    return float(digitos) if digitos else 0.0


def codigo_de_barras(valor: Any) -> str | None:
    """Devuelve el valor solo si tiene forma de GTIN (8, 12, 13 o 14 dígitos)."""
    texto = str(valor or "").strip()
    return texto if texto.isdigit() and len(texto) in (8, 12, 13, 14) else None


async def pedir(
    cliente: httpx.AsyncClient, url: str | httpx.URL, *, metodo: str = "GET", **opciones: Any
) -> httpx.Response:
    """Hace la petición y traduce cualquier falla a un `ErrorTienda` con el motivo."""
    try:
        try:
            respuesta = await cliente.request(metodo, url, **opciones)
        except (httpx.ConnectTimeout, httpx.ConnectError):
            # Una conexión que no alcanza a abrirse suele ser un tropiezo de la red: se
            # intenta una vez más. No se reintenta si el servidor ya respondió algo.
            respuesta = await cliente.request(metodo, url, **opciones)
    except httpx.TimeoutException as exc:
        raise ErrorTienda("no respondió a tiempo") from exc
    except httpx.HTTPError as exc:
        raise ErrorTienda(f"falla de red: {type(exc).__name__}") from exc
    if respuesta.status_code not in (200, 206):
        raise ErrorTienda(f"respondió HTTP {respuesta.status_code}")
    return respuesta


def leer_json(respuesta: httpx.Response) -> Any:
    try:
        return respuesta.json()
    except ValueError as exc:
        raise ErrorTienda("no devolvió JSON (posible bloqueo antibot)") from exc


def datos_de_next(html: str) -> dict:
    """Extrae el JSON que las páginas hechas con Next.js traen incrustado."""
    coincidencia = _RE_NEXT.search(html)
    if not coincidencia:
        raise ErrorTienda("la página no trae datos incrustados (posible bloqueo antibot)")
    try:
        return json.loads(coincidencia.group(1))
    except ValueError as exc:
        raise ErrorTienda("los datos incrustados de la página no son JSON válido") from exc
