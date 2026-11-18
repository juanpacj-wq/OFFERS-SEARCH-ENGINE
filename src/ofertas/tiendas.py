"""Registro de tiendas. Agregar una tienda VTEX es agregar una línea aquí."""

from __future__ import annotations

from ofertas.modelos import Tienda

TIENDAS: tuple[Tienda, ...] = (
    # Catálogo VTEX en JSON.
    Tienda("olimpica", "Olímpica", "https://www.olimpica.com"),
    Tienda("jumbo", "Jumbo", "https://www.jumbocolombia.com"),
    Tienda("carulla", "Carulla", "https://www.carulla.com"),
    Tienda("pepeganga", "Pepe Ganga", "https://www.pepeganga.com"),
    Tienda("panamericana", "Panamericana", "https://www.panamericana.com.co"),
    Tienda("velez", "Vélez", "https://www.velez.com.co"),
    Tienda("arturocalle", "Arturo Calle", "https://www.arturocalle.com"),
    Tienda("nike", "Nike", "https://www.nike.com.co"),
    Tienda("totto", "Totto", "https://co.totto.com"),
    Tienda("exito", "Éxito", "https://www.exito.com"),
    Tienda("d1", "D1", "https://www.d1.com.co"),
    Tienda("colsubsidio", "Colsubsidio", "https://www.mercadocolsubsidio.com"),
    Tienda("locatel", "Locatel", "https://www.locatelcolombia.com"),
    Tienda("easy", "Easy", "https://www.easy.com.co"),
    Tienda("homesentry", "Home Sentry", "https://www.homesentry.co"),
    Tienda("haceb", "Haceb", "https://www.haceb.com"),
    Tienda("spring", "Spring", "https://www.colchonesspring.com.co"),
    Tienda("tigo", "Tigo", "https://compras.tigo.com.co"),
    Tienda("levis", "Levi's", "https://www.levi.com.co"),
    Tienda("americanino", "Americanino", "https://www.americanino.com"),
    Tienda("chevignon", "Chevignon", "https://www.chevignon.com.co"),
    Tienda("mattelsa", "Mattelsa", "https://www.mattelsa.net"),
    Tienda("offcorss", "Offcorss", "https://www.offcorss.com"),
    Tienda("pilatos", "Pilatos", "https://www.pilatos.com"),
    Tienda("studiof", "Studio F", "https://www.studiof.com.co"),
    Tienda("tennis", "Tennis", "https://www.tennis.com.co"),
    Tienda("larebaja", "La Rebaja", "https://www.larebajavirtual.com"),
    Tienda("agaval", "Agaval", "https://www.agaval.com"),
    Tienda("electrojaponesa", "Electrojaponesa", "https://www.electrojaponesa.com"),
    Tienda("electrobello", "Electrobello", "https://www.electrobello.com"),
    Tienda("oportunidades", "Oportunidades", "https://www.oportunidades.com.co"),
    Tienda("reebok", "Reebok", "https://www.reebok.co"),
    Tienda("calzatodo", "Calzatodo", "https://www.calzatodo.com.co"),
    Tienda("bosi", "Bosi", "https://www.bosi.com.co"),
    Tienda("cromantic", "Cromantic", "https://www.cromantic.com"),
    # Datos incrustados en la página de búsqueda.
    Tienda(
        "falabella", "Falabella", "https://www.falabella.com.co", "falabella",
        busqueda="https://www.falabella.com.co/falabella-co/search?Ntt={q}",
    ),
    Tienda(
        "homecenter", "Homecenter", "https://www.homecenter.com.co", "falabella",
        busqueda="https://www.homecenter.com.co/homecenter-co/search?Ntt={q}",
    ),
    # Índice de búsqueda propio de la tienda.
    Tienda("alkosto", "Alkosto", "https://www.alkosto.com", "alkosto"),
    Tienda("ktronix", "Ktronix", "https://www.ktronix.com", "alkosto"),
    Tienda("alkomprar", "Alkomprar", "https://www.alkomprar.com", "alkosto"),
    # Tiendas de marca.
    Tienda(
        "lenovo", "Lenovo", "https://www.lenovo.com/co/es", "lenovo",
        busqueda=(
            "https://openapi.lenovo.com/co/es/ofp/search/global/cache/products/get/_tsc"
            "?fq=&text={q}&rows={n}&sort=relevance&display_tab=Products"
        ),
    ),
    Tienda(
        "hp", "HP", "https://www.hp.com/co-es/shop", "hp",
        busqueda="https://www.hp.com/co-es/shop/catalogsearch/result/?q={q}",
    ),
    Tienda(
        "samsung", "Samsung", "https://www.samsung.com/co", "samsung",
        busqueda=(
            "https://api.shop.samsung.com/tokocommercewebservices/v2/co/products/search"
            "?query={q}&pageSize={n}&currentPage={p}"
        ),
    ),
    # API de tienda de WooCommerce.
    Tienda("pcware", "PC Ware", "https://www.pcware.com.co", "woocommerce"),
    Tienda("tauro", "Tauro", "https://tauro.com.co", "woocommerce"),
    Tienda(
        "ikea", "IKEA", "https://www.ikea.com/co/es", "ikea",
        busqueda=(
            "https://sik.search.blue.cdtapps.com/co/es/search-result-page"
            "?q={q}&size={n}&types=PRODUCT"
        ),
    ),
    # Solo responden a un navegador de verdad (ver conectores/navegador.py).
    Tienda(
        "amazon", "Amazon", "https://www.amazon.com", "navegador",
        busqueda="https://www.amazon.com/s?k={q}", por_defecto=False,
    ),
    Tienda(
        "dafiti", "Dafiti", "https://www.dafiti.com.co", "navegador",
        busqueda="https://www.dafiti.com.co/catalog/?q={q}", por_defecto=False,
    ),
    Tienda(
        "decathlon", "Decathlon", "https://www.decathlon.com.co", "navegador",
        busqueda="https://www.decathlon.com.co/search?Ntt={q}", por_defecto=False,
    ),
    # Tiendas oficiales de marca en MercadoLibre: la consulta debe nombrar la marca.
    Tienda(
        "meli_oficial", "ML oficial", "https://www.mercadolibre.com.co", "navegador",
        busqueda="https://www.mercadolibre.com.co/tienda/{q}", por_defecto=False,
    ),
    # Con el extractor genérico del navegador.
    Tienda(
        "farmatodo", "Farmatodo", "https://www.farmatodo.com.co", "navegador",
        busqueda="https://www.farmatodo.com.co/buscar?product={q}", por_defecto=False,
    ),
    Tienda(
        "makro", "Makro", "https://tienda.makro.com.co", "navegador",
        busqueda="https://tienda.makro.com.co/search?name={q}", por_defecto=False,
    ),
    Tienda(
        "lg", "LG", "https://www.lg.com/co", "navegador",
        busqueda="https://www.lg.com/co/search/?search={q}", por_defecto=False,
    ),
    Tienda(
        "pricesmart", "PriceSmart", "https://www.pricesmart.com/es-co", "navegador",
        busqueda="https://www.pricesmart.com/es-co/busqueda?q={q}", por_defecto=False,
    ),
    # Claro no tiene buscador utilizable: se lee su catálogo de celulares completo.
    Tienda(
        "claro", "Claro", "https://tienda.claro.com.co", "navegador",
        busqueda="https://tienda.claro.com.co/claro/celulares", por_defecto=False,
    ),
    # API oficial; solo funciona con credenciales (ver conectores/mercadolibre.py).
    # Fuera de las búsquedas normales: crear la aplicación exige validar identidad en
    # MercadoLibre y no se pudo completar (2026-11-18). Queda por si se consigue después.
    Tienda(
        "mercadolibre", "MercadoLibre", "https://www.mercadolibre.com.co", "mercadolibre",
        por_defecto=False,
    ),
    # Domicilios: los precios son por comercio y no incluyen el envío.
    Tienda(
        "rappi", "Rappi", "https://www.rappi.com.co", "rappi",
        busqueda="https://www.rappi.com.co/search?query={q}",
    ),
)

# Tiendas que el motor todavía no consulta, con el motivo comprobado el 2026-11-18.
PENDIENTES: tuple[tuple[str, str], ...] = (
    ("adidas.co", "responde HTTP 403 incluso en navegador; adidas se cubre con otras tiendas"),
    ("Acer", "su tienda en línea no opera en Colombia (no aparece entre sus países)"),
    ("Polo R. Lauren", "no tiene tienda en línea propia en Colombia; se vende en Falabella"),
    ("MercadoLibre", "su buscador pide verificación de cuenta; solo se leen tiendas oficiales"),
    ("Xiaomi", "su buscador no mostró productos ni en el navegador"),
    ("Ara", "tiene deshabilitada la API de su tienda (HTTP 403)"),
    ("Puma y otras", "no conectaron en los dominios probados; falta confirmar la dirección"),
    ("Asus", "el sitio de Colombia no publica precios"),
    ("Dell", "no tiene tienda en línea para Colombia"),
)

_POR_ID = {t.id: t for t in TIENDAS}


def seleccionar(ids: list[str] | None, con_navegador: bool = False) -> list[Tienda]:
    """Devuelve las tiendas pedidas; sin pedido, las que se consultan por defecto.

    Las tiendas de navegador solo entran si se nombran o con `con_navegador`.
    """
    if not ids:
        return [t for t in TIENDAS if t.por_defecto or con_navegador]
    desconocidas = [i for i in ids if i not in _POR_ID]
    if desconocidas:
        disponibles = ", ".join(_POR_ID)
        raise ValueError(
            f"Tienda desconocida: {', '.join(desconocidas)}. Disponibles: {disponibles}"
        )
    return [_POR_ID[i] for i in ids]
