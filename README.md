# Motor de ofertas

Busca un producto en tiendas en línea de Colombia y lo compara por precio. Está pensado
para usarse desde Claude Code (skill `buscar-ofertas`) o directamente por consola.

## Uso

```
uv sync
uv run ofertas buscar "morral totto"
uv run ofertas buscar "aceite girasol" --tiendas olimpica,jumbo,carulla --max 10
uv run ofertas buscar "camisa" --orden descuento --descuento-min 30
uv run ofertas buscar "cuaderno" --json
uv run ofertas tiendas
```

Si `uv sync` falla con un error de certificado (`UnknownIssuer`), usa
`uv sync --system-certs`: pasa en redes corporativas que inspeccionan el tráfico.

## Descuentos reales y descuentos engañosos

Es lo más importante del motor. Muchas tiendas inflan el precio de lista ("antes
$3.209.900") para anunciar un descuento grande sobre lo que en realidad es el precio de
siempre. El motor nunca usa el precio de lista de la tienda como referencia: estima el
**precio real** con evidencia independiente y juzga cada oferta contra él.

```
uv run ofertas buscar "televisor samsung 55"                   # cada oferta trae su veredicto
uv run ofertas buscar "televisor 55" --solo-reales --orden ahorro
uv run ofertas verificar "galaxy s25 ultra 256gb"              # informe a fondo por producto
uv run ofertas verificar "portatil lenovo" --navegador         # además consulta Amazon
uv run ofertas buscar "morral" --sin-internacional             # solo tiendas e historial
```

### De dónde sale el precio real

En orden de confianza:

1. **Mercado local:** a cuánto venden hoy el mismo producto las demás tiendas (mediana).
   Tiendas del mismo dueño (Alkosto, Ktronix y Alkomprar; Éxito y Carulla) y un mismo
   vendedor repetido en varias tiendas cuentan como una sola voz.
2. **Misma referencia en otro color:** cuando el producto idéntico no está en dos
   tiendas más, sirve la misma referencia en otra presentación.
3. **Historial propio:** el precio habitual del producto en esa tienda (3 observaciones
   en 7 días o más).
4. **Precio internacional:** lo que cuesta afuera, convertido con la TRM oficial del
   día, más el IVA (19%) y un margen de importación: hasta 30% en general y hasta 55%
   en confecciones, que pagan 40% de arancel cuando no vienen de un país con TLC. Se
   puede cambiar con la variable `OFERTAS_MARGEN_IMPORTACION` (por ejemplo `0.2`).
5. **Equipos de igual ficha técnica:** para computadores que solo vende una tienda y no
   tienen referencia afuera, la mediana de otros equipos con el mismo procesador,
   memoria y almacenamiento (3 tiendas o más). Es la evidencia más débil: el veredicto
   sale "(aproximado)". En `verificar` se hace además una búsqueda aparte de equipos con
   ese procesador en todas las tiendas.

### Cómo se reconoce el mismo producto

- Entre tiendas colombianas: por código de barras o, si falta, por código de modelo del
  fabricante, con la misma marca y precios comparables.
- Afuera: los códigos de barras casi nunca coinciden, porque los modelos son
  regionales. Se busca el modelo sin su sufijo de país ("UN55CU7000KXZL" se busca como
  "UN55CU7000" y aparece como "UN55CU7000FXZA" en EE. UU.) y, si no, por marca, familia
  y especificaciones. Cada referencia dice qué tan segura es:
  - `exacto`: mismo código de barras o número de artículo. Evidencia fuerte.
  - `modelo`: mismo código de modelo. Evidencia media por sí sola, porque la
    presentación puede cambiar (una herramienta sola y su kit comparten modelo).
  - `equivalente`: misma marca, línea, capacidad y procesador. El veredicto se marca
    "(aproximado)" y no cuenta para `--solo-reales`.
- Un anuncio que solo menciona el modelo ("control para...", "paquete con...") no
  cuenta, y tampoco se comparan usados o reacondicionados con nuevos.
- Los nombres de aquí traen palabras en español que no existen en un título en inglés;
  la equivalencia se mide solo con las palabras que sí aparecen en los resultados de
  afuera (marca, línea y números).

### Veredictos

| Veredicto | Significa |
|---|---|
| Descuento real | El precio está al menos 8% por debajo del precio real. Dice el ahorro verdadero, que suele ser menor que el anunciado |
| Oferta engañosa | Anuncia descuento, pero el precio es el normal del producto |
| Más caro que lo normal | Aun con el descuento anunciado, está por encima del precio real |
| Buen precio, Precio normal, Caro | Lo mismo para ofertas que no anuncian descuento |
| Sin verificar | No hay evidencia independiente; se dice expresamente |

Cuando una oferta no se puede comprobar, el texto agrega cómo salieron las que sí se
comprobaron en esa misma búsqueda ("de 12 ofertas comprobadas, 1 era un descuento
real"): no es un veredicto sobre esa oferta, pero dice cuánto creerle al anuncio.

Además avisa cuando todo el mercado local está por encima de lo que se explica por
importar el producto, y cuando una oferta está por debajo del precio internacional.

### Fuentes internacionales

- Bing Shopping para EE. UU.: la fuente principal. Sirve para cualquier marca, trae
  comercios de todo tipo y responde en menos de un segundo.
- Tiendas de marca en EE. UU.: Lenovo, Samsung e IKEA (IKEA usa el mismo número de
  artículo en todos los países, así que la coincidencia es exacta). Si la tienda de la
  marca ya da el mismo producto, no se pregunta a nadie más.
- UPCitemdb: solo en `verificar` y para lo que las otras fuentes no resolvieron. Su
  plan gratuito admite unas 6 consultas por minuto; si responde que se excedió, no se le
  insiste durante 5 minutos.
- Amazon, con `verificar --navegador`. En la práctica aporta poco: muestra pocos
  resultados con precio para envío a Colombia.
- TRM: datos.gov.co, con respaldo en open.er-api.com.

Lo consultado afuera se guarda 7 días en la base local. Una búsqueda normal investiga
hasta 10 productos de los que se muestran, empezando por los que no tienen con qué
compararse en Colombia, y tarda entre 5 y 10 segundos en total (casi todo es la
búsqueda en las tiendas). `verificar` investiga hasta 12.

### Límites que conviene conocer

- Productos de marcas locales (Totto, Vélez) no tienen precio internacional: se juzgan
  con el mercado local y el historial.
- Si un producto solo lo vende una tienda, no hay historial y afuera no existe el
  mismo modelo ni un equivalente, queda "sin verificar". Pasa con marcas que solo se
  venden en Colombia y con productos sin ficha técnica comparable. Para portátiles de
  configuración regional conviene `verificar`, que busca equipos de igual ficha.
- El margen de importación es una estimación, no el arancel exacto de cada producto.
- Las constantes del juicio están en `src/ofertas/veredicto.py`.

## Historial de precios y seguimiento

Cada búsqueda guarda el precio de cada producto en una base local
(`datos/historial.db`, fuera del repositorio). Desde la segunda vez que aparece un
producto, el resultado dice si es el precio más bajo registrado, cuánto cambió frente a
la vez anterior y, con suficiente historial (3 observaciones en 7 días o más), si el
precio de lista que anuncia la tienda se llegó a ver o si el descuento es dudoso.

```
uv run ofertas historial "arroz diana"                 # precios guardados
uv run ofertas seguir "televisor samsung 55" --objetivo 1500000 --tiendas alkosto,exito
uv run ofertas seguimientos                            # lista de seguimiento
uv run ofertas revisar                                 # busca ahora todo lo que sigues
uv run ofertas dejar 1                                 # deja de seguir la número 1
uv run ofertas buscar "morral" --sin-historial         # sin leer ni guardar historial
```

El historial solo crece con las búsquedas que tú pides. `ofertas revisar` también se
corre a mano: el motor no consulta las tiendas por su cuenta ni de forma programada.

## Relevancia

Al buscar un producto se descartan sus accesorios: "broca para taladro" no aparece al
buscar un taladro, ni "funda para portátil" al buscar un portátil. Si buscas el
accesorio ("funda portátil"), sí aparece.

## Qué devuelve

- Ofertas ordenadas por precio (o por descuento), con precio de lista, porcentaje de
  descuento, existencias y enlace.
- El mismo producto en varias tiendas, emparejado por código de barras (EAN).
- La cobertura: qué tiendas respondieron, cuántos productos se revisaron en cada una y
  cuáles fallaron y por qué.

## Tiendas

Cincuenta y seis tiendas funcionando (47 sin navegador y 9 con él):

- Catálogo VTEX en JSON (35): Olímpica, Jumbo, Carulla, Éxito, D1, Colsubsidio, Locatel,
  La Rebaja, Agaval, Electrojaponesa, Electrobello, Oportunidades, Reebok, Calzatodo,
  Bosi, Cromantic,
  Pepe Ganga, Panamericana, Easy, Home Sentry, Haceb, Spring, Tigo, Vélez, Arturo Calle,
  Nike, Totto, Levi's, Americanino, Chevignon, Mattelsa, Offcorss, Pilatos, Studio F y
  Tennis. Agregar otra tienda VTEX es agregar una línea en
  `src/ofertas/tiendas.py`.
- Datos incrustados en la página de búsqueda: Falabella, Homecenter y Rappi (en Rappi
  los precios son por comercio, sin envío, y para una ubicación por defecto en Bogotá).
- Índice de búsqueda de la tienda (Algolia): Alkosto, Ktronix y Alkomprar.
- API del buscador de la marca: Lenovo.
- Página de resultados (Magento): HP.
- API de tienda de WooCommerce: PC Ware y Tauro. Sirve para cualquier tienda
  WooCommerce que la tenga abierta (Ara la tiene deshabilitada).
- API del buscador: IKEA.
- API de la tienda de la marca: Samsung. Su buscador ordena mal por relevancia, así
  que se revisan al menos 200 resultados; y solo se toma el precio de venta, sin las
  promociones condicionadas a medio de pago o cupón.

Éxito es inestable: su antibot rechaza por rachas (HTTP 403 o conexión cortada) después
de varias consultas seguidas. El motor no lo evade; cuando pasa, Éxito sale como fallida
en la cobertura de esa búsqueda.

### Tiendas que abren el navegador

Amazon, Dafiti y Decathlon rechazan las peticiones directas, pero cargan en un navegador
de verdad. Para ellas el motor abre el Edge instalado, con un perfil propio
(`~/.cache/ofertas/perfil-navegador`), y lee la página de resultados.

```
uv sync --extra navegador
uv run ofertas buscar "bicicleta" --tiendas decathlon
uv run ofertas buscar "tenis adidas" --navegador      # las suma a las demás
uv run ofertas navegador amazon                       # abre la tienda para resolver una verificación
```

- No entran en una búsqueda normal: hay que nombrarlas o usar `--navegador`, porque
  abren una ventana visible y tardan entre 5 y 10 segundos cada una.
- El motor no oculta que el navegador está automatizado, no altera huellas y no
  resuelve captchas. Si una tienda pide verificación, lo reporta y la resuelves a mano
  con `ofertas navegador <tienda>`; la sesión queda guardada en el perfil.
- En modo oculto (`OFERTAS_NAVEGADOR_OCULTO=1`) Dafiti y Decathlon rechazan la visita.
- Amazon muestra precios convertidos a pesos, sin envío ni impuestos de importación;
  los productos que muestra en otra moneda se descartan.
- Farmatodo, Makro, LG, PriceSmart y Claro también van por navegador, con un extractor
  genérico: busca enlaces cuyo contenedor muestre un precio. Toma el menor precio
  visible como precio de venta y el mayor como precio de lista, así que puede mostrar
  un precio condicionado (membresía o tarjeta); conviene confirmar en el enlace. Claro
  no tiene buscador utilizable: se lee su catálogo de celulares y se filtra por nombre.
- Para agregar otra tienda por esta vía basta una línea en `tiendas.py` con su URL de
  búsqueda y `plataforma="navegador"`.
- MercadoLibre: su buscador pide verificación de cuenta, pero las portadas de sus
  tiendas oficiales de marca cargan sin ella. La tienda `meli_oficial` prueba cada
  palabra de la consulta como nombre de tienda (`/tienda/lenovo`, `/tienda/adidas`) y
  lee los productos destacados de la primera que exista: unas 20 ofertas, solo de esa
  marca. No reemplaza el buscador de MercadoLibre.
- Probadas sin éxito por esta vía: adidas.co (responde HTTP 403; adidas se cubre con su
  tienda oficial en MercadoLibre, Dafiti, Decathlon y Falabella) y Xiaomi (su buscador
  no mostró productos).

Sin conectar, con el motivo comprobado el 2026-11-18 (`uv run ofertas tiendas` las lista):

- Buscador general de MercadoLibre: descartado por ahora. La web pide verificación de
  cuenta y la API exige una aplicación registrada, cuyo trámite pide validar identidad
  y no se pudo completar. El conector por API (`mercadolibre`) queda escrito, sin
  verificar contra la API real y fuera de las búsquedas normales; si algún día hay
  credenciales, van en `.env` como `MELI_CLIENT_ID` y `MELI_CLIENT_SECRET`.
- adidas: responde HTTP 403 incluso en un navegador de verdad. El motor no evade
  protecciones antibot; esta tienda necesita una API oficial o un proveedor de pago.
- Acer: su tienda en línea no opera en Colombia (no aparece entre sus países).
- Asus: el sitio de Colombia no publica precios. Dell no tiene tienda para Colombia.

## Estructura

- `src/ofertas/modelos.py`: modelo común (`Oferta`, `Resultado`) y emparejamiento por EAN.
- `src/ofertas/conectores/`: un conector por plataforma (`vtex`, `falabella`, `alkosto`,
  `lenovo`, `hp`, `samsung`, `rappi`, `woocommerce`, `ikea`, `mercadolibre`) y utilidades comunes en `base.py`.
- `src/ofertas/identidad.py`: reconoce el mismo producto entre tiendas.
- `src/ofertas/veredicto.py`: decide si un descuento es real (lógica pura).
- `src/ofertas/internacional.py`: investiga el precio en el exterior y la TRM.
- `src/ofertas/verificacion.py`: une identidad, investigación y veredicto.
- `src/ofertas/historial.py`: base SQLite con el historial de precios y la lista de
  seguimiento.
- `src/ofertas/motor.py`: consulta en paralelo, filtro de relevancia y orden.
- `src/ofertas/cli.py`: comando `ofertas`.
- `.claude/skills/buscar-ofertas/`: instrucciones para Claude Code.

## Pruebas

```
uv run ruff check .
uv run pytest            # unitarias, sin red
uv run pytest -m red     # contra las tiendas reales
```

## Decisiones

- El motor atiende búsquedas puntuales pedidas por una persona; no rastrea catálogos ni
  corre de forma programada. Por decisión del dueño del proyecto, no se guía por los
  `robots.txt` de las tiendas.
- Una tienda que falla no tumba la búsqueda: queda reportada en la cobertura. Una
  conexión que no alcanza a abrirse se reintenta una sola vez.
- Los certificados se validan contra el almacén del sistema operativo (`truststore`).
- La configuración del buscador de Alkosto, Ktronix y Alkomprar se guarda 6 horas en
  `~/.cache/ofertas` (o en la carpeta que indique `OFERTAS_CACHE`), porque leerla
  cuesta descargar más de 1 MB por tienda.
