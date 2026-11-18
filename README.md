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
- Una tienda que falla no tumba la búsqueda: queda reportada en la cobertura.
- Los certificados se validan contra el almacén del sistema operativo (`truststore`).
- La configuración del buscador de Alkosto, Ktronix y Alkomprar se guarda 6 horas en
  `~/.cache/ofertas` (o en la carpeta que indique `OFERTAS_CACHE`), porque leerla
  cuesta descargar más de 1 MB por tienda.
