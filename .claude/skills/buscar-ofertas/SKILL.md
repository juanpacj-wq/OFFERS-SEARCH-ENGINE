---
name: buscar-ofertas
description: Busca un producto en tiendas en línea de Colombia y lo compara por precio. Úsala cuando el usuario pida buscar, cotizar o comparar el precio de un producto, encontrar dónde está más barato, o ver ofertas y descuentos de algo ("busca un morral totto", "dónde está más barato el aceite", "ofertas de audífonos").
---

# Buscar ofertas

El motor vive en este repositorio (`src/ofertas`). Consulta las tiendas en paralelo y
devuelve precio, precio de lista, descuento, existencias, enlace y código de barras.

## Cómo buscar

Corre siempre con salida JSON y desde la raíz del repositorio:

```
uv run ofertas buscar "<consulta>" --json --max 30
```

Opciones útiles:

- `--tiendas olimpica,jumbo`: limita a ciertas tiendas (`uv run ofertas tiendas` las lista).
- `--orden descuento`: ordena por porcentaje de descuento en vez de por precio.
- `--descuento-min 20`: solo ofertas con ese descuento o más.
- `--precio-max 150000`: tope de precio en pesos.
- `--por-tienda 100`: revisa más productos por tienda (por defecto 50).
- `--sin-filtro`: no exige que el nombre contenga todas las palabras buscadas.
- `--agotados`: incluye productos sin existencias.

## Historial de precios

Cada oferta puede traer un campo `historial` con lo que se sabía de ese producto antes
de esta búsqueda: `veces_visto`, `minimo_visto`, `maximo_visto`, `precio_anterior` y una
`lectura` ya redactada. Si viene en `null`, es la primera vez que se ve.

- Úsalo para decir si la oferta es real: "es el precio más bajo que he registrado" o
  "la semana pasada estaba más barato".
- Si la lectura dice "descuento dudoso", adviértelo: la tienda anuncia un precio de
  lista que nunca se observó.
- Con pocas observaciones no saques conclusiones; di desde cuándo hay datos.
- `uv run ofertas historial "<palabras>" --json` muestra los precios guardados.

## Lista de seguimiento

- `uv run ofertas seguir "<consulta>" --objetivo <precio> --tiendas a,b`: agrega una
  búsqueda cuando el usuario diga que quiere esperar a que algo baje.
- `uv run ofertas revisar --json`: busca ahora todo lo seguido y marca
  `llego_al_objetivo`. Córrelo cuando el usuario pregunte por lo que sigue.
- `uv run ofertas seguimientos --json` y `uv run ofertas dejar <id>`.

No programes revisiones automáticas (tareas, cron, bucles): las revisiones se hacen
cuando el usuario las pide.

## Cómo armar la consulta

- Usa pocas palabras y concretas: producto, marca y modelo ("morral totto", "aceite premier
  girasol"). El filtro exige que todas aparezcan en el nombre o la marca.
- Si vuelven cero ofertas, quita palabras o prueba un sinónimo antes de decir que no hay.
  Cada tienda nombra los productos a su manera (Nike no responde a "tenis", sí a "air").
- Si el usuario busca un producto exacto, revisa `mismo_producto`: agrupa por código de
  barras lo que es idéntico en varias tiendas, que es la comparación confiable.

## Cómo responder

1. Empieza por la respuesta: la oferta más barata que sí corresponde a lo pedido, con
   tienda, precio y enlace.
2. Descarta a mano lo que no sea el producto (accesorios, repuestos, tamaños distintos).
   El resultado más barato de la lista muchas veces es un accesorio.
3. Compara presentaciones equivalentes; si los tamaños difieren, dilo o calcula el
   precio por unidad.
4. Informa la cobertura: qué tiendas respondieron y cuáles están en `tiendas_fallidas`,
   con su motivo. Nunca presentes un resultado como "el más barato" sin decir en qué
   tiendas se buscó.
5. Los precios son los del momento de la consulta; no afirmes que siguen vigentes.

## Particularidades de las tiendas

- Falabella y Homecenter traen `precio_tarjeta`: el precio pagando con tarjeta CMR. Es
  menor que `precio`, pero solo aplica a quien tenga esa tarjeta; menciónalo aparte y
  no lo uses para decir cuál tienda es más barata.
- Falabella, Homecenter, Lenovo y HP no informan unidades: `existencias` llega en `null`
  cuando el producto está disponible.
- Alkosto, Ktronix y Alkomprar son del mismo grupo y suelen tener el mismo precio.
- En Lenovo los nombres son de modelo ("ThinkPad E14"); la palabra "portátil" se
  reconoce por la categoría. Para esa tienda funciona mejor buscar por modelo.
- En Falabella venden terceros (`vendedor`); si el vendedor no es Falabella, dilo.
- Rappi es un domicilio: `vendedor` es el comercio (Turbo, Éxito, La Rebaja), el precio
  no incluye el envío y corresponde a una ubicación por defecto en Bogotá. Dilo siempre
  que cites un precio de Rappi.
- Samsung: el precio es el de venta que informa su tienda; no incluye promociones
  por medio de pago o cupón, así que en el sitio puede ser menor. El enlace lleva a la
  búsqueda del código del producto, no a su página.
- Éxito a veces rechaza la consulta; si aparece en `tiendas_fallidas`, repórtalo.

## Tiendas de navegador: Amazon, Dafiti, Decathlon, Farmatodo, Makro, LG, PriceSmart y Claro

No entran en una búsqueda normal. Agrégalas con `--navegador` o nombrándolas en
`--tiendas` (por ejemplo `--tiendas decathlon,dafiti`), y corre con el extra:
`uv run --extra navegador ofertas buscar ...`.

- Abren una ventana visible de Edge en el equipo del usuario y tardan de 5 a 10 segundos
  cada una. Úsalas cuando el usuario pida esas tiendas o cuando la categoría lo amerite
  (deporte y moda para Decathlon y Dafiti; importados para Amazon).
- Amazon muestra precios convertidos a pesos, sin envío ni impuestos de importación:
  dilo siempre, porque el costo final es mayor. Sus títulos vienen traducidos (dice
  "zapatillas" o "computadora portátil"), así que ajusta la consulta.
- Si el error dice que la tienda pide una verificación, no intentes saltarla: pídele al
  usuario que corra `uv run --extra navegador ofertas navegador <tienda>`, la resuelva a
  mano y repita.

## Límites actuales

Cubre 47 tiendas (`uv run ofertas tiendas` las lista): supermercados y droguerías
(Olímpica, Jumbo, Carulla, Éxito, D1, Colsubsidio, Locatel, La Rebaja, Rappi), tecnología y hogar
(Falabella, Homecenter, Alkosto, Ktronix, Alkomprar, Easy, Home Sentry, Haceb, Spring,
Tigo, Agaval, Electrojaponesa, Electrobello, Oportunidades, PC Ware, Tauro, IKEA, Lenovo, HP, Samsung), y moda y otros (Pepe Ganga, Panamericana, Vélez, Arturo
Calle, Nike, Totto, Levi's, Americanino, Chevignon, Mattelsa, Offcorss, Pilatos,
Studio F, Tennis, Reebok, Calzatodo, Bosi, Cromantic). Con tantas tiendas conviene limitar con `--tiendas` cuando la categoría
es clara. El buscador general de MercadoLibre no está disponible (ver más abajo).
adidas.co, Acer, Asus, Xiaomi y otras no están
conectadas (`uv run ofertas tiendas` muestra el motivo); si el usuario las pide,
dilo. No intentes saltarte sus protecciones antibot.

## MercadoLibre: solo tiendas oficiales de marca

La tienda `meli_oficial` (de navegador) lee la portada de la tienda oficial de la marca
que aparezca en la consulta: "portatil lenovo" abre la tienda de Lenovo, "tenis adidas"
la de adidas. Son unos 20 productos destacados, no todo MercadoLibre. Úsala cuando la
consulta nombre una marca y aclara ese alcance al responder. El buscador general de
MercadoLibre no está disponible: pide verificación de cuenta.

## Precios del extractor genérico

Farmatodo, Makro, LG, PriceSmart y Claro se leen con un extractor genérico que toma el
menor precio visible en la tarjeta. Ese precio puede estar condicionado a una membresía
o a un medio de pago (PriceSmart es un club con membresía). Antes de afirmar que una de
estas tiendas es la más barata, dilo y sugiere confirmar en el enlace.
