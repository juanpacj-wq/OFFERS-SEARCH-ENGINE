import pytest

from ofertas import identidad
from ofertas.modelos import Oferta


def oferta(nombre, precio=1000000.0, tienda="a", marca="", ean=None, vendedor=None, modelo=""):
    return Oferta(tienda, tienda.upper(), nombre, marca, precio, precio, f"https://{tienda}/p",
                  eans=[ean] if ean else [], vendedor=vendedor, modelo=modelo)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ('Portátil 14" Pulgadas RAM 8GB SSD 512 GB', {"14in", "8gb", "512gb"}),
        ("Televisor 55 Pulgadas", {"55in"}),
        ("Pantalla de 15,6 pulgadas y 1 TB", {"15.6in", "1tb"}),
        ("Galaxy S25 5G 256GB", {"256gb"}),
        ("Arroz 500 g", {"500g"}),
    ],
)
def test_medidas(texto, esperado):
    assert identidad.medidas(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Portátil LENOVO Ideapad Slim 3 Intel Core 5 RAM 8GB 83RQ003ELM", {"83RQ003ELM"}),
        ("Televisor Samsung 55 Pulgadas Led Uhd4k Smart Tv Un55u8500hk", {"UN55U8500HK"}),
        ("Lenovo Portátil i7-13620H, DDR5 de 16 GB, R7 7735HS, RTX4050, WIFI6", set()),
        ("Tenis adidas Running Response Pace Kj1772 Negro", {"KJ1772"}),
        ("Taladro Dewalt DCD996P2T-B3 20V", {"DCD996P2T-B3"}),
        ("Celular Galaxy S25 Ultra 256GB 5G (SM-S938B)", {"SM-S938B"}),
    ],
)
def test_codigos_de_modelo(texto, esperado):
    assert identidad.codigos_de_modelo(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Intel Core I3 1315U", "intel3"), ("Intel Ci 3 8Gb", "intel3"),
        ("Intel Core 5 RAM 8GB", "intel5"), ("Core Ultra 7", "intel7"),
        ("AMD Ryzen 5 7520U", "ryzen5"), ("R7 7735HS", "ryzen7"),
        ("MacBook Air M3", "m3"), ("Galaxy S25 Ultra", ""),
    ],
)
def test_procesador(texto, esperado):
    assert identidad.procesador(texto) == esperado


def test_mismo_modelo_tolera_el_sufijo_regional():
    assert identidad.mismo_modelo("QN55Q7F", "qn55q7faakxzl")
    assert identidad.mismo_modelo("83RQ003ELM", "83RQ003ELM")
    assert not identidad.mismo_modelo("83RQ003ELM", "83RQ003ELX")
    assert not identidad.mismo_modelo("KJ1772", "KJ17725")  # prefijo demasiado corto


def test_modelo_contenido_reconoce_el_codigo_de_familia():
    assert identidad.modelo_contenido("CU7000", "UN55CU7000KXZL")
    assert not identidad.modelo_contenido("CU7000", "CU7000")
    assert not identidad.modelo_contenido("AB12", "XXAB12YY")


def test_distintivos_quita_relleno_y_colores():
    palabras = identidad.distintivos(
        "Celular Samsung Galaxy S25 Ultra 5G 256Gb Titanio Negro", "SAMSUNG"
    )
    assert palabras == ["samsung", "galaxy", "s25", "ultra"]


def test_agrupa_por_codigo_de_barras_con_o_sin_ceros():
    a = oferta("TV X", ean="8806097082316")
    b = oferta("Televisor X", tienda="b", ean="08806097082316")
    c = oferta("Otra cosa", tienda="c", ean="111")
    grupos = identidad.agrupar([a, b, c])
    assert sorted(len(g.ofertas) for g in grupos) == [1, 2]
    assert next(g for g in grupos if len(g.ofertas) == 2).via == "ean"


def test_agrupa_por_modelo_cuando_no_hay_codigo_de_barras():
    a = oferta("Televisor Samsung Un55cu7000kxzl Negro", 1589768, "carulla", "SAMSUNG")
    b = oferta("Televisor 55 Pulgadas Smarttv UN55CU7000KXZL", 1589900, "falabella", "SAMSUNG")
    (grupo,) = identidad.agrupar([a, b])
    assert grupo.via == "modelo"
    assert grupo.marca == "samsung"


def test_el_modelo_no_une_accesorios_ni_precios_lejanos_ni_otra_marca():
    tv = oferta("Televisor Samsung UN55CU7000KXZL", 1600000, "a", "SAMSUNG")
    soporte = oferta("Soporte para Televisor UN55CU7000KXZL", 900000, "b", "SAMSUNG")
    combo = oferta("Televisor UN55CU7000KXZL + barra de sonido", 5000000, "c", "SAMSUNG")
    ajena = oferta("Monitor UN55CU7000KXZL", 1600000, "d", "ACME")
    assert len(identidad.agrupar([tv, soporte, combo, ajena])) == 4


def test_el_modelo_que_informa_la_tienda_tambien_cuenta():
    a = oferta("Portátil IdeaPad Slim 3", 2000000, "alkosto", "LENOVO", modelo="83RQ003ELM")
    b = oferta("Lenovo IdeaPad Slim 3 83RQ003ELM", 2100000, "falabella", "LENOVO")
    assert len(identidad.agrupar([a, b])) == 1


def test_otras_tiendas_cuenta_una_voz_por_dueno_y_por_vendedor():
    propia = oferta("TV", 100, "exito", ean="1", vendedor="Exito")
    hermana = oferta("TV", 90, "carulla", ean="1", vendedor="Carulla")  # mismo dueño
    tercero_a = oferta("TV", 80, "olimpica", ean="1", vendedor="TecnoPlaza")
    tercero_b = oferta("TV", 80, "homesentry", ean="1", vendedor="tecnoplaza")  # mismo vendedor
    independiente = oferta("TV", 95, "falabella", ean="1", vendedor="Falabella")
    (grupo,) = identidad.agrupar([propia, hermana, tercero_a, tercero_b, independiente])
    otras = grupo.otras_tiendas(propia)
    assert sorted(o.tienda_id for o in otras) == ["falabella", "olimpica"]


def test_mismo_vendedor_en_otra_tienda_no_es_evidencia_independiente():
    propia = oferta("TV", 100, "exito", ean="1", vendedor="TecnoPlaza")
    repetida = oferta("TV", 100, "olimpica", ean="1", vendedor="TecnoPlaza")
    (grupo,) = identidad.agrupar([propia, repetida])
    assert grupo.otras_tiendas(propia) == []


def test_misma_referencia_reconoce_otro_color_y_distingue_variantes():
    def huella(nombre):
        return identidad.huella_de(oferta(nombre, marca="SAMSUNG"))

    negro = huella("Celular Samsung Galaxy S25 Ultra 5G 256Gb 12Ram Titanio Negro")
    rosa = huella("Celular Samsung Galaxy S25 Ultra 256Gb 12 Gbram Rosa Titanio 200Mp")
    base = huella("Celular Samsung Galaxy S25 5G 256Gb Negro")
    grande = huella("Celular Samsung Galaxy S25 Ultra 5G 512Gb Negro")
    funda = huella("Funda para Samsung Galaxy S25 Ultra 256Gb")
    assert identidad.misma_referencia(negro, rosa)
    assert not identidad.misma_referencia(negro, base)
    assert not identidad.misma_referencia(negro, grande)
    assert not identidad.misma_referencia(negro, funda)


def test_variantes_en_otras_tiendas_excluye_el_grupo_y_los_precios_lejanos():
    propia = oferta("Galaxy S25 Ultra 256Gb Rosa", 3000000, "carulla", "SAMSUNG")
    gris = oferta("Galaxy S25 Ultra 256Gb Gris", 4600000, "olimpica", "SAMSUNG")
    azul = oferta("Galaxy S25 Ultra 256Gb Azul", 4700000, "agaval", "SAMSUNG")
    lejana = oferta("Galaxy S25 Ultra 256Gb Verde", 9000000, "jumbo", "SAMSUNG")
    todas = [propia, gris, azul, lejana]
    huellas = {id(o): identidad.huella_de(o) for o in todas}
    halladas = identidad.variantes_en_otras_tiendas(propia, todas, huellas, {id(propia)})
    assert sorted(o.tienda_id for o in halladas) == ["agaval", "olimpica"]


def test_reacondicionado_no_se_agrupa_ni_se_compara_con_nuevo():
    nuevo = oferta("Portátil Lenovo IdeaPad Slim 3 15HP10 Ryzen 5 512GB", 5600000, "carulla",
                   "LENOVO", modelo="83K7000XLM")
    usado = oferta("Computador Reacondicionado Portátil Lenovo IdeaPad Slim 3 15HP10 Ryzen 5 512GB",
                   3100000, "alkosto", "LENOVO", modelo="83K7000XLM")
    assert len(identidad.agrupar([nuevo, usado])) == 2
    assert not identidad.misma_referencia(identidad.huella_de(nuevo), identidad.huella_de(usado))
    assert identidad.es_usado("Celular Samsung Galaxy S24 Renewed")
    assert not identidad.es_usado("Celular Samsung Galaxy S24 Nuevo")
