"""Veredicto sobre cada oferta: ¿el descuento es real o es un precio normal disfrazado?

El problema que resuelve: una tienda infla el precio de lista ("antes $4.600.000") para
anunciar un descuento grande sobre lo que en realidad es el precio de siempre. Aquí el
precio de lista de la tienda NO se usa como referencia. La referencia es el precio real,
que se estima con evidencia independiente, en este orden de confianza:

1. Mercado local: a cuánto venden hoy el mismo producto las demás tiendas.
2. Historial propio: a cuánto se ha visto este producto en esta tienda.
3. Precio internacional: lo que cuesta afuera, convertido a pesos y con IVA.

El módulo es lógica pura: no consulta nada. Recibe la evidencia ya reunida.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from statistics import median

from ofertas.modelos import Oferta

# Un ahorro menor que esto frente al precio real no cuenta como descuento: es ruido
# normal entre tiendas.
AHORRO_MINIMO = 0.08
# Hasta cuánto por encima del precio real sigue siendo "precio normal".
TOLERANCIA_SOBREPRECIO = 0.05
# Desde qué descuento anunciado se examina si la oferta es engañosa.
DESCUENTO_ANUNCIADO_MINIMO = 5.0
# Cuánto por encima del precio real debe estar el precio de lista para llamarlo inflado.
INFLADO_MINIMO = 0.10
# Voces independientes necesarias para orientarse por equipos de igual ficha técnica.
# Con dos ya hay una idea del precio; el veredicto sale marcado como aproximado.
MIN_COMPARABLES = 2
# Para confiar en el historial: observaciones y días mínimos.
MIN_OBSERVACIONES = 3
MIN_DIAS = 7
# Colombia cobra IVA y los precios publicados afuera no lo incluyen.
IVA = 0.19
# Sobrecosto razonable de traer y vender un producto en Colombia cuando no se reconoce
# su categoría (flete, arancel y margen del importador juntos). Es una estimación.
MARGEN_IMPORTACION = 0.30
# Cuando sí se conoce el arancel de la categoría (ver aranceles.py), encima de él se
# acepta este sobrecosto por flete, seguro y margen comercial. También es una estimación.
LOGISTICA_Y_MARGEN = 0.20


def margen_con_arancel(arancel: float | None) -> float:
    """Sobrecosto de importación que se considera normal, dado el arancel del producto.

    Se puede fijar a mano con la variable de entorno OFERTAS_MARGEN_IMPORTACION (0.2).
    """
    configurado = os.environ.get("OFERTAS_MARGEN_IMPORTACION", "").strip()
    try:
        if configurado and 0 <= float(configurado) <= 2:
            return float(configurado)
    except ValueError:
        pass
    if arancel is None:
        return MARGEN_IMPORTACION
    return round((1 + arancel) * (1 + LOGISTICA_Y_MARGEN) - 1, 4)


# Si todo el mercado local supera el tope internacional por más de esto, se advierte.
ALERTA_SOBRE_INTERNACIONAL = 0.15

# Qué tanto pesa el precio de afuera según qué tan seguro es que sea el mismo producto.
# Con el mismo modelo todavía puede cambiar la presentación (una herramienta sola y su
# kit con baterías comparten modelo), así que por sí solo no pasa de evidencia media.
_FUERZA_INTERNACIONAL = {"exacto": "fuerte", "modelo": "media", "equivalente": "aproximada"}

CLASES = {
    "descuento_real": "Descuento real",
    "oferta_falsa": "Oferta engañosa",
    "sobreprecio": "Más caro que lo normal",
    "buen_precio": "Buen precio",
    "precio_normal": "Precio normal",
    "caro": "Caro",
    "sin_referencia": "Sin verificar",
}
PLURALES = {
    "descuento_real": "descuentos reales",
    "oferta_falsa": "ofertas engañosas",
    "sobreprecio": "más caras que lo normal",
    "sin_referencia": "sin verificar",
}


def nombre_de(clase: str, cantidad: int) -> str:
    """Nombre de la clase en minúsculas, en singular o plural según la cantidad."""
    if cantidad == 1 or clase not in PLURALES:
        return "sin verificar" if clase == "sin_referencia" else CLASES[clase].lower()
    return PLURALES[clase]


# De mejor a peor, para ordenar y filtrar.
FAVORABLES = ("descuento_real", "buen_precio")


@dataclass
class Internacional:
    """Precio de referencia en el exterior para un producto."""

    precio_usd: float
    trm: float
    coincidencia: str  # "exacto", "modelo" o "equivalente"
    fuentes: list[str] = field(default_factory=list)
    ejemplo: str = ""
    url: str = ""
    candidatos: int = 1
    # Sobrecosto de importación que se acepta como normal para este producto.
    margen: float = MARGEN_IMPORTACION
    # De dónde sale el arancel usado ("" si no se reconoció la categoría).
    fuente_arancel: str = ""

    @property
    def en_pesos(self) -> float:
        """Precio de afuera convertido, sin impuestos."""
        return self.precio_usd * self.trm

    @property
    def con_iva(self) -> float:
        """Lo que costaría en Colombia sumando solo el IVA."""
        return self.en_pesos * (1 + IVA)

    @property
    def tope_normal(self) -> float:
        """Precio local máximo que todavía se explica por los costos de importar."""
        return self.con_iva * (1 + self.margen)

    @property
    def normal_esperado(self) -> float:
        """Precio local que cabría esperar: IVA más la mitad del margen de importación."""
        return self.con_iva * (1 + self.margen / 2)

    @property
    def confiable(self) -> bool:
        return self.coincidencia in ("exacto", "modelo")


@dataclass
class Mercado:
    """Cómo se reparten los precios de venta de lo que otras tiendas ofrecen en la búsqueda.

    Sirve para productos genéricos o de marca local (colchones, sillas, bicicletas), que
    no tienen "el mismo producto" en otra tienda. No dice cuánto vale este artículo, pero
    sí permite ver si su precio de lista está fuera de lo que cobra el mercado.
    """

    productos: int
    tiendas: int
    p25: float
    mediana: float
    p75: float
    p90: float


@dataclass
class Evidencia:
    tipo: str  # "mercado", "archivo", "historial", "internacional", "ficha" o "categoria"
    precio: float
    detalle: str
    fuerza: str  # "fuerte", "media" o "aproximada"
    resumen: str = ""  # versión corta del detalle, para la línea del veredicto


@dataclass
class Veredicto:
    clase: str
    titulo: str
    texto: str
    precio_real: float | None = None
    ahorro_real_pct: float | None = None
    descuento_anunciado_pct: float = 0.0
    lista_inflada_pct: float | None = None
    # Qué tan firme es la evidencia principal: "fuerte", "media" o "aproximada".
    confianza: str = ""
    evidencias: list[Evidencia] = field(default_factory=list)

    @property
    def favorable(self) -> bool:
        """Buen precio comprobado: no cuenta si la evidencia es solo aproximada."""
        return self.clase in FAVORABLES and self.confianza != "aproximada"

    def a_dict(self) -> dict:
        return asdict(self)


def _pesos(valor: float) -> str:
    return "$" + f"{round(valor):,}".replace(",", ".")


def _pct(fraccion: float) -> str:
    return f"{abs(fraccion) * 100:.0f}%"


def reunir_evidencias(
    oferta: Oferta,
    otras_tiendas: list[Oferta],
    historial: dict | None = None,
    internacional: Internacional | None = None,
    variantes: list[Oferta] | None = None,
    comparables: list[Oferta] | None = None,
    archivo: list[dict] | None = None,
) -> list[Evidencia]:
    """Arma la lista de evidencias disponibles, de la más confiable a la menos."""
    evidencias: list[Evidencia] = []
    if len(otras_tiendas) >= 2:
        precios = sorted(o.precio for o in otras_tiendas)
        nombres = ", ".join(sorted({o.tienda for o in otras_tiendas}))
        evidencias.append(Evidencia(
            "mercado", median(precios),
            f"mediana de {len(precios)} tiendas más ({nombres});"
            f" la más barata, {_pesos(precios[0])}",
            "fuerte", f"mediana de {len(precios)} tiendas más",
        ))
    elif len(otras_tiendas) == 1:
        otra = otras_tiendas[0]
        evidencias.append(Evidencia(
            "mercado", otra.precio, f"precio en {otra.tienda}, la única otra tienda que lo tiene",
            "media", f"precio en {otra.tienda}",
        ))
    if len(otras_tiendas) < 2 and variantes and len(variantes) >= 2:
        # Sin suficientes tiendas con el producto idéntico, sirve la misma referencia en
        # otra presentación (otro color), que suele costar lo mismo.
        precios = sorted(o.precio for o in variantes)
        nombres = ", ".join(sorted({o.tienda for o in variantes}))
        evidencias.append(Evidencia(
            "mercado", median(precios),
            f"mediana de {len(precios)} tiendas que venden la misma referencia en otra"
            f" presentación ({nombres}); la más barata, {_pesos(precios[0])}",
            "media", f"mediana de {len(precios)} tiendas con la misma referencia en otro color",
        ))
    elif not otras_tiendas and variantes:
        # Una sola tienda más con la misma referencia, reconocida por el nombre.
        otra = variantes[0]
        evidencias.append(Evidencia(
            "mercado", otra.precio,
            f"precio en {otra.tienda}, que vende la misma referencia (reconocida por el nombre)",
            "media", f"precio en {otra.tienda} de la misma referencia",
        ))
    if archivo:
        # Copias antiguas de esta misma página en el archivo de Internet.
        precios = [a["precio"] for a in archivo]
        fechas = ", ".join(f"{_pesos(a['precio'])} el {a['fecha']}" for a in archivo)
        evidencias.append(Evidencia(
            "archivo", median(precios),
            f"esta misma página mostraba {fechas}, según el archivo de Internet",
            "media", f"lo que esta misma página mostraba el {archivo[-1]['fecha']}",
        ))
    if (
        historial
        and historial.get("veces_visto", 0) >= MIN_OBSERVACIONES
        and historial.get("dias_observado", 0) >= MIN_DIAS
        and historial.get("mediana_vista")
    ):
        evidencias.append(Evidencia(
            "historial", historial["mediana_vista"],
            f"precio habitual en esta tienda: {historial['veces_visto']} observaciones en"
            f" {historial['dias_observado']} días",
            "media", "su precio habitual en esta tienda",
        ))
    if internacional:
        aproximado = "" if internacional.confiable else " (producto equivalente, no idéntico)"
        evidencias.append(Evidencia(
            "internacional", internacional.normal_esperado,
            f"afuera cuesta US$ {internacional.precio_usd:,.2f}{aproximado}:"
            f" {_pesos(internacional.en_pesos)} a la TRM de {_pesos(internacional.trm)},"
            f" {_pesos(internacional.con_iva)} con IVA, y hasta"
            f" {_pesos(internacional.tope_normal)} con costos de importación"
            f"{'; ' + internacional.fuente_arancel if internacional.fuente_arancel else ''}"
            f" ({', '.join(internacional.fuentes)})",
            _FUERZA_INTERNACIONAL[internacional.coincidencia],
            f"afuera vale US$ {internacional.precio_usd:,.2f}, que con IVA e importación"
            f" son unos {_pesos(internacional.normal_esperado)}",
        ))
    if comparables and len(comparables) >= MIN_COMPARABLES:
        # Último recurso: equipos de otras marcas o modelos con la misma ficha técnica.
        precios = sorted(o.precio for o in comparables)
        evidencias.append(Evidencia(
            "ficha", median(precios),
            f"mediana de {len(precios)} equipos con el mismo procesador, memoria y"
            f" almacenamiento en otras tiendas; el más barato, {_pesos(precios[0])}",
            "aproximada",
            f"mediana de {len(precios)} equipos con la misma ficha técnica",
        ))
    orden = {"fuerte": 0, "media": 1, "aproximada": 2}
    tipo = {"mercado": 0, "archivo": 1, "historial": 2, "internacional": 3, "ficha": 4}
    # sorted es estable: entre dos evidencias de mercado de igual fuerza gana la primera.
    return sorted(evidencias, key=lambda e: (orden[e.fuerza], tipo[e.tipo]))


def _segun_el_mercado(oferta: Oferta, mercado: Mercado) -> Veredicto:
    """Juicio aproximado para un producto que nadie más vende, mirando su categoría.

    Solo se pronuncia en el caso claro: el precio de lista está por encima de lo que
    cobra casi todo el mercado y el precio con descuento es el corriente. En lo demás
    no hay cómo saber si el producto es mejor o peor que los otros, y se dice así.
    """
    anunciado = oferta.descuento_pct
    rango = (
        f"En esta búsqueda, {mercado.productos} productos de {mercado.tiendas} tiendas más se"
        f" venden entre {_pesos(mercado.p25)} y {_pesos(mercado.p75)} (la mitad central),"
        f" y 9 de cada 10 por menos de {_pesos(mercado.p90)}."
    )
    if oferta.precio_lista > mercado.p90 and oferta.precio <= mercado.p75:
        return Veredicto(
            clase="oferta_falsa",
            titulo=CLASES["oferta_falsa"] + " (aproximado)",
            texto=(
                f"Ninguna otra tienda vende este mismo producto. {rango} El precio de lista"
                f" de {_pesos(oferta.precio_lista)} está por encima de casi todo el mercado,"
                f" y {_pesos(oferta.precio)} es un precio corriente: el {anunciado:.0f}%"
                " anunciado se calcula sobre una lista fuera de rango. Sin confirmar: se"
                " compara con productos parecidos, no con el mismo."
            ),
            precio_real=None,
            descuento_anunciado_pct=anunciado,
            lista_inflada_pct=round((oferta.precio_lista - mercado.p90) / mercado.p90 * 100, 1),
            confianza="aproximada",
            evidencias=[Evidencia(
                "categoria", mercado.mediana,
                f"{mercado.productos} productos de {mercado.tiendas} tiendas en la misma búsqueda",
                "aproximada", "precios de productos parecidos en la búsqueda",
            )],
        )
    if oferta.precio < mercado.p25:
        posicion = "está por debajo de ese rango; puede ser una oferta o un producto más sencillo"
    elif oferta.precio <= mercado.p75:
        posicion = "está dentro de ese rango"
    else:
        posicion = "está por encima de ese rango"
    return Veredicto(
        "sin_referencia", CLASES["sin_referencia"],
        f"La tienda anuncia {anunciado:.0f}% de descuento, pero ninguna otra tienda vende este"
        f" mismo producto y no hay historial para comprobarlo. {rango} Este precio {posicion}.",
        descuento_anunciado_pct=anunciado,
    )


def evaluar(
    oferta: Oferta,
    otras_tiendas: list[Oferta],
    historial: dict | None = None,
    internacional: Internacional | None = None,
    variantes: list[Oferta] | None = None,
    comparables: list[Oferta] | None = None,
    mercado: Mercado | None = None,
    archivo: list[dict] | None = None,
) -> Veredicto:
    """Decide qué tan real es la oferta comparándola con el precio real estimado."""
    anunciado = oferta.descuento_pct
    evidencias = reunir_evidencias(
        oferta, otras_tiendas, historial, internacional, variantes, comparables, archivo
    )
    if not evidencias and mercado and anunciado >= DESCUENTO_ANUNCIADO_MINIMO:
        return _segun_el_mercado(oferta, mercado)
    if not evidencias:
        aviso = (
            f"La tienda anuncia {anunciado:.0f}% de descuento, pero no hay con qué comprobarlo:"
            " ninguna otra tienda tiene el mismo producto, no hay historial suficiente y"
            " no se halló precio internacional."
            if anunciado >= DESCUENTO_ANUNCIADO_MINIMO
            else "No hay evidencia independiente para juzgar este precio."
        )
        return Veredicto("sin_referencia", CLASES["sin_referencia"], aviso,
                         descuento_anunciado_pct=anunciado)

    principal = evidencias[0]
    real = principal.precio
    ahorro = (real - oferta.precio) / real
    inflado = (oferta.precio_lista - real) / real if oferta.precio_lista > oferta.precio else None
    base = f"Precio real: cerca de {_pesos(real)} ({principal.resumen})."

    if anunciado >= DESCUENTO_ANUNCIADO_MINIMO:
        if ahorro >= AHORRO_MINIMO:
            clase = "descuento_real"
            texto = f"{base} Ahorras {_pct(ahorro)} de verdad"
            texto += (
                f", no el {anunciado:.0f}% que anuncia la tienda."
                if inflado is not None and inflado >= INFLADO_MINIMO
                else "."
            )
        elif ahorro > -TOLERANCIA_SOBREPRECIO:
            clase = "oferta_falsa"
            texto = (
                f"{base} La tienda anuncia {anunciado:.0f}% de descuento sobre un precio de"
                f" lista de {_pesos(oferta.precio_lista)}, pero {_pesos(oferta.precio)} es"
                " el precio normal del producto: no hay ahorro real."
            )
        else:
            clase = "sobreprecio"
            texto = (
                f"{base} Aun con el {anunciado:.0f}% de descuento anunciado, está"
                f" {_pct(ahorro)} por encima del precio real."
            )
        if inflado is not None and inflado >= INFLADO_MINIMO:
            texto += f" El precio de lista está inflado {_pct(inflado)} sobre el real."
    else:
        if ahorro >= AHORRO_MINIMO:
            clase, texto = "buen_precio", f"{base} Está {_pct(ahorro)} por debajo."
        elif ahorro > -AHORRO_MINIMO:
            clase, texto = "precio_normal", f"{base} Este precio está dentro de lo normal."
        else:
            clase, texto = "caro", f"{base} Está {_pct(ahorro)} por encima."

    # El mercado local entero puede estar inflado frente al exterior: se dice aparte.
    if internacional and principal.tipo != "internacional":
        exceso = (real - internacional.tope_normal) / internacional.tope_normal
        salvedad = "" if internacional.confiable else " (comparando con un producto equivalente)"
        if exceso >= ALERTA_SOBRE_INTERNACIONAL:
            texto += (
                f" Ojo: en Colombia este producto cuesta {_pct(exceso)} más de lo que se"
                f" explica por importarlo{salvedad}; afuera vale US$"
                f" {internacional.precio_usd:,.2f}, unos {_pesos(internacional.con_iva)} con IVA."
            )
        elif oferta.precio <= internacional.con_iva:
            texto += (
                f" Además está por debajo del precio internacional con IVA"
                f" ({_pesos(internacional.con_iva)}){salvedad}."
            )
    # Una segunda evidencia de otro tipo refuerza (o matiza) la principal: se menciona.
    segunda = next(
        (e for e in evidencias[1:] if e.tipo != principal.tipo and e.tipo != "internacional"),
        None,
    )
    if segunda:
        texto += f" Otra referencia: {_pesos(segunda.precio)} ({segunda.resumen})."

    titulo = CLASES[clase]
    if principal.fuerza == "aproximada":
        titulo += " (aproximado)"
        texto += (
            " Sin confirmar: son otros equipos de igual ficha, y la marca también pesa."
            if principal.tipo == "ficha"
            else " Sin confirmar: la referencia es un producto equivalente, no el idéntico."
        )
    elif principal.fuerza == "media" and len(evidencias) == 1:
        if principal.tipo == "internacional":
            texto += " La evidencia es limitada: confirma que sea la misma presentación."
        elif principal.tipo == "archivo":
            texto += " La evidencia es limitada: es una copia antigua de la página."
        else:
            texto += " La evidencia es limitada."

    return Veredicto(
        clase=clase,
        titulo=titulo,
        confianza=principal.fuerza,
        texto=texto,
        precio_real=round(real),
        ahorro_real_pct=round(ahorro * 100, 1),
        descuento_anunciado_pct=anunciado,
        lista_inflada_pct=round(inflado * 100, 1) if inflado is not None else None,
        evidencias=evidencias,
    )
