"""Conector para la tienda de Samsung Colombia: usa la API de su tienda en línea.

Dos particularidades comprobadas:

- El buscador ordena mal por relevancia (una búsqueda de celulares trae primero
  repuestos), así que se revisan más resultados de los pedidos y el filtro por
  nombre del motor hace el resto.
- Se toma el precio de venta que informa la API. Las promociones condicionadas
  (tipo `SPECIAL`: medio de pago, cupones) no se reflejan, de modo que el precio
  real en el sitio puede ser menor.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ofertas.conectores.base import ErrorTienda, a_numero, leer_json, pedir
from ofertas.modelos import Oferta, Tienda

TAMANO_PAGINA = 100
MINIMO_A_REVISAR = 200
CAMPOS = (
    "products(code,name,price(value),allPrices(priceType,value),"
    "stock(stockLevel,stockLevelStatus),picture(url)),pagination"
)


def interpretar_producto(
    producto: dict, tienda: Tienda, incluir_agotados: bool = False
) -> Oferta | None:
    precio = a_numero((producto.get("price") or {}).get("value"))
    if precio <= 0:
        return None
    existencias_api = producto.get("stock") or {}
    disponible = existencias_api.get("stockLevelStatus") in ("inStock", "lowStock")
    if not disponible and not incluir_agotados:
        return None
    lista = max(
        (a_numero(p.get("value")) for p in producto.get("allPrices") or []
         if p.get("priceType") == "RRP"),
        default=0.0,
    )
    codigo = producto.get("code") or ""
    unidades = existencias_api.get("stockLevel")
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=(producto.get("name") or "").strip(),
        marca="Samsung",
        precio=precio,
        precio_lista=max(lista, precio),
        # La API no entrega el enlace del producto: se enlaza la búsqueda por su código.
        url=f"{tienda.url_base}/search/?searchvalue={quote(codigo, safe='')}",
        existencias=(int(unidades) if isinstance(unidades, int) else None) if disponible else 0,
        vendedor="Samsung",
        modelo=codigo,
        imagen=(producto.get("picture") or {}).get("url"),
    )


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    ofertas: list[Oferta] = []
    recibidos = 0
    total: int | None = None
    a_revisar = max(limite, MINIMO_A_REVISAR)
    pagina = 0
    while recibidos < a_revisar:
        respuesta = await pedir(
            cliente,
            tienda.busqueda.format(q=quote(consulta, safe=""), n=TAMANO_PAGINA, p=pagina)
            + f"&fields={quote(CAMPOS, safe='(),')}",
        )
        datos = leer_json(respuesta)
        productos = datos.get("products") if isinstance(datos, dict) else None
        if not isinstance(productos, list):
            raise ErrorTienda("la tienda devolvió un JSON con forma inesperada")
        paginacion = datos.get("pagination") or {}
        total = paginacion.get("totalResults", total)
        recibidos += len(productos)
        for producto in productos:
            oferta = interpretar_producto(producto, tienda, incluir_agotados)
            if oferta is not None:
                ofertas.append(oferta)
        pagina += 1
        if not productos or pagina >= (paginacion.get("totalPages") or 0):
            break
    return ofertas, recibidos, total
