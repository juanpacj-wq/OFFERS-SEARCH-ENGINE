"""Conector para Falabella y Homecenter: leen el JSON incrustado en la página de búsqueda.

Las dos tiendas son del mismo grupo y comparten plataforma; cambian los nombres de
los tipos de precio y el lugar donde quedan los resultados.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ofertas.conectores.base import HTML, datos_de_next, pedir, precio_de_texto
from ofertas.modelos import Oferta, Tienda

MAX_PAGINAS = 4


def _resultados(datos: dict) -> tuple[list[dict], dict]:
    """Ubica la lista de productos y la paginación, que cambian según la tienda."""
    pagina = (datos.get("props") or {}).get("pageProps") or {}
    if isinstance(pagina.get("results"), list):
        return pagina["results"], pagina.get("pagination") or {}
    busqueda = (pagina.get("searchProps") or {}).get("searchData") or {}
    if busqueda.get("results"):
        return busqueda["results"], busqueda.get("pagination") or {}
    # Cuando la búsqueda coincide con una categoría, la tienda redirige a ella.
    categoria = ((pagina.get("categoryProps") or {}).get("categoryData") or {}).get("results")
    if isinstance(categoria, dict) and isinstance(categoria.get("results"), list):
        return categoria["results"], categoria.get("pagination") or {}
    return [], {}


def interpretar_producto(producto: dict, tienda: Tienda) -> Oferta | None:
    """Convierte un producto de Falabella u Homecenter en una `Oferta`."""
    normal = tarjeta = 0.0
    publicos: list[float] = []
    for precio in producto.get("prices") or []:
        valor = precio_de_texto(precio.get("priceWithoutFormatting") or precio.get("price"))
        if valor <= 0:
            continue
        tipo = str(precio.get("type") or "").lower()
        if "cmr" in tipo:
            tarjeta = valor
        elif "normal" in tipo:
            normal = valor
        else:
            publicos.append(valor)
    precio_final = min(publicos) if publicos else normal
    if precio_final <= 0:
        return None
    url = producto.get("url")
    if not url and producto.get("productId"):
        url = f"{tienda.busqueda.split('/search')[0]}/product/{producto['productId']}"
    imagenes = producto.get("mediaUrls") or []
    return Oferta(
        tienda_id=tienda.id,
        tienda=tienda.nombre,
        nombre=(producto.get("displayName") or "").strip(),
        marca=(producto.get("brand") or "").strip(),
        precio=precio_final,
        precio_lista=max(normal, precio_final),
        url=url or "",
        vendedor=producto.get("sellerName"),
        imagen=imagenes[0] if imagenes else None,
        precio_tarjeta=tarjeta if 0 < tarjeta < precio_final else None,
    )


async def buscar(
    cliente: httpx.AsyncClient,
    tienda: Tienda,
    consulta: str,
    limite: int = 50,
    incluir_agotados: bool = False,
) -> tuple[list[Oferta], int, int | None]:
    """Busca en la página de resultados. La tienda solo lista productos disponibles."""
    ofertas: list[Oferta] = []
    recibidos = 0
    total: int | None = None
    url: str | httpx.URL = tienda.busqueda.format(q=quote(consulta, safe=""))
    pagina = 1
    while True:
        respuesta = await pedir(cliente, url, headers=HTML)
        productos, paginacion = _resultados(datos_de_next(respuesta.text))
        total = paginacion.get("count") or total
        recibidos += len(productos)
        for producto in productos:
            oferta = interpretar_producto(producto, tienda)
            if oferta is not None:
                ofertas.append(oferta)
        por_pagina = paginacion.get("perPage") or len(productos) or 1
        # Cada página pesa cerca de 2 MB: solo se pide otra si falta al menos media página.
        faltan = limite - recibidos
        if not productos or faltan < por_pagina / 2 or pagina >= MAX_PAGINAS:
            break
        if total is not None and recibidos >= total:
            break
        pagina += 1
        # Se parte de la URL final porque la tienda puede haber redirigido a una categoría.
        url = respuesta.url.copy_merge_params({"page": str(pagina)})
    return ofertas, recibidos, total
