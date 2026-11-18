"""Conector para MercadoLibre Colombia por su API oficial.

MercadoLibre no entrega precios sin autenticación (comprobado el 2026-11-18: el
listado web pide captcha y la API responde 403). Este conector usa las credenciales
de una aplicación registrada en https://developers.mercadolibre.com.co, leídas de
las variables de entorno MELI_CLIENT_ID y MELI_CLIENT_SECRET.

ADVERTENCIA: la forma de las respuestas se tomó de la documentación pública y NO se
ha verificado contra la API real, porque aún no hay credenciales. Lo verificado en
vivo es solo el comportamiento sin credenciales.
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, codigo_de_barras, leer_json, pedir
from ofertas.modelos import Oferta, Tienda

API = "https://api.mercadolibre.com"
SITIO = "MCO"
# Cada producto necesita una petición aparte para conocer su precio.
MAX_PRODUCTOS = 20
_token: dict[str, str] = {}


def credenciales() -> tuple[str, str] | None:
    identificador = os.environ.get("MELI_CLIENT_ID", "").strip()
    secreto = os.environ.get("MELI_CLIENT_SECRET", "").strip()
    return (identificador, secreto) if identificador and secreto else None


async def _obtener_token(cliente: httpx.AsyncClient) -> str:
    par = credenciales()
    if par is None:
        raise ErrorTienda(
            "sin configurar: define MELI_CLIENT_ID y MELI_CLIENT_SECRET con las "
            "credenciales de tu aplicación de MercadoLibre"
        )
    if par[0] not in _token:
        try:
            respuesta = await pedir(
                cliente, f"{API}/oauth/token", metodo="POST",
                data={"grant_type": "client_credentials",
                      "client_id": par[0], "client_secret": par[1]},
            )
        except ErrorTienda as exc:
            raise ErrorTienda(f"MercadoLibre rechazó las credenciales ({exc})") from exc
        token = leer_json(respuesta).get("access_token")
        if not token:
            raise ErrorTienda("MercadoLibre no entregó un token de acceso")
        _token[par[0]] = token
    return _token[par[0]]


def interpretar_producto(producto: dict, tienda: Tienda) -> Oferta | None:
    """Convierte el detalle de un producto de catálogo en una `Oferta`."""
    ganador = producto.get("buy_box_winner") or {}
    precio = a_numero(ganador.get("price"))
    if precio <= 0:
        return None
    atributos = {a.get("id"): a.get("value_name") for a in producto.get("attributes") or []}
    ean = codigo_de_barras(atributos.get("GTIN"))
    imagenes = producto.get("pictures") or []
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=(producto.get("name") or "").strip(),
        marca=(atributos.get("BRAND") or "").strip(),
        precio=precio,
        precio_lista=max(a_numero(ganador.get("original_price")), precio),
        url=producto.get("permalink") or f"{tienda.url_base}/p/{producto.get('id', '')}",
        moneda=ganador.get("currency_id") or "COP",
        ean=ean,
        eans=[ean] if ean else [],
        imagen=imagenes[0].get("url") if imagenes else None,
    )


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    cabeceras = {"Authorization": f"Bearer {await _obtener_token(cliente)}"}
    respuesta = await pedir(
        cliente,
        f"{API}/products/search?status=active&site_id={SITIO}"
        f"&q={quote(consulta, safe='')}&limit={min(limite, MAX_PRODUCTOS)}",
        headers=cabeceras,
    )
    datos = leer_json(respuesta)
    encontrados = datos.get("results") if isinstance(datos, dict) else None
    if not isinstance(encontrados, list):
        raise ErrorTienda("la API devolvió un JSON con forma inesperada")

    async def detalle(identificador: str) -> dict | None:
        try:
            return leer_json(
                await pedir(cliente, f"{API}/products/{identificador}", headers=cabeceras)
            )
        except ErrorTienda:
            return None  # Un producto que falla no descarta los demás.

    detalles = await asyncio.gather(
        *(detalle(p["id"]) for p in encontrados[:MAX_PRODUCTOS] if p.get("id"))
    )
    ofertas = [
        oferta
        for producto in detalles
        if isinstance(producto, dict)
        and (oferta := interpretar_producto(producto, tienda)) is not None
    ]
    return ofertas, len(encontrados), (datos.get("paging") or {}).get("total")
