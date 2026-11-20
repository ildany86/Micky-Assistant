# Hoja de ruta

Qué falta, en qué orden y por qué. Cada etapa tiene objetivo, entregables,
riesgos y criterio de terminado; si algo no tiene las cuatro cosas, no entra.

Las estimaciones son **días de trabajo de una persona**, no fechas. Si le
dedicás dos o tres días por semana, la 0.2 son unas ocho semanas.

---

## Dónde estamos: beta 0.1

Cierre de esta foto: **6 de noviembre de 2026**. Versión `0.1.0b1`.

### Lo que funciona hoy

| Área | Qué hay | Dónde vive |
|---|---|---|
| Catálogo | 55 comandos con parámetros tipados, validación y plantilla de respuesta hablada | `src/miky/data/commands.json`, `src/miky/catalog.py` |
| Motor | planes de hasta 12 pasos, validación completa antes de tocar REAPER, confirmación en los 3 comandos peligrosos, pregunta previa a grabar (arranca en silencio) y flujo de elección cuando hay varios plugins | `src/miky/engine.py`, `src/miky/app.py` |
| Puente | 60 comandos (55 del catálogo + `ping`, `bridge.info`, `state.get`, `action.info`, `app.quit`), un solo Lua de ~3.185 líneas (~106 KB), se instala y arranca con REAPER | `reaper/src/miky/`, `src/miky/data/miky_bridge.lua` |
| Conocimiento | Ocho fichas técnicas curadas (EQ, dinámica, niveles, voz, batería, espacio, grabación, mezcla) que se inyectan solo en consultas de criterio, para que los consejos tengan números y no inventos. Ampliable en `src/miky/knowledge.py` | `src/miky/knowledge.py`, [doc](08-conocimiento.md) |
| IA | Gemini con function calling manual. Cada pedido se clasifica primero por intención y se le mandan solo las herramientas de esa familia (8 en vez de 55: ~84 % menos declaraciones), con prompt compacto (~2.080 tokens de entrada por pedido, antes 3.266), memoria de los últimos intercambios y respaldo al modelo grande si el rápido no resuelve. Proveedores `openai` / `local` / `mock` | `src/miky/ai/`, `src/miky/intent.py` |
| Router | 57 reglas que resuelven pedidos sin consultar la IA (~0,06 ms), con números en palabras, tolerancia a nombres y rechazo de frases con varias órdenes | `src/miky/router.py` |
| Ruteo | envíos entre pistas, salidas físicas por pista (`track.output`, verificado contra REAPER) y ventana de ruteo | `reaper/src/miky/cmd_sends.lua` |
| Plugins | índice de los plugins instalados que se carga al conectar (en esta máquina: 1.497), búsqueda por descripción (`fx.search`) con sinónimos y desempate a favor de VST3/VST sobre los JS de utilería, **favoritos de REAPER como primera opción** (lee `reaper-fxfolders.ini`) lectura de los parámetros reales (x.params) y del medidor de niveles (levels.get) para diagnosticar la sesión, y opciones numeradas cuando hay más de un candidato | `reaper/src/miky/cmd_fx.lua`, `src/miky/app.py` |
| Voz | WASAPI 16 kHz con filtro de pseudo-dispositivos y bloques rearmados a 512, cierre de frase en 550 ms con transcripción especulativa, corrección de marcas y nombres propios, decodificación greedy, caché de voz con precalentado, Silero VAD, faster-whisper `base` int8 con hotwords de las pistas, palabra clave con 8 variantes, ventana de seguimiento sin repetir la palabra, confirmación sí/no, voz argentina masculina (edge-tts) con respaldo SAPI5 | `src/miky/voice/` |
| Interfaz | icono de 104 px con 8 estados (celeste = escuchando, violeta = pensando, verde = hablando), halo que responde al nivel del micrófono, arrastre con posición persistida, Ctrl+rueda, menú, ajustes, confirmación, bandeja, logo propio | `src/miky/ui/`, `src/miky/data/assets/` |
| Seguridad | API key cifrada con DPAPI, render limitado a carpetas permitidas, tope de pasos por pedido | `src/miky/security.py`, `src/miky/engine.py` |
| Operación | configuración TOML editable a mano, `doctor`, CLI de 10 subcomandos, logs | `src/miky/config.py`, `src/miky/doctor.py`, `src/miky/__main__.py` |
| Herramientas | prueba real contra REAPER, autotest de voz sin micrófono, humo de UI, render de estados del icono, generación del catálogo, `miky bench` para medir cada etapa | `tools/`, `src/miky/bench.py` |
| Pruebas | 408 tests de Python y un arnés Lua con REAPER simulado que verifica que **todos** los comandos del catálogo tengan handler | `tests/` |

La prueba de punta a punta está en `research/live_test_report.json`: **55 pedidos
seguidos contra REAPER 7.84 real**, 52 correctos y 3 fallos intencionales (pista,
plugin y marcador inexistentes) que devolvieron el error esperado en español.
Total: 3,2 s de ejecución sumada para los 55 pedidos.

Latencia medida por comando en esa corrida:

| Tramo | Tiempo | Outliers |
|---|---|---|
| Comandos simples (pista, FX, transporte, marcadores) | 15–63 ms, la mayoría 31–47 ms | — |
| Guardar como | — | 109 ms |
| Render de una selección de tiempo | — | 750 ms (0,69 s dentro del puente) |
| Parar después de grabar | — | 1.609 ms (flush de archivos a disco) |

### Lo que todavía no hay

- **Conversación.** No hay historial. Cada pedido es una consulta nueva: el
  modelo ve el estado del proyecto y `last_actions` (6 entradas), pero **nunca ve
  el resultado de lo que ejecutó** —la respuesta la arma una plantilla local—.
  Por eso «no, la otra» o «subilo un poco más» no funcionan.
- **Cobertura.** Ya hay ruteo (envíos), y edición básica de items (cortar en el
  cursor, recortar entre marcadores, borrar). Todavía no hay folders ni grupos,
  automatización, compás (solo BPM), volumen de master ni phase/width.
- **Distribución.** `instalar.bat` es un script de desarrollador: necesita
  Python, internet y el repo. No hay `.exe`, no hay firma, no hay updater, no hay
  onboarding más allá del aviso de bandeja cuando falta la API key.
- **Producto.** Sin presets de sesión, sin memoria de preferencias, sin
  telemetría, sin documentación de usuario más allá de
  [instalación y uso](05-instalacion-uso.md).
- **Voz.** El modelo por defecto es `base`. No hay tabla de precisión medida ni
  `initial_prompt` con los nombres reales de las pistas.
- **Puente.** No escribe `I_FOLDERDEPTH`, no maneja containers ni FX de entrada,
  y el undo es por paso (un plan de 5 pasos deja 5 entradas en el historial).
- **Detalle.** `ai.recovery` está declarado en `AISection` y no se usa en ningún
  lado. O se implementa en la 0.2 o se borra.

---

## Beta 0.2 — «uso diario»

**Objetivo:** grabar una tarde entera sin tocar el mouse, sin sorpresas, y que
otra persona pueda instalarlo sin ayuda.

La beta 0.1 ya demuestra el camino completo. La 0.2 es lo que falta para que no
tengas que volver al mouse cuando pedís algo que el catálogo no cubre.

### 1. Memoria corta de conversación

**Qué.** Mantener los últimos 6 turnos y, cuando la ejecución falla o el pedido
es ambiguo, devolver el resultado al modelo como `function_response` para que
pueda corregir el plan. Es la opción 1 del
[informe de investigación](../research/informe-gemini-api-voz-local-windows.md)
(§A.7), sin estado del lado del servidor.

**Entregable.** `ai/history.py` con una `Conversation` que poda por turnos y por
tokens; segunda llamada gateada por `ai.recovery`; tests con proveedor `mock`
que devuelva historia.

**Riesgo.** Cada turno extra son tokens y, si se usa recovery, dos requests por
pedido en vez de una. En el free tier eso se nota.

**Terminado cuando.** «Subilo un poco más» y «no, la otra» funcionan en dos
turnos seguidos sin repetir el nombre de la pista, y el costo en tokens por
pedido queda medido y documentado.

### 2. Ruteo y envíos

**Qué.** `track.send_add`, `send.set_volume`, `send.set_pan`, `send.set_mode`,
`send.remove`, `track.output_hw` y un `bus.create` que cree la pista, le ponga
nombre y color, y conecte los envíos.

**API.** `CreateTrackSend`, `SetTrackSendInfo_Value` (`D_VOL`, `D_PAN`,
`B_MUTE`, `I_SENDMODE` 0/1/3/8), `GetTrackNumSends`, `RemoveTrackSend`.

**Terminado cuando.** «Creá un bus de reverb, mandale la voz y la guitarra al
30%» se ejecuta en un solo plan, con undo y respuesta que nombre el bus.

### 3. Folders y grupos

**Qué.** `track.folder` (escribir `I_FOLDERDEPTH` en `+1`/`-1`) y `track.group`
(`GetSetTrackGroupMembership`). El detalle del bitfield está en
[referencias de REAPER](06-referencias-reaper.md).

**Cuidado.** Cerrar un folder mal deja huérfanas todas las pistas de abajo. El
comando tiene que validar la estructura y, si el usuario pide meter una pista en
un folder existente, ofrecer «cerrar el folder anterior» en vez de romperlo.

**Terminado cuando.** «Meté la batería en un folder y colapsalo» funciona ida y
vuelta y no toca la estructura que ya existía.

### 4. Items y edición

**Qué.** `item.split` (acción 40012), `item.duplicate`, `item.move`,
`item.trim`, `item.fade`, `item.normalize`, `item.select`, `item.delete`.

**Contexto.** La selección manda: «cortá acá» usa el cursor; «duplicá esto» usa
los items seleccionados; si no hay selección, el comando falla con un mensaje
que explica cómo seleccionar.

**Terminado cuando.** Cortar, mover y duplicar un item por voz, con undo y sin
perder la selección después de cada paso.

### 5. Compás y tempo

**Qué.** `project.set_timesig` (compás 6/8), `project.add_tempo_marker`,
`transport.goto_bar` explícito.

**API.** `SetTempoTimeSigMarker`, `TimeMap2_beatsToTime`,
`TimeMap_GetTimeSigAtTime`. `transport.set_position` ya pasa compás y pulso por
`TimeMap2_beatsToTime`, que respeta el mapa de tempo; lo que falta es **crear** y
**leer** cambios de compás, y que el comando lo diga por voz.

**Terminado cuando.** «Poné 6/8 y andá al compás 12» cae en el lugar correcto,
también después de un cambio de tempo en el medio del proyecto.

### 6. Automatización

**Qué.** `automation.add_point`, `automation.mode` (leer/touch/latch/write),
`automation.clear`, y `track.fade_out` como atajo de envelope de volumen.

**API.** `GetTrackEnvelopeByName`, `InsertEnvelopePoint`, `SetAutomationMode`.

**Riesgo.** Cada pista tiene varias envelopes y los nombres dependen del idioma
en algunos casos. Hay que elegir por nombre normalizado y fallar claro si no
está.

**Terminado cuando.** «Hacé un fade out de 5 segundos al final» se escucha y se
deshace en un solo Ctrl+Z.

### 7. Voz: precisión medida

**Qué.**

- A/B `base` vs `small` con 40 frases (20 comandos, 20 nombres de pista), con y
  sin ruido de fondo, midiendo aciertos y tiempo.
- `initial_prompt` dinámico: inyectar los nombres de pista del proyecto en el
  prompt del STT (hoy es una lista fija de jerga).
- Normalizar números también del lado del texto («menos seis» → −6), no solo en
  el router.

**Terminado cuando.** ≥90% de acierto en comandos y ≥80% en nombres de pista. Si
`small` no baja de 1,5 s p95 en la máquina objetivo, `base` queda como default y
`small` como opción.

### 8. Icono y logo

**Qué.** El logo propio ya está integrado (`logo@2x.png`, con `logo.png` y
`logo.ico` al lado) y el icono dibuja halo por estado. Falta el `.ico` en el
ejecutable (cuando exista) y probar la bandeja a 125%, 150% y 200% de escalado.

**Terminado cuando.** El icono se ve nítido en los tres escalados y el `.exe`
tiene icono propio en Explorador y barra de tareas.

### 9. Instalador

**Qué.**

1. **PyInstaller en modo `onedir`** (no `onefile`: arranca lento y los
   antivirus lo marcan más). Incluir `src/miky/data/` completo.
2. **Modelo de voz.** No empaquetar `small` (484 MB). Descarga en el primer
   arranque a `%APPDATA%\Miky\models`, con progreso, verificación de hash y
   reintento. `base` sí se puede empaquetar.
3. **Inno Setup.** Instalar en `%LOCALAPPDATA%\Miky`, acceso directo, arranque
   con Windows opcional, y un desinstalador que quite el bloque de
   `__startup.lua` (hoy lo hace `miky install-bridge --remove`).
4. **Firma Authenticode** antes de publicar. Sin firma, SmartScreen frena la
   descarga y el usuario promedio no pasa de ahí.

**Terminado cuando.** En un Windows 11 limpio, sin Python ni Git,
`miky-setup-0.2.0.exe` deja todo funcionando en menos de 5 minutos, y el
desinstalador no deja ni el puente ni el bloque de startup.

### 10. Deuda técnica

- Un test del puente por cada comando nuevo (el arnés ya valida catálogo ↔
  handlers, pero no el resultado).
- `doctor`: comparar versión instalada del puente contra la app y avisar si el
  modelo de voz no está descargado.
- Log del puente: hoy el error va a `status.json`; falta un `bridge.log` rotativo
  (la guía de instalación ya lo menciona).
- Investigar el outlier de `transport.stop` después de grabar (1,6 s): si es el
  flush de archivos, la app tiene que avisar «guardando tomas…» en vez de
  parecer colgada.

### Resumen de 0.2

| Ítem | Días |
|---|---|
| Memoria corta | 3 |
| Ruteo y envíos | 3 |
| Folders y grupos | 2 |
| Items y edición | 4 |
| Compás y tempo | 2 |
| Voz medida | 3 |
| Instalador + firma | 5 |
| Deuda técnica | 2 |
| **Total** | **24** |

### Riesgos de la etapa

- **Más comandos, más estado.** Cada comando nuevo puede romper el undo o
  dejar el snapshot inconsistente. Mitigación: un test por comando y correr
  `tools/live_test.py` antes de cada release.
- **Instalador y antivirus.** PyInstaller + PySide6 dispara falsos positivos.
  Mitigación: `onedir`, firma, y subir el binario a VirusTotal antes de publicar.
- **Cuota.** El historial y el recovery consumen más requests. Mitigación: el
  router sigue resolviendo lo básico sin gastar nada.

### Criterio de terminado de 0.2

1. 12 comandos nuevos, cada uno con test, validación y plantilla de respuesta.
2. 40 frases de prueba con ≥90% de acierto en comandos y ≥80% en nombres.
3. «No, la otra» y «subilo un poco más» funcionan con memoria de dos turnos.
4. Instalador probado en una VM limpia, con desinstalación completa.
5. `pytest` verde, `doctor` sin `[x]` y `live_test.py` con 0 fallos inesperados
   en la máquina de desarrollo.

---

## Versión 1.0 — producto

**Objetivo:** que lo pueda instalar y usar alguien que no sabe qué es un venv.

### Entregables

1. **Empaquetado y firma definitivos**, con build reproducible y versión
   estampada en el `.exe`, en el puente y en el `status.json`.
2. **Onboarding asistido.** Detectar REAPER, instalar el puente, elegir micrófono
   con medidor de nivel en vivo, elegir voz, y ejecutar un comando real de prueba
   que se deshace solo («creé una pista de prueba» → borrarla). Si algo falla, el
   onboarding dice exactamente qué y cómo arreglarlo.
3. **Presets de sesión.** «Preparame una sesión de batería», «de voz», «podcast»,
   «para mezclar». Son plantillas declarativas en JSON que se expanden a
   comandos del catálogo (nombres, colores, folders, armado, entrada, monitoreo,
   tempo, metrónomo, render). Nada de código especial: si un preset necesita un
   comando que no existe, no se puede escribir.
4. **Memoria de preferencias.** Por proyecto (última carpeta de render, último
   preset, nombres de bus usados) y global (voz, modelo, micrófono).
5. **Actualizaciones.** Feed JSON firmado, canal `stable` y `beta`, verificación
   de hash, y rollback si la versión nueva no arranca.
6. **Documentación de usuario.** Una página de «qué pedirle» con ejemplos por
   tarea, y un video de dos minutos que muestre el flujo completo.
7. **Robustez.** Reintento cuando el puente se cae, mensaje claro cuando REAPER
   está en un diálogo modal, y desconexión limpia sin perder el pedido.

### Riesgos

- **Licencias.** Resuelto: Miky es **GPL-3.0** (software libre, repo público), así que
  edge-tts y Piper son compatibles. Sólo hay que citar los componentes en [NOTICE.md](../NOTICE.md).
- **Cuota real con usuarios.** Un usuario intensivo puede pasar los 100 pedidos
  diarios. Hay que mostrar el consumo y ofrecer su propia API key.
- **Soporte multi-versión.** REAPER 7.5, 7.84 y 8.0 pueden comportarse distinto.
  Mantener una matriz de pruebas mínima.
- **Tamaño y arranque.** PySide6 + Whisper + assets pesa. Objetivo: instalador
  por debajo de ~200 MB y arranque < 3 s en un equipo con disco mecánico.

### Criterio de terminado

10 usuarios externos instalan sin ayuda; 8 de 10 completan el onboarding sin
abrir un issue; menos del 5% de los comandos falla por causas del producto (no
del usuario); el update automático llega y se aplica sin intervención.

---

## Versión 2 — contexto y multi-DAW

**Objetivo:** que Miky opine como ingeniero, no solo que obedezca.

### Entregables

1. **Diagnóstico de sesión.** «Revisá la sesión» devuelve una lista corta:
   pistas sin nombre, plugins en bypass, pistas armadas sin monitoreo, folders
   mal cerrados, sample rate distinto entre el proyecto y los archivos, picos
   por encima de 0 dBFS.
2. **Medidores y loudness.** `Track_GetPeakInfo`, `CalculateNormalization` y
   `RENDER_STATS` para responder «¿qué pista está saturando?» o «¿cuánto mide la
   mezcla?». Esto tiene que correr **fuera del tick** (proceso aparte o
   `AudioAccessor`) para no congelar REAPER.
3. **Mezcla de auriculares.** Bus de control room, sends y mute del master en un
   solo comando.
4. **Multi-DAW.** La arquitectura ya separa `BridgeClient` (protocolo),
   `reaper.py` (sistema operativo y REAPER) y `catalog.py` (superficie de
   comandos). Un DAW nuevo = un adaptador de puente + un catálogo. La voz, la IA
   y la UI no se tocan. **No prometer paridad**: cada DAW tiene su modelo de
   objetos y algunos no tienen API scriptable.
5. **Multi-instancia.** Ya existe `MIKY_IPC_ROOT` para aislar el canal; falta la
   UI para elegir a qué instancia hablar.
6. **Undo por plan.** Un solo bloque de undo para todo el plan, y un comando
   «deshacé lo que hizo Miky» que borre las últimas N entradas.

### Riesgos

- El diagnóstico puede ser ruidoso: si grita «clipping» en cada sesión, el
  usuario lo apaga y no vuelve.
- Medir loudness en tiempo real compite por CPU con la grabación.
- Multi-DAW puede comerse el roadmap entero: se hace con un solo DAW aliado
  primero y se decide después.

### Criterio de terminado

Tres diagnósticos que el usuario acepte como correctos en 4 de 5 sesiones; un
segundo DAW con 20 comandos funcionando; «deshacé lo que hizo Miky» revierte un
plan completo en un paso.

---

## Riesgos abiertos

| Riesgo | Qué puede pasar | Mitigación hoy | Qué falta |
|---|---|---|---|
| **Cuota de Gemini** | El free tier corta a mitad de sesión. Según el informe, `3.5-flash-lite` tiene ~500 pedidos/día y `3.8-flash` ~20 (fuente terciaria, verificar en AI Studio) | router directo (0 requests), planes multi-paso, mensaje claro cuando hay 429 | cachear interpretaciones idénticas, mostrar consumo, y que `doctor` chequee la cuota |
| **Latencia** | El pedido tarda y el usuario repite o se frustra | mediana de 31–47 ms en el puente, planes de una sola consulta | objetivo 0.2: p95 < 2,5 s de punta a punta; medir STT + red + ejecución por separado |
| **Precisión del STT con ruido de estudio** | Con monitoreo abierto, batería o bleed, el texto sale mal y el comando también | VAD Silero, palabra clave, confirmación en acciones destructivas | pruebas con ruido real, `small` como opción, y micrófono distinto al de REAPER |
| **Conflicto de audio con ASIO** | «No me escucha»: el asistente no puede abrir el dispositivo que REAPER tomó en exclusiva | por diseño usa otro dispositivo (WASAPI, micrófono interno) y lo explica en `doctor` | detectar el conflicto automáticamente y ofrecer cambiar de micrófono en el momento |
| **Licencias de voces y modelos** | Algunos modelos de wake word no son comerciales | el producto es GPL-3.0, así que edge-tts (GPL) y Piper son compatibles; Whisper es MIT | documentar cada componente en [NOTICE.md](../NOTICE.md) y evitar modelos no comerciales |
| **Privacidad** | El free tier de Gemini usa los prompts para entrenar; pueden ir nombres de clientes o de proyectos | aviso en la doc; la API key es del usuario | modo «solo router» visible en la UI y aviso en el onboarding |

---

## Backlog priorizado

Estimación gruesa en días de una persona. «Etapa» indica dónde entra.

### P0 — sin esto no hay uso diario

| Ítem | Etapa | Días |
|---|---|---|
| Memoria corta de conversación + `ai.recovery` | 0.2 | 3 |
| Sends, ruteo y bus | 0.2 | 3 |
| Folders y grupos | 0.2 | 2 |
| Items y edición básica | 0.2 | 4 |
| Compás y marcadores de tempo | 0.2 | 2 |
| Voz: A/B medido + prompt con nombres de pista | 0.2 | 3 |
| Instalador PyInstaller + Inno Setup | 0.2 | 4 |
| Firma Authenticode | 0.2 | 1 |
| `bridge.log` + `doctor` extendido | 0.2 | 1 |
| Outlier de `transport.stop` post-grabación | 0.2 | 1 |
| **Total P0** | | **24** |

### P1 — lo que convierte la beta en producto

| Ítem | Etapa | Días |
|---|---|---|
| Automatización | 0.2 → 1.0 | 4 |
| Presets de sesión | 1.0 | 3 |
| Onboarding asistido | 1.0 | 3 |
| Auto-update con feed firmado | 1.0 | 3 |
| Memoria de preferencias | 1.0 | 2 |
| Undo por plan + «deshacé lo de Miky» | 1.0 | 2 |
| Telemetría opt-in (solo errores) | 1.0 | 2 |
| Documentación de usuario + video | 1.0 | 1 |
| **Total P1** | | **20** |

### P2 — lo que lo vuelve distinto

| Ítem | Etapa | Días |
|---|---|---|
| Diagnóstico de sesión | 2.0 | 5 |
| Medidores y loudness fuera del tick | 2.0 | 3 |
| Mezcla de auriculares | 2.0 | 2 |
| Multi-DAW (segundo DAW, 20 comandos) | 2.0 | 10 |
| Multi-instancia en la UI | 2.0 | 2 |
| Comandos por lote («esto en las 4 seleccionadas») | 2.0 | 2 |
| LLM local (Ollama) probado y documentado | 2.0 | 2 |
| **Total P2** | | **26** |

Total de la hoja: **70 días** de trabajo, sin contar investigación ni pruebas en
máquina real.

---

## Lo que no está en el roadmap (a propósito)

- **Edición de audio muestra por muestra.** Miky no es un editor: usa los items y
  las acciones de REAPER.
- **Controlar plugins por su interfaz gráfica.** ReaScript no puede; se hace por
  parámetros y nada más.
- **Un chatbot general.** Si el pedido no es de la sesión, Miky lo dice y no
  inventa.
- **Grabar o procesar audio en la nube.** La voz es local, el audio no sale de la
  máquina.
- **Sincronización entre computadoras.** No hay cuentas ni servidor propio; la
  configuración es local.
