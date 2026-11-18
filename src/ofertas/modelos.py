"""Modelo común de datos: toda tienda, sin importar su plataforma, se traduce a esto."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Tienda:
    """Una tienda consultable. `plataforma` decide qué conector la atiende."""

    id: str
    nombre: str
    url_base: str
    plataforma: str = "vtex"
    # Plantilla de la URL de búsqueda, con `{q}`, para plataformas que la necesitan.
    busqueda: str = ""
    # Falso en las tiendas que abren un navegador: son lentas y muestran una ventana,
    # así que solo se consultan cuando se piden.
    por_defecto: bool = True


@dataclass
class Oferta:
    """Un producto en una tienda, con el precio de su variante disponible más barata."""

    tienda_id: str
    tienda: str
    nombre: str
    marca: str
    precio: float
    precio_lista: float
    url: str
    # None cuando la tienda dice que hay, pero no cuántas unidades.
    existencias: int | None = None
    moneda: str = "COP"
    ean: str | None = None
    eans: list[str] = field(default_factory=list)
    vendedor: str | None = None
    imagen: str | None = None
    # Precio pagando con la tarjeta propia de la tienda (CMR en Falabella y Homecenter).
    precio_tarjeta: float | None = None
    # Categoría según la tienda. Cuenta para la relevancia: en una tienda de marca el
    # nombre es "ThinkPad E14" y la palabra "portátil" solo está en la categoría.
    categoria: str = ""

    @property
    def descuento_pct(self) -> float:
        """Porcentaje de descuento frente al precio de lista (0 si no hay rebaja)."""
        if self.precio_lista <= 0 or self.precio >= self.precio_lista:
            return 0.0
        return round((self.precio_lista - self.precio) / self.precio_lista * 100, 1)

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["descuento_pct"] = self.descuento_pct
        return datos


@dataclass
class EstadoTienda:
    """Qué pasó con una tienda en una búsqueda: sirve para saber qué cobertura hubo."""

    tienda_id: str
    tienda: str
    ok: bool
    encontrados: int = 0
    relevantes: int = 0
    total_en_tienda: int | None = None
    error: str | None = None
    segundos: float = 0.0


@dataclass
class Resultado:
    """Respuesta completa de una búsqueda: ofertas y cobertura por tienda."""

    consulta: str
    ofertas: list[Oferta]
    tiendas: list[EstadoTienda]

    @property
    def tiendas_consultadas(self) -> list[EstadoTienda]:
        return [t for t in self.tiendas if t.ok]

    @property
    def tiendas_fallidas(self) -> list[EstadoTienda]:
        return [t for t in self.tiendas if not t.ok]

    def a_dict(self) -> dict:
        return {
            "consulta": self.consulta,
            "ofertas": [o.a_dict() for o in self.ofertas],
            "mismo_producto": [
                {"ean": ean, "ofertas": [o.a_dict() for o in grupo]}
                for ean, grupo in agrupar_por_ean(self.ofertas).items()
            ],
            "tiendas_consultadas": [asdict(t) for t in self.tiendas_consultadas],
            "tiendas_fallidas": [asdict(t) for t in self.tiendas_fallidas],
        }


def agrupar_por_ean(ofertas: list[Oferta]) -> dict[str, list[Oferta]]:
    """Agrupa por código de barras las ofertas que aparecen en más de una tienda.

    Solo devuelve los códigos presentes en dos o más tiendas distintas, con las
    ofertas de cada grupo ordenadas de menor a mayor precio.
    """
    por_ean: dict[str, dict[str, Oferta]] = {}
    for oferta in ofertas:
        for ean in oferta.eans:
            # El mismo código se publica con o sin ceros a la izquierda (UPC y EAN-13).
            tiendas = por_ean.setdefault(ean.lstrip("0"), {})
            actual = tiendas.get(oferta.tienda_id)
            if actual is None or oferta.precio < actual.precio:
                tiendas[oferta.tienda_id] = oferta
    grupos: dict[str, list[Oferta]] = {}
    vistos: set[tuple[int, ...]] = set()
    for ean, tiendas in por_ean.items():
        if len(tiendas) < 2:
            continue
        grupo = sorted(tiendas.values(), key=lambda o: o.precio)
        # Dos códigos del mismo producto (tallas, por ejemplo) producen el mismo grupo.
        huella = tuple(sorted(id(o) for o in grupo))
        if huella in vistos:
            continue
        vistos.add(huella)
        grupos[ean] = grupo
    return grupos
