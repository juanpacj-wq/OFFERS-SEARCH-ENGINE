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
# Para confiar en el historial: observaciones y días mínimos.
MIN_OBSERVACIONES = 3
MIN_DIAS = 7
# Colombia cobra IVA y los precios publicados afuera no lo incluyen.
IVA = 0.19
# Sobrecosto razonable de traer y vender un producto en Colombia (flete, arancel,
# margen del importador). El precio local se considera normal hasta este tope.
MARGEN_IMPORTACION = 0.30
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
        return self.con_iva * (1 + MARGEN_IMPORTACION)

    @property
    def normal_esperado(self) -> float:
        """Precio local que cabría esperar: IVA más la mitad del margen de importación."""
        return self.con_iva * (1 + MARGEN_IMPORTACION / 2)

    @property
    def confiable(self) -> bool:
        return self.coincidencia in ("exacto", "modelo")


@dataclass
class Evidencia:
    tipo: str  # "mercado", "historial" o "internacional"
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
            f" ({', '.join(internacional.fuentes)})",
            _FUERZA_INTERNACIONAL[internacional.coincidencia],
            f"afuera vale US$ {internacional.precio_usd:,.2f}, que con IVA e importación"
            f" son unos {_pesos(internacional.normal_esperado)}",
        ))
    orden = {"fuerte": 0, "media": 1, "aproximada": 2}
    tipo = {"mercado": 0, "historial": 1, "internacional": 2}
    # sorted es estable: entre dos evidencias de mercado de igual fuerza gana la primera.
    return sorted(evidencias, key=lambda e: (orden[e.fuerza], tipo[e.tipo]))


def evaluar(
    oferta: Oferta,
    otras_tiendas: list[Oferta],
    historial: dict | None = None,
    internacional: Internacional | None = None,
    variantes: list[Oferta] | None = None,
) -> Veredicto:
    """Decide qué tan real es la oferta comparándola con el precio real estimado."""
    anunciado = oferta.descuento_pct
    evidencias = reunir_evidencias(oferta, otras_tiendas, historial, internacional, variantes)
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
        texto += " Sin confirmar: la referencia es un producto equivalente, no el idéntico."
    elif principal.fuerza == "media" and len(evidencias) == 1:
        texto += (
            " La evidencia es limitada: confirma que sea la misma presentación."
            if principal.tipo == "internacional"
            else " La evidencia es limitada."
        )

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
