"""Identidad de producto: saber cuándo dos ofertas son el mismo artículo.

Dos ofertas se consideran el mismo producto si comparten código de barras o, en su
defecto, código de modelo del fabricante (con la misma marca y precios comparables).
Sobre esos grupos se calcula el precio real de mercado.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from statistics import median

from ofertas.modelos import Oferta

# Tiendas del mismo dueño: suelen publicar el mismo precio, así que para medir el
# consenso del mercado cuentan como una sola voz.
FAMILIAS = {
    "ktronix": "alkosto", "alkomprar": "alkosto",
    "carulla": "exito",
    "jumbo": "cencosud", "easy": "cencosud",
    "homecenter": "falabella",
}
# Diferencia máxima de precio para aceptar una coincidencia por modelo. Más que eso
# suele ser un accesorio o un paquete distinto que menciona el mismo modelo (una
# herramienta sola y su kit con baterías, por ejemplo).
RAZON_MAXIMA = 1.8

_UNIDADES = {
    "gb": "gb", "tb": "tb", "mb": "mb", "ml": "ml", "l": "l", "lt": "l", "litros": "l",
    "kg": "kg", "g": "g", "gr": "g", "w": "w", "hz": "hz", "mah": "mah",
    "pulgadas": "in", "pulgada": "in", "pulg": "in", "in": "in", "inch": "in", "inches": "in",
    '"': "in", "''": "in", "”": "in", "″": "in", "¨": "in",
}
# El número no puede venir pegado a una "x": en "2x3 pulgadas" el 3 es parte de una
# dimensión, no una medida suelta.
_RE_MEDIDA = re.compile(
    r"(?<![\dx.,])(\d+(?:[.,]\d+)?)\s*"
    r"(gb|tb|mb|ml|litros|lt|kg|gr|mah|hz|pulgadas|pulgada|pulg|inches|inch"
    r"|in\b|l\b|g\b|w\b|\"|''|”|″|¨)",
    re.I,
)
_RE_PALABRA = re.compile(r"[a-z0-9]+(?:[-/.][a-z0-9]+)*")
_RE_CODIGO = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9][A-Z0-9\-/.]{4,}$")
# Cosas que parecen código de modelo y no lo son: procesadores, memorias, resoluciones.
_RE_NO_CODIGO = re.compile(
    r"^(?:I[3579]-?\d.*|R[3579]-?\d.*|RYZEN.*|CORE.*|U?HD-?\d.*|[FQ]HD.*|\d+K.*|\d{4,5}[A-Z]{1,2}|N\d{4}"
    r"|RTX?-?\d.*|GTX-?\d.*|DDR\d.*|LPDDR.*|\d+X\d+.*|\d+P|WIFI-?\d.*|WI-FI.*|USB.*|HDMI.*"
    r"|BT-?\d.*|IP\d{2}.*|\d+(?:K|G|MP|MM|CM|V|HZ|W|MAH|GB|TB|MB|ML|KG|L|IN|BTU|RPM|PCS|UND?S?)"
    r"|\d+(?:ST|ND|RD|TH)|\d+[.,]\d+.*|WINDOWS.*|WIN\d+|OFFICE.*|ANDROID.*)$"
)
# Palabras que describen el tipo de producto o son relleno: no distinguen un artículo.
GENERICAS = frozenset(
    """
    de del la el los las un una y o con sin para por en a al x mas
    computador computadora portatil portatiles laptop notebook celular celulares telefono
    smartphone televisor televisores tv pantalla monitor tablet audifonos audifono parlante
    nevera lavadora secadora estufa horno microondas aire acondicionado tenis zapatos zapato
    zapatillas camiseta camisa pantalon jean chaqueta morral maleta bolso reloj consola
    videojuego juego impresora teclado mouse camara cargador cable funda estuche
    pulgadas pulgada pulg ram disco ssd hdd memoria almacenamiento procesador intel amd
    core ryzen smart uhd fhd hd full led oled qled 4k 8k 5g 4g lte wifi bluetooth
    negro negra blanco blanca gris azul rojo roja verde amarillo rosa rosado morado violeta
    plata plateado dorado beige cafe naranja titanio titanium grafito lavanda menta
    crema marfil celeste fucsia lila vino oscuro claro turquesa coral
    hombre mujer nino nina unisex adulto original nuevo nueva oferta promocion combo kit
    incluye und unidad unidades ref referencia modelo color talla tamano version edicion
    new the and for with inch black white gray grey blue red green silver gold
    """.split()
)
# Palabras que cambian de producto dentro de una misma familia (S25 y S25 Ultra).
VARIANTES = frozenset(
    ["pro", "ultra", "plus", "max", "mini", "lite", "fe", "air", "neo", "se", "edge", "fold",
     "flip", "chromebook", "gaming", "kids", "junior", "xl", "xs", "5a", "3i", "5i", "3x"]
)
# Detalles de ficha técnica que unas tiendas ponen en el nombre y otras no.
_RE_DETALLE = re.compile(r"^(?:\d+(?:ram|mp|gbram|nucleos|cores)|gbram|\d{1,2}gen)$")
ACCESORIOS = frozenset(
    """
    funda estuche forro carcasa protector vidrio mica cargador cable adaptador soporte base
    repuesto control correa pulso case cover charger adapter stand mount strap protector
    replacement sleeve skin screen film holder dock compatible bundle remote backlight
    board legs wire strip part parts repair
    """.split()
)


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def medidas(texto: str) -> set[str]:
    """Especificaciones con unidad, en forma comparable: "512 GB" pasa a "512gb"."""
    salida = set()
    for numero, unidad in _RE_MEDIDA.findall(normalizar(texto)):
        valor = numero.replace(",", ".")
        if unidad.lower() == "g" and float(valor) < 10:
            continue  # "5G" es la red celular, no cinco gramos
        if "." in valor:
            valor = valor.rstrip("0").rstrip(".")
        salida.add(f"{valor}{_UNIDADES[unidad.lower()]}")
    return salida


def palabras(texto: str) -> list[str]:
    """Palabras del texto, sin las medidas (que se comparan aparte)."""
    return _RE_PALABRA.findall(_RE_MEDIDA.sub(" ", normalizar(texto)))


_RE_CPU = re.compile(
    r"\b(?:core\s*)?(i[3579])\b|\bci\s*([3579])\b|\bcore\s*(?:ultra\s*)?([3579])\b"
    r"|\bryzen\s*([3579])\b|\br([3579])\b|\b(celeron|pentium|athlon|snapdragon|n\d{3,4})\b"
    r"|\b(m[1-5])\b"
)


def procesador(texto: str) -> str:
    """Gama del procesador en forma comparable: "Core i5", "Ci 5" y "Core 5" dan "intel5"."""
    hallado = _RE_CPU.search(normalizar(texto))
    if not hallado:
        return ""
    i, ci, core, ryzen, r, otro, apple = hallado.groups()
    if i:
        return f"intel{i[1]}"
    if ci or core:
        return f"intel{ci or core}"
    if ryzen or r:
        return f"ryzen{ryzen or r}"
    return otro or apple or ""


def codigos_de_modelo(texto: str) -> set[str]:
    """Códigos de modelo del fabricante que aparecen en un texto (83RQ003ELM, UN55U8500HK)."""
    salida = set()
    for trozo in re.split(r"[\s,;()\[\]|]+", unicodedata.normalize("NFKD", texto or "").upper()):
        trozo = trozo.strip("-/.:+*'\"")
        if _RE_CODIGO.match(trozo) and not _RE_NO_CODIGO.match(trozo):
            salida.add(trozo)
    return salida


def mismo_modelo(a: str, b: str) -> bool:
    """Iguales, o uno es el otro con un sufijo regional (QN55Q7F y QN55Q7FAAKXZL)."""
    a, b = a.upper(), b.upper()
    if a == b:
        return True
    corto, largo = sorted((a, b), key=len)
    return len(corto) >= 7 and largo.startswith(corto)


def modelo_contenido(a: str, b: str) -> bool:
    """Uno es el código de familia del otro: "CU7000" dentro de "UN55CU7000KXZL"."""
    corto, largo = sorted((a.upper(), b.upper()), key=len)
    digitos = sum(c.isdigit() for c in corto)
    return len(corto) >= 5 and digitos >= 3 and corto != largo and corto in largo


def variante_regional(a: str, b: str) -> bool:
    """Mismo modelo con distinto sufijo de país: UN55CU7000KXZL y UN55CU7000FXZA."""
    a, b = a.upper(), b.upper()
    comun = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        comun += 1
    return comun >= 7 and comun >= 0.6 * min(len(a), len(b))


def sin_procesador(texto: str) -> str:
    """Quita la mención del procesador, para que su número no pase por nombre de familia."""
    return _RE_CPU.sub(" ", normalizar(texto))


def distintivos(nombre: str, marca: str = "") -> list[str]:
    """Palabras que identifican el producto: marca, familia y variante, en orden."""
    vistas, salida = set(), []
    for palabra in palabras(f"{marca} {nombre}"):
        muy_corta = len(palabra) < 2 and not palabra.isdigit()
        if palabra in GENERICAS or palabra in vistas or muy_corta:
            continue
        vistas.add(palabra)
        salida.append(palabra)
    return salida


def es_accesorio(texto: str) -> bool:
    return bool(ACCESORIOS.intersection(palabras(texto)))


USADOS = frozenset(
    ["reacondicionado", "reacondicionada", "refurbished", "renewed", "usado", "usada",
     "seminuevo", "seminueva", "exhibicion", "openbox", "remanufacturado", "outlet", "demo",
     "used", "preowned", "pre-owned", "restored", "certified"]
)


# Palabras con las que un anuncio menciona un modelo sin ser ese producto.
_RE_PARA_OTRO = re.compile(r"\b(?:compatible|replacement|bundle|fits?|for|para|repuesto)\b")


def menciona_sin_ser(titulo: str) -> bool:
    """El título habla de un producto ajeno: "Remote for UN55CU7000", "TV Bundle with..."."""
    return bool(_RE_PARA_OTRO.search(normalizar(titulo)))


# Sustantivos que, al comienzo del nombre, indican que es un accesorio de otra cosa.
ACCESORIOS_LOCALES = frozenset(
    ["funda", "estuche", "forro", "carcasa", "protector", "vidrio", "mica", "cargador",
     "cable", "adaptador", "soporte", "repuesto", "control", "correa", "pulso", "broca",
     "brocas", "portabrocas"]
)
_RE_PARA = re.compile(r"\bpara\s+(?:(?:el|la|los|las|un|una|tu|su)\s+)?((?:\w+\s+){0,2}\w+)")


def es_accesorio_de(nombre: str, consulta: str) -> bool:
    """El producto es un accesorio de lo que se busca, no lo que se busca.

    "Broca para Taladro Percutor" no es un taladro; "Funda para portátil Lenovo" no es
    un portátil. Si el nombre empieza por lo que se busca ("Morral para portátil" al
    buscar un morral) o la consulta pide el accesorio, no aplica.
    """
    buscadas = set(palabras(consulta))
    buscadas |= {p[:-1] for p in buscadas if p.endswith("s") and len(p) > 3}
    del_nombre = palabras(nombre)
    if not del_nombre or del_nombre[0] in buscadas or "para" in buscadas:
        return False
    if del_nombre[0] in ACCESORIOS_LOCALES:
        return True
    return any(
        buscadas & set(despues.split()) for despues in _RE_PARA.findall(normalizar(nombre))
    )


def es_usado(texto: str) -> bool:
    """Reacondicionado, usado o de exhibición: no se compara con el producto nuevo."""
    return bool(USADOS.intersection(palabras(texto))) or "open box" in normalizar(texto)


def misma_condicion(a: str, b: str) -> bool:
    """Los dos son accesorios o ninguno, y los dos son nuevos o ninguno."""
    return es_accesorio(a) == es_accesorio(b) and es_usado(a) == es_usado(b)


def familia(tienda_id: str) -> str:
    return FAMILIAS.get(tienda_id, tienda_id)


def voces(oferta: Oferta) -> set[str]:
    """Quién pone el precio de una oferta: el dueño de la tienda y, si lo hay, el vendedor.

    Un mismo vendedor publica igual en varias tiendas (Éxito, Olímpica, Home Sentry), y
    eso no son tres precios independientes sino uno repetido.
    """
    quienes = {f"tienda:{familia(oferta.tienda_id)}"}
    vendedor = normalizar(oferta.vendedor or "").strip()
    if vendedor:
        quienes.add(f"vendedor:{vendedor}")
    return quienes


def independientes(oferta: Oferta, candidatas: list[Oferta]) -> list[Oferta]:
    """De las candidatas, la más barata por cada voz distinta a las de `oferta`."""
    usadas = set(voces(oferta))
    elegidas: list[Oferta] = []
    for otra in sorted(candidatas, key=lambda o: o.precio):
        quienes = voces(otra)
        if quienes & usadas:
            continue
        usadas |= quienes
        elegidas.append(otra)
    return elegidas


@dataclass
class Grupo:
    """Ofertas que corresponden al mismo producto."""

    ofertas: list[Oferta] = field(default_factory=list)
    via: str = "unico"  # "ean", "modelo" o "unico"

    @property
    def principal(self) -> Oferta:
        """La oferta con el nombre más descriptivo: sirve para buscar el producto afuera."""
        return max(self.ofertas, key=lambda o: (bool(o.marca), len(o.nombre)))

    @property
    def marca(self) -> str:
        marcas = [normalizar(o.marca) for o in self.ofertas if o.marca]
        return max(set(marcas), key=marcas.count) if marcas else ""

    @property
    def modelos(self) -> set[str]:
        return {m for o in self.ofertas for m in modelos_de(o)}

    @property
    def eans(self) -> set[str]:
        return {e for o in self.ofertas for e in o.eans}

    @property
    def precio_mediano(self) -> float:
        return median(o.precio for o in self.ofertas)

    def otras_tiendas(self, oferta: Oferta) -> list[Oferta]:
        """La mejor oferta de cada dueño o vendedor distinto al de `oferta`."""
        return independientes(oferta, [o for o in self.ofertas if o is not oferta])


@dataclass(frozen=True)
class Huella:
    """Lo que define a un producto sin importar el color ni el orden de las palabras."""

    marca: str
    palabras: frozenset[str]
    medidas: frozenset[str]
    procesador: str
    accesorio: bool
    usado: bool = False


def huella_de(oferta: Oferta) -> Huella:
    marca = normalizar(oferta.marca)
    return Huella(
        marca=marca,
        palabras=frozenset(
            p for p in distintivos(oferta.nombre) if p != marca and not _RE_DETALLE.match(p)
        ),
        medidas=frozenset(m for m in medidas(oferta.nombre) if m.endswith(("gb", "tb", "in"))),
        procesador=procesador(oferta.nombre),
        accesorio=es_accesorio(oferta.nombre),
        usado=es_usado(oferta.nombre),
    )


# Parte del nombre más corto que debe estar en el otro para ser la misma referencia.
PARECIDO_MINIMO = 0.8
# Dentro de una misma referencia los precios no difieren más que esto.
RAZON_MAXIMA_VARIANTES = 1.8


def _en_gb(medida: str) -> float:
    return float(medida[:-2]) * (1024 if medida.endswith("tb") else 1)


def medidas_compatibles(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> bool:
    """Dos juegos de medidas no se contradicen.

    Unas tiendas ponen la memoria RAM en el nombre y otras no, así que no se exige que
    las medidas sean idénticas: debe coincidir el almacenamiento (la capacidad mayor) y
    el tamaño; la RAM solo se compara si los dos nombres la traen.
    """
    for unidad in ("in",):
        en_a = {m for m in a if m.endswith(unidad)}
        en_b = {m for m in b if m.endswith(unidad)}
        if en_a and en_b and en_a != en_b:
            return False
    cap_a = sorted(_en_gb(m) for m in a if m.endswith(("gb", "tb")))
    cap_b = sorted(_en_gb(m) for m in b if m.endswith(("gb", "tb")))
    if bool(cap_a) != bool(cap_b):
        return False
    if not cap_a:
        return True
    if cap_a[-1] != cap_b[-1]:
        return False
    ram_a, ram_b = set(cap_a[:-1]), set(cap_b[:-1])
    return not (ram_a and ram_b) or bool(ram_a & ram_b)


def misma_referencia(a: Huella, b: Huella) -> bool:
    """Misma marca, especificaciones y casi las mismas palabras: otra presentación."""
    if not a.palabras or not b.palabras:
        return False
    if a.accesorio != b.accesorio or a.usado != b.usado:
        return False
    if a.marca and b.marca and a.marca != b.marca:
        return False
    if a.procesador != b.procesador or not medidas_compatibles(a.medidas, b.medidas):
        return False
    # Un S25 no es un S25 Ultra: las palabras de variante deben ser las mismas.
    if VARIANTES & a.palabras != VARIANTES & b.palabras:
        return False
    # Se mide contra el nombre más corto: las tiendas agregan detalles distintos al mismo
    # producto, y lo que importa es que el nombre breve esté contenido en el largo.
    menor = min(len(a.palabras), len(b.palabras))
    return menor >= 2 and len(a.palabras & b.palabras) / menor >= PARECIDO_MINIMO


def variantes_en_otras_tiendas(
    oferta: Oferta, todas: list[Oferta], huellas: dict[int, Huella], excluir: set[int]
) -> list[Oferta]:
    """La mejor oferta de cada dueño distinto para la misma referencia en otra presentación.

    `excluir` son las ofertas del propio grupo (ya cuentan como mismo producto).
    """
    huella = huellas[id(oferta)]
    parecidas = []
    for otra in todas:
        if id(otra) in excluir:
            continue
        bajo, alto = sorted((oferta.precio, otra.precio))
        if bajo <= 0 or alto / bajo > RAZON_MAXIMA_VARIANTES:
            continue
        if misma_referencia(huella, huellas[id(otra)]):
            parecidas.append(otra)
    return independientes(oferta, parecidas)


@dataclass(frozen=True)
class Ficha:
    """Especificaciones que fijan el precio de un computador, sin importar la marca."""

    procesador: str
    almacenamiento: float
    memoria: float | None
    pantalla: str


def ficha_de(oferta: Oferta) -> Ficha | None:
    """La ficha técnica, o None si el nombre no trae procesador y almacenamiento."""
    procesador_ = procesador(oferta.nombre)
    del_nombre = medidas(oferta.nombre)
    capacidades = sorted(_en_gb(m) for m in del_nombre if m.endswith(("gb", "tb")))
    if not procesador_ or not capacidades or es_accesorio(oferta.nombre):
        return None
    pantallas = sorted(m for m in del_nombre if m.endswith("in"))
    return Ficha(
        procesador=procesador_,
        almacenamiento=capacidades[-1],
        memoria=capacidades[0] if len(capacidades) > 1 else None,
        pantalla=pantallas[0] if pantallas else "",
    )


def procesador_legible(clave: str) -> str:
    """De la clave interna a como lo escriben las tiendas: "intel5" pasa a "core i5"."""
    if clave.startswith("intel"):
        return f"core i{clave[5:]}"
    if clave.startswith("ryzen"):
        return f"ryzen {clave[5:]}"
    return clave


# Entre equipos de la misma ficha los precios no difieren más que esto.
RAZON_MAXIMA_FICHA = 1.7


def misma_ficha(a: Ficha, b: Ficha) -> bool:
    if a.procesador != b.procesador or a.almacenamiento != b.almacenamiento:
        return False
    if a.memoria and b.memoria and a.memoria != b.memoria:
        return False
    return not (a.pantalla and b.pantalla) or a.pantalla == b.pantalla


def comparables_por_ficha(
    oferta: Oferta, todas: list[Oferta], fichas: dict[int, Ficha | None], excluir: set[int]
) -> list[Oferta]:
    """Equipos de otras voces con la misma ficha técnica: orientan cuando no hay más."""
    propia = fichas.get(id(oferta))
    if propia is None or es_usado(oferta.nombre):
        return []
    parecidos = []
    for otra in todas:
        ficha = fichas.get(id(otra))
        if id(otra) in excluir or ficha is None or es_usado(otra.nombre):
            continue
        bajo, alto = sorted((oferta.precio, otra.precio))
        if bajo > 0 and alto / bajo <= RAZON_MAXIMA_FICHA and misma_ficha(propia, ficha):
            parecidos.append(otra)
    return independientes(oferta, parecidos)


def modelos_de(oferta: Oferta) -> set[str]:
    codigos = codigos_de_modelo(oferta.nombre)
    if oferta.modelo and len(oferta.modelo) >= 5:
        codigos.add(oferta.modelo.upper())
    return codigos


def _marcas_compatibles(a: Oferta, b: Oferta) -> bool:
    ma, mb = normalizar(a.marca), normalizar(b.marca)
    if not ma or not mb:
        return True
    if ma in mb or mb in ma:
        return True
    # Los vendedores de terceros ponen su propio nombre en la marca: se mira el título.
    return ma in normalizar(b.nombre) or mb in normalizar(a.nombre)


def _comparables(a: Oferta, b: Oferta) -> bool:
    bajo, alto = sorted((a.precio, b.precio))
    if bajo <= 0 or alto / bajo > RAZON_MAXIMA:
        return False
    return misma_condicion(a.nombre, b.nombre)


def agrupar(ofertas: list[Oferta]) -> list[Grupo]:
    """Reúne las ofertas del mismo producto. Devuelve un grupo por producto."""
    padre = list(range(len(ofertas)))
    via = ["unico"] * len(ofertas)

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(i: int, j: int, motivo: str) -> None:
        ri, rj = raiz(i), raiz(j)
        if ri != rj:
            padre[rj] = ri
        for k in (ri, rj, i, j):
            if via[k] != "ean":
                via[k] = motivo

    por_ean: dict[str, int] = {}
    for i, oferta in enumerate(ofertas):
        for ean in oferta.eans:
            clave = ean.lstrip("0")
            if clave in por_ean:
                unir(por_ean[clave], i, "ean")
            else:
                por_ean[clave] = i

    con_modelo = [(i, modelos_de(o)) for i, o in enumerate(ofertas)]
    con_modelo = [(i, m) for i, m in con_modelo if m]
    for posicion, (i, modelos_i) in enumerate(con_modelo):
        for j, modelos_j in con_modelo[posicion + 1:]:
            if raiz(i) == raiz(j):
                continue
            if not any(mismo_modelo(a, b) for a in modelos_i for b in modelos_j):
                continue
            if _marcas_compatibles(ofertas[i], ofertas[j]) and _comparables(ofertas[i], ofertas[j]):
                unir(i, j, "modelo")

    grupos: dict[int, Grupo] = {}
    for i, oferta in enumerate(ofertas):
        r = raiz(i)
        grupo = grupos.setdefault(r, Grupo())
        grupo.ofertas.append(oferta)
        if via[i] == "ean" or grupo.via == "unico":
            grupo.via = via[i] if via[i] != "unico" else grupo.via
    for grupo in grupos.values():
        if len(grupo.ofertas) == 1:
            grupo.via = "unico"
    return list(grupos.values())
