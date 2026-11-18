"""Pruebas del conector de navegador con una página simulada (sin abrir Edge)."""

import pytest

from ofertas import motor
from ofertas.conectores import base, navegador
from ofertas.modelos import Tienda

AMAZON = Tienda(
    "amazon", "Amazon", "https://a.example", "navegador",
    busqueda="https://a.example/s?k={q}", por_defecto=False,
)


class Respuesta:
    def __init__(self, status):
        self.status = status


class Pagina:
    def __init__(self, datos, status=200, titulo="Resultados", texto=""):
        self.datos, self.status, self.titulo, self.texto = datos, status, titulo, texto
        self.visitada = None
        self.cerrada = False

    async def goto(self, url, **_):
        self.visitada = url
        return Respuesta(self.status)

    async def wait_for_timeout(self, _):
        return None

    async def evaluate(self, _):
        return self.datos

    async def title(self):
        return self.titulo

    async def inner_text(self, _):
        return self.texto

    async def close(self):
        self.cerrada = True


class Contexto:
    def __init__(self, pagina):
        self.pagina = pagina

    async def new_page(self):
        return self.pagina


@pytest.fixture
def con_pagina(monkeypatch):
    def preparar(pagina):
        async def falso_contexto():
            return Contexto(pagina)

        monkeypatch.setattr(navegador, "_contexto", falso_contexto)
        return pagina

    return preparar


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("COP 1,322,666.93", 1322666.93),
        ("COP\xa0879,297.89", 879297.89),
        ("COP 1,322,666", 1322666.0),
        ("$\xa0134.000", 134000.0),
        ("$ 195900", 195900.0),
        ("US$ 499.99", 0.0),
        ("", 0.0),
    ],
)
def test_precio_en_pesos(texto, esperado):
    assert navegador.precio_en_pesos(texto) == esperado


DATO = {
    "nombre": "  Lenovo V15\n Gen 4 ", "marca": "", "precio": "COP 879,297.89",
    "antes": "COP 1,058,126.93", "url": "https://a.example/dp/B01", "imagen": "https://img/a",
}


def test_interpreta_y_descarta_lo_incompleto():
    oferta = navegador.interpretar_producto(DATO, AMAZON)
    assert oferta.nombre == "Lenovo V15 Gen 4"
    assert (oferta.precio, oferta.precio_lista) == (879297.89, 1058126.93)
    assert oferta.descuento_pct == 16.9
    assert navegador.interpretar_producto({**DATO, "precio": ""}, AMAZON) is None
    assert navegador.interpretar_producto({**DATO, "precio": "US$ 300.00"}, AMAZON) is None
    assert navegador.interpretar_producto({**DATO, "url": ""}, AMAZON) is None


async def test_buscar_lee_la_pagina_y_la_cierra(con_pagina):
    pagina = con_pagina(Pagina([DATO, {**DATO, "precio": ""}]))
    ofertas, recibidos, total = await navegador.buscar(None, AMAZON, "laptop lenovo", 50)
    assert (len(ofertas), recibidos, total) == (1, 2, None)
    assert pagina.visitada == "https://a.example/s?k=laptop%20lenovo"
    assert pagina.cerrada


async def test_buscar_reporta_la_verificacion_sin_intentar_resolverla(con_pagina):
    pagina = con_pagina(Pagina([], titulo="Seguridad", texto="Por seguridad, completa este paso"))
    with pytest.raises(base.ErrorTienda, match="ofertas navegador amazon"):
        await navegador.buscar(None, AMAZON, "x")
    assert pagina.cerrada


async def test_buscar_reporta_el_rechazo_del_sitio(con_pagina):
    con_pagina(Pagina([], status=403))
    with pytest.raises(base.ErrorTienda, match="HTTP 403 incluso en el navegador"):
        await navegador.buscar(None, AMAZON, "x")


async def test_sin_resultados_ni_reto_devuelve_vacio(con_pagina):
    con_pagina(Pagina([], texto="No encontramos resultados"))
    assert await navegador.buscar(None, AMAZON, "x") == ([], 0, None)


GENERICA = Tienda("makro", "Makro", "https://m.example", "navegador",
                  busqueda="https://m.example/search?name={q}", por_defecto=False)


def test_generico_toma_el_menor_precio_visible_y_el_mayor_como_lista():
    dato = {"nombre": "TV LG 55", "precios": ["$ 3.699.900", "$ 1.999.900"], "antes": "",
            "url": "https://m.example/p/tv", "imagen": ""}
    oferta = navegador.interpretar_producto(dato, GENERICA)
    assert (oferta.precio, oferta.precio_lista) == (1999900.0, 3699900.0)
    con_comas = {**dato, "precios": ["$21,550"]}
    oferta = navegador.interpretar_producto(con_comas, GENERICA)
    assert (oferta.precio, oferta.descuento_pct) == (21550.0, 0.0)
    assert navegador.interpretar_producto({**dato, "precios": []}, GENERICA) is None


async def test_tienda_sin_extractor_propio_usa_el_generico(con_pagina):
    usados = []
    pagina = con_pagina(Pagina([]))

    async def evaluar(codigo):
        usados.append(codigo)
        return [{"nombre": "Arroz Roa 5000G", "precios": ["$21,550"], "antes": "",
                 "url": "https://m.example/p/arroz", "imagen": ""}]

    pagina.evaluate = evaluar
    ofertas, recibidos, _ = await navegador.buscar(None, GENERICA, "arroz")
    assert usados[0] is navegador.GENERICO
    assert (len(ofertas), recibidos) == (1, 1)


async def test_el_motor_cierra_el_navegador_al_terminar(con_pagina, monkeypatch):
    con_pagina(Pagina([DATO]))
    cierres = []

    async def falso_cerrar():
        cierres.append(1)

    monkeypatch.setattr(navegador, "cerrar", falso_cerrar)
    resultado = await motor.buscar("lenovo", [AMAZON])
    assert len(resultado.ofertas) == 1
    assert cierres == [1]


MELI = Tienda("meli_oficial", "ML oficial", "https://ml.example", "navegador",
              busqueda="https://ml.example/tienda/{q}", por_defecto=False)


class PaginaDeMarcas(Pagina):
    """Simula el sitio: solo `lenovo` es una tienda; lo demás redirige al directorio."""

    def __init__(self):
        super().__init__([])
        self.url = ""
        self.visitas = []

    async def goto(self, url, **_):
        self.visitas.append(url)
        self.url = url if url.endswith("/tienda/lenovo") else "https://ml.example/tiendas-oficiales"
        return Respuesta(200)

    async def evaluate(self, _):
        if self.url.endswith("/tienda/lenovo"):
            return [{"nombre": "Portátil Lenovo IdeaPad", "marca": "", "precio": "$ 2.440.900",
                     "antes": "$ 4.599.900", "url": "https://ml.example/p/MCO1", "imagen": ""}]
        return []


async def test_tienda_oficial_prueba_cada_palabra_hasta_hallar_la_marca(con_pagina):
    pagina = con_pagina(PaginaDeMarcas())
    ofertas, recibidos, _ = await navegador.buscar(None, MELI, "Portátil Lenovo")
    assert pagina.visitas == ["https://ml.example/tienda/portatil", "https://ml.example/tienda/lenovo"]
    assert (len(ofertas), recibidos) == (1, 1)
    assert (ofertas[0].precio, ofertas[0].precio_lista) == (2440900.0, 4599900.0)


async def test_tienda_oficial_sin_marca_conocida_devuelve_vacio(con_pagina):
    pagina = con_pagina(PaginaDeMarcas())
    assert await navegador.buscar(None, MELI, "arroz blanco") == ([], 0, None)
    assert len(pagina.visitas) == 2
