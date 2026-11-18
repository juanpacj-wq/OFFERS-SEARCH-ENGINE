# Motor de ofertas: reporte de herramientas (tanda 1, investigación)

Fecha: 2026-11-17. Alcance: solo investigación, no se construyó nada todavía.

Cómo se verificó: las estrellas y la fecha del último push salen de la API de GitHub consultada hoy. Lo demás viene de búsquedas web; cuando la fuente es un blog del propio proveedor o no pude confirmar el dato, lo digo en la fila.

## 1. Conclusiones en corto

1. **No existe un "motor de ofertas para Claude Code" popular que podamos adoptar entero.** Los proyectos hechos específicamente para comparar precios con Claude Code tienen entre 0 y 15 estrellas. Sirven como referencia de diseño, no como base.
2. **Lo que sí tiene éxito masivo es la infraestructura genérica** de scraping y navegación para agentes (Firecrawl, Scrapling, Crawl4AI, browser-use, agent-browser, Playwright MCP). Ahí están las decenas de miles de estrellas, y con eso se arma el motor.
3. **MercadoLibre cerró su API pública de búsqueda** (`/sites/MCO/search` devuelve 403 según varios reportes). El MCP oficial de MercadoLibre sirve para vendedores y documentación, no para buscar ofertas como comprador. Hay que ir por el catálogo oficial (`/products/search` con token de aplicación) o por scraping con navegador sigiloso.
4. **Amazon retiró la PA-API 5** (mayo de 2026) y la reemplazó por la Creators API, que exige cuenta de afiliado con 10 ventas calificadas en 30 días. Para nosotros Amazon queda vía scraping o vía un proveedor (Keepa, Apify, Bright Data).
5. **Buena parte de las tiendas colombianas se puede consultar sin navegador.** Lo probé hoy: nueve tiendas VTEX (Olímpica, Jumbo, Carulla, Pepe Ganga, Panamericana, Vélez, Arturo Calle, Nike y Totto) respondieron JSON con precios sin llave, y Falabella, Homecenter, Alkosto, Ktronix, Asus, Lenovo, HP y Samsung traen los datos incrustados en el HTML. Las difíciles son MercadoLibre, Éxito, Decathlon, adidas, Polo, Rappi, Acer y Dafiti. Dell no tiene tienda en línea para Colombia (sección 4).
6. **Shopify abrió un catálogo global para agentes** (Catalog MCP, protocolo UCP): una sola integración cubre las marcas que venden sobre Shopify.

## 2. Proyectos parecidos hechos con o para Claude Code

Baja popularidad en todos; valen por las ideas.

| Proyecto | Estrellas | Último push | Qué aporta al motor |
|---|---|---|---|
| [anthropics/commerce-agents](https://github.com/anthropics/commerce-agents) | 3.481 | 2026-11-16 | Plano de referencia de Anthropic para agentes de compra y de comercio con Claude. Ojo: es para que un negocio lo incruste sobre su propio catálogo, no busca en tiendas ajenas; nos sirve como patrón de diseño (detalle en la sección 10). |
| [DaizeDong/shopping-aggregator](https://github.com/DaizeDong/shopping-aggregator) | 9 | 2026-10-27 | Skill "orquestador delgado": no raspa, coordina Playwright MCP, Keepa MCP e historial de precios y cupones. Buen patrón de arquitectura. |
| [tannerorourke/shopping-research-mcp](https://github.com/tannerorourke/shopping-research-mcp) | 0 | 2026-11-13 | MCP local con fuentes gratuitas. Idea valiosa: cada herramienta reporta su cobertura, así el agente nunca afirma "mejor precio" sobre una tienda que no consultó. |
| [furey/price-tracker](https://github.com/furey/price-tracker) | 1 | 2026-11-16 | Claude Code en modo headless (`claude -p`) corriendo por cron con solo WebSearch y WebFetch, salida en JSON, notifica cuando el precio baja. |
| [Gagallllllllll/shopping-skill](https://github.com/Gagallllllllll/shopping-skill) | 0 | 2026-11-17 | Skill de asesor de compras: entrevista, investigación en paralelo, precio final con envío, códigos de descuento. |
| [sujithsuresh-803/deal-hunter](https://github.com/sujithsuresh-803/deal-hunter) | 0 | 2026-10-14 | Calcula el "precio real" apilando cupón y tarjeta (Amazon.in, Flipkart, HP). Cada scraper falla en silencio en vez de tumbar la búsqueda. |
| [Cedriccmh/claude-code-skill-scrapling](https://github.com/Cedriccmh/claude-code-skill-scrapling) | 490 | 2026-06-18 | Skill de Claude Code para Scrapling: elige el fetcher y guarda patrones por sitio. El más popular de los skills de scraping específicos. |
| [channel3-ai/skills](https://github.com/channel3-ai/skills) | 12 | 2026-10-26 | Skills oficiales de Channel3: búsqueda sobre 100M+ productos y seguimiento de precios (servicio comercial, cobertura en Colombia sin verificar). |
| [shopsavvy/shopsavvy-mcp-server](https://github.com/shopsavvy/shopsavvy-mcp-server) | 10 | 2026-11-17 | MCP gratuito de ShopSavvy: comparación e historial de precios. Enfocado en Estados Unidos. |
| [BuyWhere/buywhere-mcp](https://github.com/buywhere/buywhere-mcp) | 15 | 2026-11-09 | MCP de búsqueda de productos (Estados Unidos y sudeste asiático). No cubre Colombia. |

MCP de comparación por país con más tracción, útiles como modelo de "un MCP por tienda": [handle-mcp](https://github.com/NJohansen/handle-mcp) (153, supermercados daneses), [alza-mcp-community](https://github.com/lukabudik/alza-mcp-community) (102), [kroger-mcp](https://github.com/CupOfOwls/kroger-mcp) (84), [torob-mcp](https://github.com/mmdju/torob-mcp) (76). Lista curada: [awesome-agentic-commerce](https://github.com/MentionNetwork/awesome-agentic-commerce) (66).

## 3. Extracción de datos: scraping y navegación

Aquí está el núcleo técnico del motor.

| Herramienta | Estrellas | Tipo | Para qué en el motor |
|---|---|---|---|
| [Firecrawl](https://github.com/firecrawl/firecrawl) | 202.569 | API más MCP, plugin y CLI con skill para Claude Code | Convertir páginas en Markdown o JSON estructurado. [MCP](https://github.com/firecrawl/firecrawl-mcp-server) (7.846), [plugin](https://github.com/firecrawl/firecrawl-claude-plugin) (261), [CLI](https://github.com/firecrawl/cli) (689). De pago por uso; hay modo sin llave limitado por IP. No confirmé precios. |
| [Scrapling](https://github.com/D4Vinci/Scrapling) | 103.901 | Librería Python con MCP propio | Fetcher sigiloso que pasa Cloudflare Turnstile (según su documentación) y selectores adaptativos que sobreviven a rediseños. Gratis y local. Candidato principal para Éxito y MercadoLibre. |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | 87.474 | Librería Python | Rastreo local gratuito con extracción por esquema o por LLM. |
| [browser-use](https://github.com/browser-use/browser-use) | 121.304 | Agente de navegador | El LLM decide cada paso. Flexible pero caro en tokens; reservarlo para sitios donde no haya otra salida. |
| [agent-browser](https://github.com/vercel-labs/agent-browser) (Vercel) | 52.301 | CLI de navegador para agentes | Alternativa liviana en tokens a los MCP de navegador; creció muy rápido en 2026. |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | 39.792 | MCP oficial de Microsoft | El estándar para que Claude Code maneje un navegador. Sin antibot propio. |
| [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) | 57.991 | MCP oficial | Inspeccionar la red de una tienda para descubrir sus API internas de búsqueda (lo más rentable: un endpoint JSON vale más que cualquier scraper de HTML). |
| [Lightpanda](https://github.com/lightpanda-io/browser) | 42.184 | Navegador headless | Mucho más liviano que Chrome para volumen alto. |
| [Stagehand](https://github.com/browserbase/stagehand) | 26.082 | SDK TypeScript | Acciones asistidas por IA sobre Playwright. El sigilo depende de Browserbase (de pago). |
| [Crawlee](https://github.com/apify/crawlee) | 26.480 | Librería Node y Python | Colas, reintentos y rotación de proxies para rastreadores de producción. |
| [Camoufox](https://github.com/daijro/camoufox) | 13.375 | Navegador antidetección | Para sitios con Akamai o Cloudflare (adidas respondió 403 de Akamai en mi prueba). |
| [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) | 16.256 | Proxy | Resolver el reto de Cloudflare como servicio local. |
| [browser-act/skills](https://github.com/browser-act/skills) | 6.371 | Skills de navegador | Incluye un skill de detalle de producto de e-commerce. |
| [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai) | 32.833 | Scraper con LLM | Extracción guiada por prompt. |

Servicios gestionados (de pago, resuelven proxies y antibot):

| Servicio | Estrellas | Nota |
|---|---|---|
| [Apify MCP](https://github.com/apify/apify-mcp-server) | 16.681 | Da acceso a miles de "actors". Ya existen actors para MercadoLibre Colombia, Éxito, Falabella (CL, PE, CO), Olímpica y Rappi. [Skills oficiales](https://github.com/apify/agent-skills) (2.505) con `apify-ecommerce`. Atajo más rápido para las tiendas colombianas; el costo por resultado hay que medirlo. |
| [Bright Data MCP](https://github.com/brightdata/brightdata-mcp) | 2.730 | Proxies residenciales y extractores estructurados de Amazon y otros. |
| [SerpApi MCP](https://github.com/serpapi/serpapi-mcp) | 185 | Google Shopping como JSON. Serper es la opción barata. No encontré evidencia de qué tan buena es la cobertura con `gl=co`; hay que probarla. |

## 4. Fuentes por tienda: qué camino tiene cada una

Diagnóstico hecho hoy con una petición HTTP simple (sin navegador, sin proxy) a cada sitio. "Abierto" significa que respondió datos de producto a esa petición; "protegido" significa que respondió un reto antibot. Una sola petición no prueba que aguante volumen.

### Nivel 1: JSON abierto, sin llave (lo más barato)

| Tienda | Evidencia | Camino |
|---|---|---|
| Olímpica, Jumbo Colombia, Carulla, Pepe Ganga, Panamericana, Vélez, Arturo Calle, Nike Colombia (`nike.com.co`), Totto (`co.totto.com`) | Respondieron JSON con `productName` y precio | Catálogo VTEX: `GET /api/catalog_system/pub/products/search?ft=...`. Un solo adaptador sirve para las nueve. Verifiqué en Olímpica que cada producto trae código de barras (`ean`), precio actual (`Price`), precio de lista (`ListPrice`) y existencias: con eso se calcula el descuento y se empareja el mismo producto entre tiendas. Ojo: en Nike la búsqueda "tenis" devolvió vacío y "air" devolvió productos, así que la relevancia del buscador varía por tienda. |
| MercadoLibre (solo clasificación) | `domain_discovery/search` respondió 200 sin token | Sirve para obtener el `domain_id`; la búsqueda en sí va en el nivel 3. |

### Nivel 2: HTML con datos incrustados (una petición y parseo, sin navegador)

| Tienda | Evidencia | Camino |
|---|---|---|
| Falabella Colombia | 200, con `__NEXT_DATA__` y JSON-LD con precios | Leer el JSON incrustado de la página de búsqueda. |
| Homecenter | 200, con `__NEXT_DATA__` y precios | Igual que Falabella (mismo grupo). |
| Alkosto y Ktronix (y Alkomprar, mismo grupo) | 200, la página usa Algolia y trae precios | Consultar su índice de Algolia directamente; identificar las llaves con Chrome DevTools MCP. |
| Asus Colombia (sitio de marca) | 200, JSON-LD con `productName` y precio | Leer el JSON-LD. La tienda en línea `co.store.asus.com` sí pide captcha. |
| Lenovo Colombia | 200, con JSON-LD | Leer el JSON-LD; confirmar que incluye precio. |
| HP Colombia | 200, Magento con JSON-LD (la página menciona captcha) | Leer el JSON-LD; puede escalar a nivel 3. |
| Samsung Colombia | 200, SAP Hybris con JSON-LD | Leer el JSON-LD. |
| Amazon | 200 con 216 KB de HTML a una petición simple | Funciona en bajo volumen, pero ver la sección 7 sobre el riesgo legal. Historial con Keepa ([cosjef/keepa_MCP](https://github.com/cosjef/keepa_MCP), 73, API de pago). [rigwild/mcp-server-amazon](https://github.com/rigwild/mcp-server-amazon) (63) busca por scraping. |

### Nivel 3: protegido, requiere navegador sigiloso o proveedor

| Tienda | Evidencia | Camino |
|---|---|---|
| MercadoLibre (búsqueda) | `api.mercadolibre.com/sites/MCO/search` respondió 403; el listado web respondió una página con captcha | Catálogo oficial `/products/search?site_id=MCO&domain_id=...` con token de aplicación (camino tomado de un artículo de un tercero, falta probarlo), o Scrapling, o actor de Apify. El [MCP oficial](https://github.com/mercadolibre/mercadolibre-mcp-server) (17 estrellas) no sirve para comprar. |
| Éxito | VTEX, pero 403 con reto de Cloudflare | El mismo adaptador VTEX detrás de Scrapling o FlareSolverr. |
| Decathlon Colombia | 403 con reto de Cloudflare | Igual que Éxito. |
| adidas Colombia | 403 "Access Denied" (Akamai) | Camoufox o proveedor. Es de los más difíciles. |
| Polo Ralph Lauren | Redirección a captcha de PerimeterX | Navegador antidetección o proveedor. No encontré tienda oficial colombiana; se probó el sitio global. |
| Rappi | 500 con página que incluye captcha; no hay API pública de precios | Actor de Apify o su API interna. El paquete `rappi-mcp` apunta a Chile y pide iniciar sesión. |
| Tienda en línea de Asus | 403 con captcha | Usar el sitio de marca (nivel 2). |
| Acer (`acer.com/co-es` y `store.acer.com/es-co`) | Probado con tres métodos: petición simple (tiempo agotado), Edge headless con agente de usuario normal ("Access Denied" en la tienda, vacío en el sitio) y un servicio de lectura desde otra red (conexión cortada). Está detrás de Akamai. | Rechaza todo acceso automatizado. La plataforma global de comercio de Acer es Adobe Commerce (Magento), según un caso de estudio de 2021; no pude confirmar que la tienda colombiana exponga su GraphQL. Caminos: proveedor con desbloqueo (Bright Data) o, más simple, cubrir Acer a través de los distribuidores ya resueltos (Alkosto, Ktronix, Falabella, MercadoLibre). No encontré un scraper específico para la tienda de Acer. |
| Dafiti Colombia | Probado con los mismos tres métodos: el servidor corta la conexión a la petición simple, Edge headless queda vacío y el servicio externo no pudo acceder. Internet Archive tampoco sirvió (límite de peticiones). | Camino identificado: ya existen dos scrapers en Apify que cubren `dafiti.com.co` con precio y descuento, [scrapers_lat/dafiti-scraper](https://apify.com/scrapers_lat/dafiti-scraper) (desde 6,80 USD por 1.000 resultados) y [parseforge/dafiti-latam-scraper](https://apify.com/parseforge/dafiti-latam-scraper) (desde 7,50 USD por 1.000). No los ejecuté. |

### Casos especiales

| Tienda | Hallazgo |
|---|---|
| Dell | **No tiene tienda en línea para Colombia.** `dell.com/es-co` y `dell.com/co` sirven la tienda de Estados Unidos con precios en dólares (confirmado con Edge headless y con el servicio externo). Además responde "Access Denied" al navegador headless por defecto. En Colombia, Dell se consigue por distribuidores (Alkosto, Ktronix, Falabella, Éxito, MercadoLibre), que ya están cubiertos. La tienda de Estados Unidos solo serviría para compras con casillero. |
| Sodimac | `sodimac.com.co` no respondió por ninguno de los tres métodos. La operación de Sodimac en Colombia es Homecenter, que sí está cubierta en el nivel 2. |
| Puma | No encontré una tienda oficial para Colombia: `co.puma.com` no existe, `puma.com/co/es` redirige al sitio corporativo y `colombia.puma.com` no respondió. No estaba en tu lista; queda fuera hasta que se identifique la URL correcta. |

### Marcas sobre Shopify

[Catalog MCP de Shopify](https://shopify.dev/docs/agents/catalog/catalog-mcp) (`search_catalog`, `get_product`) y el skill `ucp` del [Shopify AI Toolkit](https://github.com/Shopify/Shopify-AI-Toolkit) (649). Requiere registrar un perfil de agente; no confirmé los requisitos exactos. Especificación: [UCP](https://github.com/Universal-Commerce-Protocol/ucp) (3.506). No identifiqué todavía qué marcas colombianas están sobre Shopify.

## 5. Seguimiento de precios y alertas

Importa porque una "oferta" solo es real frente al historial: muchas rebajas son precios inflados antes.

| Herramienta | Estrellas | Uso |
|---|---|---|
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | 35.866 | Monitor de cambios con detección de precio y reabastecimiento. Maduro. |
| [PriceBuddy](https://github.com/jez500/pricebuddy) | 1.516 | Rastreador autoalojado con historial y notificaciones. |
| [PriceGhost](https://github.com/clucraft/PriceGhost) | 1.152 | Similar; nació en enero de 2026 y sin commits desde febrero. |
| [Discount Bandit](https://github.com/Cybrarist/Discount-Bandit) | 764 | Multiusuario, tiendas personalizadas. |
| [Apprise](https://github.com/caronc/apprise) | 17.785 | Notificaciones a Telegram, WhatsApp, correo y más desde una sola librería. |

## 6. Propuesta de pila para la tanda 2

Recomendación mía, pendiente de tu visto bueno:

1. **Un adaptador por tienda con contrato común** (producto, precio actual, precio de lista, descuento, envío, URL, fecha), y cada adaptador reporta su cobertura y falla sin tumbar la búsqueda.
2. **Tres niveles de extracción, del más barato al más caro**, que coinciden con los de la sección 4: API JSON (VTEX, Algolia, Catalog MCP de Shopify); luego HTML con datos incrustados (JSON-LD y `__NEXT_DATA__`); y Scrapling o un navegador con agente (agent-browser o Playwright MCP) solo para las tiendas protegidas.
3. **Chrome DevTools MCP como herramienta de desarrollo** para descubrir las API internas de Alkosto, Falabella y las marcas.
4. **Historial de precios propio en base de datos** desde el primer día, para distinguir ofertas reales de rebajas infladas.
5. **Apify como plan B de pago** para las tiendas que resulten muy costosas de mantener.
6. **Pipeline determinista, agente solo para lo difuso:** descarga, parseo e historial en scripts; el modelo se usa para emparejar el mismo producto entre tiendas y para reparar un adaptador cuando la revisión de salud falla (consejo recurrente en Reddit, sección 7).
7. **Probar klura** como forma de convertir las búsquedas de Alkosto, Falabella y las marcas en llamadas de API reutilizables.
8. **Exponer el motor como MCP más un skill de Claude Code**, siguiendo el patrón de shopping-aggregator y revisando antes commerce-agents de Anthropic.

## 7. Reddit y foros

Reddit bloquea a mi buscador y a las consultas sin sesión, así que usé el archivo público Arctic Shift (búsqueda por título, mayo a noviembre de 2026). Limitaciones: el archivo limita las peticiones seguidas, así que repetí las consultas tres veces, la última a razón de una ventana mensual cada 40 segundos. Donde la búsqueda por título seguía fallando, cambié de método: descargué el listado completo de publicaciones del mes y lo filtré localmente. Cobertura final de las tres consultas más difíciles, las tres con los siete meses completos (mayo a noviembre de 2026):

- r/selfhosted "price tracker": ningún hilo.
- r/webscraping "mercadolibre": ningún hilo. En julio, septiembre y noviembre revisé las 420 publicaciones del subreddit una por una.
- r/ClaudeCode "shopping" y temas afines (compras, precios, ofertas, scraping): en julio, septiembre y octubre revisé 21.089 publicaciones. Sobre motores de ofertas o comparación de precios solo apareció [un comparador de cámaras y lentes hecho con Claude Code](https://reddit.com/r/ClaudeCode/comments/1x90xk4/) con 1 voto. Los hilos con votos son los dos ya citados sobre las negativas del modelo a raspar.

Reddit directo (JSON, RSS y la versión antigua) responde 403 a clientes automatizados; es un bloqueo deliberado y no lo forcé. Además, los votos pueden estar desactualizados porque el archivo los captura poco después de publicarse. Hacker News lo consulté por su API oficial (historias de 2026).

**Conclusión:** en ninguna de las dos comunidades apareció un motor de ofertas hecho con Claude Code que haya tenido éxito. Lo que tuvo votos fue otra cosa. De los hilos marcados como "leído" revisé la publicación y los comentarios más votados.

| Hilo | Señal | Qué nos dice |
|---|---|---|
| [Why is it so fussed over web scraping now?](https://reddit.com/r/ClaudeCode/comments/1x2h4zj/why_is_it_so_fussed_over_web_scraping_now/) (r/ClaudeCode, leído) | 150 votos, 144 comentarios | El hilo más votado sobre el tema. El autor reporta que Claude Code ahora se niega a saltarse retos de Cloudflare y respeta `robots.txt`, cuando antes no lo hacía. Los comentarios son sobre todo quejas y chistes; uno con 14 votos explica que cada vez más plataformas (cita a Amazon) son hostiles a los agentes. |
| [Claude Code refusing to build scraper](https://reddit.com/r/webscraping/comments/1wzf7jo/claude_code_refusing_to_build_scraper_any_way/) (r/webscraping, leído) | 67 votos, 137 comentarios | Mismo fenómeno: el modelo se niega cuando el scraper viola los términos del sitio. Los comentarios más votados son chistes, no soluciones técnicas. |
| [Scraping 100+ sites daily with a self-healing agent on a cron job](https://reddit.com/r/ClaudeCode/comments/1xacvb2/scraping_100_sites_daily_with_a_selfhealing_agent/) (r/ClaudeCode, leído) | 2 votos, 12 comentarios | Pocos votos, pero es el hilo con más consejo práctico de gente que opera scrapers diarios, incluido uno de un comparador de precios. Resumen abajo. |
| [klura](https://reddit.com/r/webscraping/comments/1tibgp5/i_built_klura_a_toolkit_for_an_ai_agent_to/) (r/webscraping, leído) | 39 votos; [repo](https://github.com/klura-ai/klura) con 62 estrellas | Herramienta gratuita para Claude Code y cualquier cliente MCP: el agente hace la tarea una vez en el navegador, klura captura las peticiones reales y las guarda como una configuración JSON ejecutable que luego corre sin navegador ni modelo. Es la misma idea que propongo con Chrome DevTools MCP para Alkosto y Falabella, ya empaquetada. Candidata a probar en la tanda 2. |
| [Launch HN: Kampala](https://news.ycombinator.com/item?id=47794514) | 100 puntos, 84 comentarios | Producto comercial con la misma idea: convertir aplicaciones en API por ingeniería inversa. Confirma que ese enfoque tiene tracción. |
| [Launch HN: Intuned](https://news.ycombinator.com/item?id=48445171) | 117 puntos, 58 comentarios | Automatizaciones de navegador como código, mantenibles. Comercial. |
| [Anthropic dropped a full open-source blueprint for shopping + merchant agents](https://reddit.com/r/ClaudeAI/comments/1w5qjhb/anthropic_dropped_a_full_opensource_blueprint_for/) (r/ClaudeAI) | Votos bajos en el archivo | Confirma de forma independiente que commerce-agents es de Anthropic. |
| [Amazon wins court order to block Perplexity's AI shopping agent](https://news.ycombinator.com/item?id=47327309) | 29 puntos | Riesgo legal, ver abajo. |
| [Amazon blocks Meta's Muse AI shopping agent](https://news.ycombinator.com/item?id=49789120) | 19 puntos | Igual. |
| [Can AI Shopping Agents Be Trusted?](https://news.ycombinator.com/item?id=49853522) (F-Secure) | 17 puntos, 29 comentarios | Las páginas de tienda pueden manipular al agente. Refuerza extraer datos con código y no dejar que el modelo "lea" la página y decida. |
| [Why is price comparison still so bad in 2026?](https://news.ycombinator.com/item?id=46940958) | 3 puntos | Sin tracción. |

**Consejos de quienes operan scrapers diarios** (comentarios del hilo de los 100 sitios):

- El trabajo determinista (descargar, parsear, deduplicar, guardar estado) va en scripts simples; el agente solo toca lo que requiere criterio. Un comentarista cuenta que cuando dejó la capa HTTP en manos del agente tuvo fallos intermitentes.
- La revisión de salud es un script (cada etapa terminó, conteos en rango, ningún sitio devolvió cero); el agente se enciende solo cuando esa revisión falla. Así no se gastan tokens en las corridas normales.
- Si una tienda bloquea, se conserva el último dato bueno en vez de borrarlo.
- Quien raspa tiendas dice que no usa herramienta de scraping: consulta el JSON que la plataforma ya publica (en su caso WooCommerce). Coincide con lo que encontré en VTEX.
- Algunos sitios bloquean IP de centros de datos y otros las residenciales; ese comentarista corre desde dos lugares.
- Un comentario advierte sobre inyección de instrucciones al ingerir tanto texto de terceros.

**Lo que esto implica para el motor.** Los dos hilos más votados coinciden en que Claude Code ya no ayuda a saltarse protecciones antibot. Por eso conviene que el motor dependa lo menos posible del nivel 3: las fuentes abiertas (niveles 1 y 2) cubren la mayoría de las tiendas colombianas, y para las protegidas el camino estable es la API oficial cuando existe (catálogo de MercadoLibre) o un proveedor de pago (Apify, Bright Data), no un bypass hecho a mano.

**Segunda pasada por meses.** Confirmó el panorama: los proyectos de compras y precios que la gente publica casi no reciben votos.

- r/mcp "shopping": seis hilos, el mayor con 3 votos. Son anuncios de servidores MCP propios: [uno de inteligencia de compra para 2.250 tiendas de Estados Unidos](https://reddit.com/r/mcp/comments/1wpiz25/i_built_a_shoppingintelligence_mcp_server_ask/), [Hadacart](https://reddit.com/r/mcp/comments/1xim8o1/hadacart_a_readonly_shopping_mcp_that_keeps/) (solo lectura, conserva la fecha de cada dato) y [uno con Google Shopping entre 17 herramientas](https://reddit.com/r/mcp/comments/1wyd0qt/i_built_an_opensource_mcp_server_with_17_live/). Ninguno cubre Colombia.
- r/mcp "ecommerce": tres hilos con 0 a 1 voto; el relevante es [ecommerce-agent-starter](https://reddit.com/r/mcp/comments/1wcdlsm/ecommerceagentstarter_live_product_data_for_ai/).
- r/ClaudeAI "price tracker": dos hilos con 0 a 1 voto, entre ellos [un rastreador de precios de cámaras y lentes hecho con Claude](https://reddit.com/r/ClaudeAI/comments/1x90x94/built_a_camera_and_lens_price_tracker_with_claude/) que ordena las ofertas por cuánto han bajado desde el precio de lanzamiento. Buena idea de métrica para nuestro motor.
- r/ClaudeCode "scraper": [Reddit killed my scraper two months ago](https://reddit.com/r/ClaudeCode/comments/1un0c8x/reddit_killed_my_scraper_two_months_ago_claude/) (65 votos, 24 comentarios), sobre un scraper de Reddit reconstruido con Claude Code. No leí su contenido y no trata de tiendas.

**Otros hilos leídos de r/webscraping y r/ClaudeCode** (pocos votos, pero pertinentes):

- [Total newbie trying to build a retail deal monitor](https://reddit.com/r/webscraping/comments/1wrpgde/total_newbie_trying_to_build_a_retail_deal_monitor/) (5 votos, 16 comentarios): alguien intentando lo mismo que nosotros contra Home Depot, Target y Walmart. Los consejos: empezar por observar el tráfico de red del sitio, no arrancar por las tiendas más grandes y protegidas, y recordar que las IP de centros de datos se bloquean. Nadie recomendó una herramienta lista.
- [Scraping prices and gtin from webshops](https://reddit.com/r/webscraping/comments/1uulnb9/scraping_prices_and_gtin_from_webshops/) (12 comentarios): un comparador que usa el buscador propio de cada tienda en tiempo real y empareja productos por GTIN (el código de barras). Le recomendaron mirar la API de autocompletar del buscador y la API de la plataforma de la tienda. El GTIN es la mejor llave para saber que dos tiendas venden el mismo producto; VTEX lo expone como `ean`.
- [Built a shopping assistant using claude](https://reddit.com/r/ClaudeCode/comments/1vkqx1o/built_a_shopping_assistant_using_claude_how_can_i/) (0 votos): la crítica de los usuarios fue que un asistente que hace muchas preguntas antes de buscar cansa más que escribir una sola frase. Para nuestro motor: buscar primero, afinar después.

En r/mcp los hilos de scraping son casi todos anuncios de servidores con 1 a 4 votos (Firecrawl MCP entre ellos); no hay un consenso de comunidad que citar. Los rastreadores de precios que la gente publica en Hacker News son de nicho (GPU, memoria RAM, carne en el Reino Unido) y ninguno pasó de 5 puntos.

**Riesgo legal con Amazon.** Según los titulares de CNBC, The Register y Reuters enlazados en Hacker News, Amazon obtuvo en marzo de 2026 una orden judicial contra el agente de compras de Perplexity, bloqueó el de Meta en septiembre y en noviembre se reportó un plan para controlar sus datos de producto frente a agentes. No leí los artículos completos. Esos casos son de agentes que compran a nombre del usuario, no de buscadores de precios, pero indican que Amazon es la fuente con más riesgo y la que más conviene consultar a través de un proveedor.

## 8. Precios de los servicios de pago

Cifras de noviembre de 2026 tomadas de comparativas de terceros, no de la página oficial de cada proveedor; confirma en la página de precios antes de contratar.

| Servicio | Gratis | Primer plan de pago | Nota |
|---|---|---|---|
| Firecrawl | 1.000 créditos (una fuente dice que es una sola vez, no mensual) | Hobby: 19 USD al mes por 5.000 créditos. Standard: 99 USD por 100.000 | Los créditos no se acumulan. |
| Apify | 5 USD de crédito al mes | Starter: 19 USD al mes (páginas viejas dicen 29) | Cada scraper cobra aparte por resultado; los de Dafiti cuestan 6,80 a 7,50 USD por 1.000. |
| Bright Data | 5.000 peticiones al mes sin tarjeta | Web Unlocker: 1,50 USD por 1.000 peticiones exitosas | Las fuentes se contradicen sobre si el MCP gasta de esa misma bolsa. |
| Keepa API | No tiene | 49 EUR al mes por 20 tokens por minuto | Solo Amazon. La suscripción Pro de 29 EUR es otro producto. |
| SerpApi | 250 búsquedas al mes | Developer: 75 USD al mes por 5.000 búsquedas | |
| Serper | 2.500 consultas al crear la cuenta | 50 USD por 50.000 créditos (1 USD por 1.000) | Prepago; los créditos vencen a los seis meses. |

Para un motor de uso personal, los planes gratuitos de Bright Data (5.000 peticiones), SerpApi (250 búsquedas) y Apify (5 USD) alcanzan para cubrir las tiendas protegidas a bajo volumen. Es una estimación mía, no la medí.

## 9. Qué dice el `robots.txt` de cada tienda

Descargué y analicé hoy el `robots.txt` de 24 sitios. No es una revisión legal de los términos y condiciones (esa sigue pendiente), pero es la declaración pública y verificable de cada tienda sobre el acceso automatizado.

**Vetan por nombre a los bots de Claude y de otros asistentes:**

- **MercadoLibre Colombia** (sitio y listado): prohibición total para ClaudeBot, Claude-User, GPTBot, ChatGPT-User y los de Perplexity.
- **Amazon**: prohibición total para ClaudeBot, Claude-User, Claude-SearchBot, GPTBot, CCBot, PerplexityBot, Google-Extended y Bytespider.
- **Rappi**: veta a GPTBot y, para todos, las rutas `/api`, `/api-services` y `/base-api`.

**Vetan la ruta que el motor usaría:**

- **Éxito, Carulla y Panamericana**: tienen `Disallow: /api/`, que incluye el catálogo VTEX. Carulla y Panamericana respondieron JSON de todos modos; técnicamente funciona, pero la tienda pide no usarlo.
- **Alkosto y Ktronix**: vetan `/search/` y cualquier URL con `?q=`.
- **Homecenter**: veta sus rutas de búsqueda.
- **Jumbo, Nike, Vélez, Arturo Calle, Pepe Ganga**: vetan las páginas de búsqueda HTML (`/busca/`), no la ruta `/api/` del catálogo. Vélez la permite de forma explícita (`Allow: /api/`).
- **Lenovo, Asus, HP, Samsung**: vetan sus buscadores internos; las páginas de categoría, que son las que traen el JSON-LD, no.

**Sin restricciones relevantes:** Olímpica, Totto y Falabella (solo veta carrito, cuenta y pagos).

**No disponibles:** adidas y Decathlon respondieron 403 incluso al `robots.txt`.

**Cómo leo esto.** Hay tres grupos. Con Olímpica, Totto, Falabella, Jumbo, Nike, Vélez, Arturo Calle, Pepe Ganga y las páginas de categoría de las marcas, el camino técnico coincide con lo que la tienda permite. Con Éxito, Carulla, Panamericana, Alkosto, Ktronix y Homecenter hay que decidir si se respeta el veto (usando páginas de categoría en vez del buscador) o no. Con MercadoLibre y Amazon el mensaje es explícito contra los agentes, y por eso el camino recomendado es su API oficial o un proveedor. Esa decisión es tuya y conviene tomarla antes de la tanda 2.

## 10. Lectura de los repositorios clave

Leí el README, la licencia y la estructura de seis repositorios. No ejecuté ni audité el código.

| Repositorio | Licencia | Lo que confirma la lectura |
|---|---|---|
| [anthropics/commerce-agents](https://github.com/anthropics/commerce-agents) | Apache-2.0, Python, 718 forks | Es un agente de compras para que **un negocio lo incruste en su propia tienda**, sobre su propio catálogo (hay que implementar `StorefrontBackend`). No busca en tiendas ajenas. Nos sirve como patrón: flujos definidos como skills, contratos de herramientas, evaluaciones, y un plugin de Claude Code (`commerce-builder`) con `/scaffold-commerce-agent`. Menos directamente útil de lo que sugerí al principio. |
| [DaizeDong/shopping-aggregator](https://github.com/DaizeDong/shopping-aggregator) | MIT, Python | Se instala como plugin. Reglas de evidencia que vale la pena copiar: misma variante de producto, existencias, identidad del vendedor, costo total de pago (envío, impuestos, cupones verificados) y marca de tiempo por precio. Un cupón sin prueba en carrito se rotula como no verificado. No recomienda Honey. |
| [tannerorourke/shopping-research-mcp](https://github.com/tannerorourke/shopping-research-mcp) | MIT, Python | Plugin con servidor MCP local. Cada respuesta trae `{data, sources_checked, sources_skipped}`. Fuentes: SerpApi Google Shopping, eBay, Shopify `/products/<handle>.json`, JSON-LD de schema.org, OpenGraph y Playwright como último recurso. Es la arquitectura más parecida a la que propongo; candidata a bifurcar y adaptar a Colombia. |
| [furey/price-tracker](https://github.com/furey/price-tracker) | MIT, JavaScript | El modelo solo investiga y devuelve JSON; las reglas de alerta corren en código ("el modelo nunca decide si alertar"). Revisiones directas gratuitas para Shopify y JSON-LD, SQLite, alertas por ntfy, tope mensual de corridas con IA. Nunca resuelve un captcha: marca el sitio y sigue. Una corrida tarda de 7 a 10 minutos, así que no sirve para ofertas relámpago. |
| [klura-ai/klura](https://github.com/klura-ai/klura) | BUSL-1.1 (código disponible, no es open source) | Uso interno gratuito, incluso comercial; prohíbe revenderlo como servicio. Corre local, sin cuenta ni llave. Cada herramienta declara dominios, presupuesto de peticiones y forma de la salida, y solo reporta éxito si los datos cumplen esa forma. |
| [Cedriccmh/claude-code-skill-scrapling](https://github.com/Cedriccmh/claude-code-skill-scrapling) | MIT, 63 forks | Árbol de decisión para elegir el fetcher de Scrapling, plantillas y biblioteca de patrones por tipo de sitio. Incluye una guía de seguridad sobre autorización e inyección de instrucciones. |

## 11. Lo que no quedó cubierto

- **Reddit se consultó a través de un archivo público**, no del sitio (detalle en la sección 7). La cobertura de fechas quedó completa, pero busqué por título, no dentro del texto de las publicaciones ni de los comentarios, y los votos del archivo pueden ser menores que los reales.
- **Todas las tiendas de tu lista tienen diagnóstico.** Las que quedan sin resolver son de acceso, no de investigación: Acer y Dafiti rechazan cualquier acceso automatizado desde esta red, y Puma no tiene una URL colombiana identificada.
- **Los diagnósticos son de una sola petición.** Que una tienda responda una vez no garantiza que tolere consultas frecuentes.
- **Los precios** (sección 8) vienen de comparativas de terceros, no de las páginas oficiales.
- **Los términos y condiciones** de cada tienda no los leí; solo analicé el `robots.txt` (sección 9). No es asesoría legal.
- **Ningún repositorio fue instalado ni ejecutado.** De seis leí README, licencia y estructura (sección 10); del resto, solo descripción y metadatos.
