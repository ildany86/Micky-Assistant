# Referencias de REAPER y decisiones de plataforma

Este documento es la memoria técnica de la plataforma: qué leímos, qué
verificamos contra el REAPER real y qué decidimos a partir de eso. Está pensado
para quien tenga que tocar el puente ReaScript, sumar comandos o portar Miky a
otra versión de REAPER.

No es un tutorial de ReaScript ni un changelog: es el conjunto de hechos que, si
se ignoran, hacen que el puente falle de formas difíciles de diagnosticar.

Última verificación: **6 de noviembre de 2026**, sobre **REAPER 7.84/x64**
(Lua 5.4) en Windows 11 build 26300.

---

## 1. Enlaces oficiales

| Qué | Dónde | Para qué lo usamos |
|---|---|---|
| Sitio de REAPER | <https://www.reaper.fm/> | versión vigente, notas de release, licencia |
| Descarga | <https://www.reaper.fm/download.php> | bajar la misma versión contra la que se verificó todo |
| Documentación de ReaScript | <https://www.reaper.fm/sdk/reascript/reascripthelp.html> | la referencia de la API: firmas C/Lua/Python/EEL y descripción de cada parámetro |
| SDK y headers | <https://github.com/justinfrankel/reaper-sdk> | `reaper_plugin.h` y `reaper_plugin_functions.h`: la verdad de los tipos cuando la doc resume de más |
| Foro oficial (Cockos) | <https://forum.cockos.com/> | dudas de comportamiento raro, hilos de ReaScript y de extensiones |
| Foro: hilo de ReaPack | <https://forum.cockos.com/showthread.php?t=177978> | soporte del gestor de paquetes (solo si algún día lo usamos) |

Dos aclaraciones que ahorran tiempo:

- La página `reascripthelp.html` del sitio apunta **siempre a la última versión**.
  Para la versión instalada, la copia fiel es la que genera REAPER en
  *Help → ReaScript documentation*; en el repo está guardada como
  `research/reascripthelp.html` y es la que se usó para todo este documento.
- El header `reaper_plugin_functions.h` (641 KB) es más confiable que la doc para
  **tipos y rangos**, y menos confiable para **semántica**: los comentarios de la
  doc explican qué significa cada bit, el header solo declara la firma.

---

## 2. El ecosistema no oficial

### 2.1 ReaPack

**Qué es.** El gestor de paquetes de REAPER, de Christian Fillion (cfillion).
Indexa repositorios de scripts y extensiones, instala, actualiza y permite fijar
versiones. Hoy va por la **v1.2.6** (septiembre de 2025).

**Cómo se instala.** Se baja el DLL de la arquitectura correcta (no la del
sistema operativo: la de REAPER) y se copia en la carpeta de recursos, subcarpeta
`UserPlugins`; se reinicia REAPER y aparece el menú *Extensions → ReaPack*.
Después se administran repositorios desde *Manage repositories*.

**Por qué NO es una dependencia de Miky.**

1. Obligaría a un paso manual de instalación antes de que Miky sirva. El puente
   tiene que arrancar solo desde `__startup.lua`, sin que el usuario instale
   nada más.
2. Es un binario de terceros que hay que mantener actualizado y que puede
   cambiar de comportamiento entre versiones.
3. Importar repositorios remotos es una superficie de confianza que no
   controlamos: un paquete ajeno puede ejecutar código en la sesión.
4. No lo necesitamos: el puente es un archivo `.lua` con JSON propio, IPC propio
   y registro de comandos propio. Cero librerías.

**Cuándo lo revisitaríamos.** Si quisiéramos distribuir los comandos de Miky como
paquete instalable desde ReaPack, o si algún día la interfaz viviera dentro de
REAPER. Hoy ninguna de las dos cosas está en el plan.

### 2.2 La documentación de X-Raym

**Qué es.** Un render navegable de la misma API, con filtros por lenguaje
(C++, EEL2, Lua, Python): <https://www.extremraym.com/cloud/reascript-doc/>.

**Qué aporta de más.** Además de la API nativa, incluye las funciones de las
extensiones más usadas (SWS `CF_*`, ReaImGui `ImGui_*`, FNG, GU, Fab). Cuando
buscás algo y en la doc oficial no aparece, muchas veces está ahí porque es de
una extensión, no del core.

**Por qué no es dependencia.** Es documentación, no código: se consulta y se
cierra. Sirve como segunda opinión cuando la doc oficial es ambigua.

### 2.3 REAPER Blog

**Qué es.** El blog de Jon Tidey (<https://reaperblog.net/>): tutoriales, videos y
artículos de flujo de trabajo.

**Qué aporta.** No es documentación de API: es uso real del programa. Sirve para
entender convenciones (cómo se nombran las pistas en sesiones reales, qué
acciones usa la gente, cómo se arma una sesión de batería) y para escribir
mejores prompts y mejores presets.

**Por qué no es dependencia.** Es material de lectura, no un artefacto que el
producto consuma.

### 2.4 SWS / S&M

**Qué es.** La extensión C++ más difundida de REAPER
(<https://sws-extension.org/>): agrega cientos de acciones y funciones
(`CF_*`, `SNM_*`, `BR_*`, etc.).

**Qué aportaría.** Algunas cosas que el core no tiene: gestión de cadenas de FX,
utilidades de items, funciones de proyecto.

**Por qué no lo usamos.**

- Duplica cosas que ya resolvemos con la API nativa y con acciones nativas
  (que además son más estables entre versiones que las de una extensión).
- Agrega una dependencia binaria más a la instalación.
- Sus acciones y funciones están **en inglés**, incluso en un REAPER en
  español. Eso rompe la promesa de que todo lo que Miky reporta se entienda en
  el idioma del usuario.
- Nuestro puente tiene que funcionar en un REAPER recién instalado. SWS no viene
  con REAPER.

### 2.5 ReaImGui

**Qué es.** El binding de Dear ImGui para ReaScript (`ImGui_*`), también de
cfillion. El repositorio vive hoy en Codeberg:
<https://codeberg.org/cfillion/reaimgui> (el de GitHub redirige allí).

**Qué aportaría.** Si algún día quisiéramos una ventana de estado o un panel de
configuración **dentro de REAPER**, es el camino: widgets reales desde Lua.

**Por qué no lo usamos.** La interfaz de Miky vive fuera de REAPER, en Qt. Sumar
ReaImGui sería una segunda tecnología de UI, con su propio ciclo de versiones,
para un problema que ya está resuelto. Se revisa solo si aparece un requisito de
"panel adentro de REAPER".

### 2.6 Por qué el puente es autónomo

El puente es **un solo archivo** de ~2.640 líneas y ~86 KB que se copia a
`%APPDATA%\REAPER\Scripts\Miky\miky_bridge.lua`, con estas piezas escritas a mano:

| Pieza | Archivo fuente | Por qué propia |
|---|---|---|
| JSON (encode/decode) | `reaper/src/miky/json.lua` | no hay librería en REAPER y no queremos vendorizar una |
| IPC por archivos | `reaper/src/miky/ipc.lua` | no hay sockets ni HTTP |
| Registro de comandos | `reaper/src/miky/registry.lua` | catálogo cerrado, sin `load()` de código externo |
| Resolución de pistas/FX | `reaper/src/miky/state.lua` | reglas del producto (nombre, número, selección) |

El resultado: se instala copiando un archivo y agregando un bloque a
`__startup.lua`. No se rompe cuando el usuario actualiza SWS o ReaPack, y el
soporte se reduce a "mandame el log". El costo —reimplementar JSON y una cola—
ya está pago.

---

## 3. Entorno verificado

Datos medidos en la máquina de desarrollo, no estimados:

| Ítem | Valor |
|---|---|
| REAPER | 7.84/x64 |
| Intérprete | Lua 5.4 embebido |
| Ejecutable | `C:\Program Files\REAPER (x64)\reaper.exe` |
| Carpeta de recursos | `C:\Users\Dani Lugo\AppData\Roaming\REAPER` |
| Acciones disponibles | 6.853 (`kbd_enumerateActions`) |
| SO | Windows 11 Pro, build 26300 |
| CPU / RAM | Intel i7-8665U (4c/8t) / 15,8 GB |
| Python del proyecto | 3.12 (venv) |

Lo que el intérprete **sí** tiene: `io.open`, `io.write`, `io.popen`,
`os.remove`, `os.rename`, `os.execute`, `os.date`, `os.getenv`, `string.pack`,
`math.type`, `utf8`.

Lo que **no** tiene y conviene recordar: `io.seek` y `os.exit` son `nil`. Sin
`seek` no se puede leer un archivo por partes ni saber su tamaño sin leerlo
entero; el puente lee con `'*a'` y corta por tamaño máximo antes de decodificar.

---

## 4. Hechos que condicionan el diseño

### 4.1 `defer` corre cada ~31 ms y bloquea el hilo principal

Medido con tres modos de trabajo, 60 ticks cada uno:

| Modo | Intervalo medio | Mediana | Mín. | Máx. |
|---|---|---|---|---|
| con IO por tick | 32,41 ms | 31,21 ms | 9,51 ms | 145,74 ms |
| sin IO | 31,25 ms | 31,21 ms | 30,15 ms | 32,30 ms |
| sin IO, más liviano | 31,24 ms | 31,19 ms | 16,29 ms | 46,61 ms |

Y en reposo, con la interfaz de REAPER ocupada, aparecieron picos de **838 ms**:
`defer` no es un timer de tiempo real, es "lo antes posible después de que el
hilo principal quede libre".

Consecuencias directas:

1. **La latencia mínima de un comando es un tick.** Con un pedido por tick y una
   escritura de respuesta, el piso está en ~31–60 ms. No hay forma de bajarlo sin
   romper el modelo.
2. **No hay hilos.** Todo lo que ejecute el puente bloquea la interfaz de REAPER.
   Por eso cada tick hace trabajo acotado (máximo 8 pedidos, máximo 32 pasos por
   pedido) y nunca espera nada.
3. **`defer` no se reprograma si el callback tira error.** Todo el tick va dentro
   de `pcall`; un error no puede dejar a REAPER sin puente hasta reiniciarlo.
4. **El latido va cada 15 ticks** (~0,5 s) y la app lo considera vencido a los
   3,5 s. Es la única señal de vida que tiene el lado Python.

### 4.2 El IPC por archivos: números y trampas

No hay cliente HTTP ni sockets en ReaScript, así que el canal es una carpeta:
`requests/`, `responses/` y `status.json` dentro de `%APPDATA%\Miky\ipc`
(override por `MIKY_IPC_ROOT`, útil para tests o para una segunda instancia de
REAPER).

Costos medidos por operación:

| Operación | Costo |
|---|---|
| `open` + `write` + `close` de un JSON chico | 0,877 ms |
| escritura con buffer + `flush` | 0,124 ms |
| escritura con buffer, sin flush por op | 0,026 ms |
| primera medición, durante reproducción con UI activa | ~4,16 ms |

Aun con el peor número, un pedido completo (escribir request + leer response)
cuesta menos de 10 ms: un tercio del tick. No es el cuello de botella.

Trampas verificadas, todas con test o medición:

- **`EnumerateFiles` cachea el listado del directorio.** Un archivo nuevo no
  aparece hasta llamarlo con índice `-1`. El puente lo hace en cada tick; sin
  eso, los pedidos se quedan en la carpeta para siempre.
- **`os.rename` no sobrescribe en Windows.** Si el destino existe, falla con
  "No such file or directory". Para escribir `status.json` hay que borrar el
  destino y renombrar.
- **`os.remove` falla con "Permission denied" si quedó un handle abierto.**
  Cerrar siempre antes de borrar; el pedido se borra después de responder, no
  antes.
- **Unicode funciona.** Se probó con `uni_ñandú_áéíóú_测试.txt`: `io.open` y
  `EnumerateFiles` lo manejan bien, incluido el nombre exacto.
- **El lado Python escribe atómico** (`os.replace` sobre un `.tmp`): el puente
  nunca ve un JSON a medio escribir.
- **El lado Python limpia** pedidos y respuestas con más de 60 s al arrancar.

### 4.3 El render es sincrónico

`Main_OnCommand(42230, 0)` **no vuelve hasta que el archivo está escrito**.
Medido con un proyecto de 2 s de audio:

| Acción | Tiempo de retorno | Archivo resultante |
|---|---|---|
| 42230 (render + cerrar diálogo) | 0,63 s | 529.890 bytes |
| 41824 (render con últimos ajustes) | 0,60 s | 265.290 bytes |

Por eso el handler de render está marcado como lento: antes de ejecutar escribe
`status.json` con `busy: true`, y al terminar lo vuelve a escribir. La app, del
lado Python, tiene timeout de 30 minutos para `render.*` y muestra "renderizando"
mientras el latido diga `busy`.

No se usa la acción 40015 ("Renderizar Proyecto en el disco…") porque abre el
diálogo y necesita que alguien apriete un botón. 42230 es la única forma de
renderizar sin intervención y sin dejar una ventana colgada.

### 4.4 IDs de acción verificados

Los nombres están tal como los devuelve la instalación **en español**
(`kbd_getTextFromCmd`). El ID es el mismo en cualquier idioma.

| ID | Nombre en esta instalación | Uso |
|---|---|---|
| 1007 | Transporte: Reproducir | `transport.play` |
| 1008 | Transporte: Pausa | `transport.pause` |
| 1013 | Transporte: Grabar | `transport.record` |
| 1016 | Transporte: Parar | `transport.stop` |
| 1068 | Transporte: Repetir (Activar/Desactivar) | `transport.set_loop` |
| 40364 | Opciones: Metrónomo (Activar/Desactivar) | `project.set_metronome` |
| 40029 | Editar: Deshacer | `project.undo` |
| 40030 | Editar: Rehacer | `project.redo` |
| 40062 | Pista: Duplicar pistas | respaldo de `track.duplicate` |
| 40297 | Pista: Deseleccionar todas las pistas | `track.select` (sin `add`) |
| 42230 | Archivo: Renderizar el proyecto usando los últimos ajustes y cerrar el diálogo al Terminar | `render.start` |
| 41824 | Archivo: Renderizar Proyecto, Usando los últimos ajustes de renderizado | verificado, sin uso |
| 40001 | Pista: Insertar pista | verificado, sin uso |
| 40005 | Pista: Eliminar pistas | verificado, sin uso |
| 40026 | Archivo: Guardar proyecto | verificado, sin uso |
| 40004 | Archivo: Salir de REAPER | solo test (`app.quit`) |

Los cuatro "sin uso" están verificados a propósito: son el plan B si alguna
función de API cambia. `40001` y `40005` no se usan porque
`InsertTrackInProject` y `DeleteTrack` son más precisos (no dependen de la
selección ni del foco). `40026` no se usa porque `Main_SaveProject` distingue
"nunca guardado" de "guardado" y permite devolver un error útil.

### 4.5 `GetPlayState` es un bitfield

```
&1 = reproduciendo      &2 = pausado      &4 = grabando
```

Verificado: `state = 1` durante reproducción, `state = 0` detenido. Se consulta
antes de actuar para no mandar "play" si ya está sonando, y para no mandar
"record" si ya está grabando. Nunca se compara contra un valor exacto: siempre
con los bits.

### 4.6 Pistas: los parámetros que importan

**`I_RECINPUT`** (entrada de grabación). La doc lo define así (traducido y
abreviado):

> `<0` = sin entrada. Si `4096` está seteado, la entrada es MIDI y los 5 bits
> bajos son el canal (`0` = todos, `1–16` = solo ese), los siguientes 6 bits son
> la entrada física (`63` = todas, `62` = teclado virtual). Si `4096` no está
> seteado, los 10 bits bajos (`0..1023`) son el canal de entrada (ReaRoute y
> Loopback arrancan en `512`). Si `2048` está seteado, es entrada multicanal; si
> `1024` está seteado, es entrada estéreo.

Traducido a lo que usa el puente:

| Pedido | Valor |
|---|---|
| `none` | `-1` |
| `mono:1` / `mono:2` | `0` / `1` (¡el canal es 0-based!) |
| `stereo:1` | `1024 + 0` |
| `midi` (todos los canales, todos los dispositivos) | `4096 + (63 << 5)` |
| `midi:ch1` | `4096 + (63 << 5) + 1` |
| `midi:2` (dispositivo 2, todos los canales) | `4096 + (2 << 5)` |

El error clásico es asumir canales 1-based: `mono:1` es `0`, no `1`.

**`I_FOLDERDEPTH`**: `0` = normal, `1` = la pista es padre de folder, `-1` = es
la última del folder más interno, `-2` = última del más interno y del siguiente,
etc. El puente **lee** este valor en el snapshot y todavía no lo escribe: crear
folders es trabajo de la 0.2.

**`I_RECMON`**: `0` = off, `1` = normal, `2` = tape (solo cuando no reproduce).

**`I_SOLO`**: `0` sin solo, `1` solo, `2` solo in place, `5` safe solo, `6` safe
solo in place. El puente lo reduce a booleano (`!= 0`) en el snapshot y en el
comando; el modo fino (solo in place, safe solo) se pierde, y togglear un `2` lo
deja en `1`. Es una limitación aceptada de la beta, no un bug.

**`D_VOL`**: es ganancia lineal, no dB. `0` = −inf, `0.5` = −6 dB, `1` = 0 dB,
`2` = +6 dB. Conversión: `vol = 10^(dB/20)` y `dB = 20·log10(vol)`. El puente
clampea a `−150 dB` (que manda a `0`) y a `+24 dB`.

**`I_CUSTOMCOLOR`**: el color del sistema con el bit `0x1000000` prendido
(`ColorToNative(r,g,b) | 0x1000000`). Sin ese bit el color se guarda pero no se
usa. Verificado: `ColorToNative(255,0,0)` devuelve `255` y `GetTrackColor` después
de `SetTrackColor` devuelve `16777471` = `0x10000FF`, o sea el rojo con el bit.
`GetTrackColor` devuelve `0` si no hay color y `0x1000000` si el color es negro.

### 4.7 FX: el orden de parámetros de `TrackFX_AddByName`

La firma real es:

```lua
integer reaper.TrackFX_AddByName(MediaTrack track, string fxname, boolean recFX, integer instantiate)
```

`recFX` va **tercero** e `instantiate` **cuarto**. Es el error más común al
copiar ejemplos de internet, porque muchas veces aparece como
`AddByName(track, name, instantiate, recFX)`. Si se invierte, el FX se agrega al
chain equivocado o no se agrega.

Semántica de `instantiate`:

| Valor | Qué hace |
|---|---|
| `< 0` | siempre crea una instancia nueva |
| `0` | solo consulta: devuelve el índice de la primera instancia o `-1` |
| `> 0` | agrega una instancia si no existe |
| `<= -1000` | codifica la **posición de inserción**: `-1000` = primero de la cadena, `-1001` = segundo, etc. |

Si el retorno es negativo, el FX no existe o no se pudo cargar: el puente lo
convierte en un error con el nombre de la pista y una sugerencia de cómo se llama
el plugin en REAPER.

`fxname` acepta prefijos de tipo: `VST3:`, `VST2:`, `VST:`, `JS:`, `AU:`, `DX:`,
o `FXADD:` (agrega lo que esté seleccionado en el explorador de FX abierto).

Para parámetros:

- `TrackFX_GetNumParams` / `TrackFX_GetParamName`: enumerar y buscar por nombre.
- `TrackFX_SetParam` usa la **escala real** (dB, Hz, ratio).
- `TrackFX_SetParamNormalized` usa **0..1** sobre el rango completo.
- `TrackFX_GetFormattedParamValue` devuelve el texto que muestra REAPER
  ("−18.0 dB"): es lo que se usa para confirmar por voz lo que quedó.

Índices especiales: `+0x1000000` direcciona el FX de entrada de la pista (o el
de salida de hardware en el master) y `+0x2000000` direcciona FX dentro de
containers. El puente todavía no los usa; el snapshot devuelve solo el chain
normal.

### 4.8 Render: `RENDER_FORMAT` y el resto de los parámetros

**`RENDER_FORMAT`** acepta un FourCC de 4 bytes **sin base64**. Para WAV es
`"evaw"` (el código se guarda invertido respecto de "wave"), con los ajustes por
defecto del formato. La doc lo dice explícitamente y da `"evaw"` y `"l3pm"` como
ejemplos. Verificado: el valor por defecto leído con `GetSetProjectInfo_String`
es base64 `ZXZhdxgAAQ==`, que decodifica a `evaw` + 3 bytes de configuración
(`18 00 01`).

Consecuencia: para exportar WAV no hace falta armar el blob base64. Alcanza con
`GetSetProjectInfo_String(0, 'RENDER_FORMAT', 'evaw', true)`.

**Formatos disponibles en esta instalación.** La descripción de `RENDER_FORMAT`
lista `wave`, `aiff`, `caff`. MP3 requiere `lame_enc.dll`; si no está, el formato
no aparece y el render falla. Por eso la 0.1 solo ofrece `wav` y `last`.

**`RENDER_TARGETS`** (solo lectura) devuelve la lista separada por `;` de los
archivos que se escribirían con los ajustes actuales. Verificado: devuelve la
ruta completa **antes** de renderizar y la misma después. Es lo que permite decir
por voz "quedó en *D:\Renders\tema.wav*" sin adivinar.

**El resto de la familia:**

| Parámetro | Tipo | Qué define |
|---|---|---|
| `RENDER_FILE` | string | carpeta de salida |
| `RENDER_PATTERN` | string | nombre del archivo, admite wildcards (`$project`, `$track`) |
| `RENDER_SETTINGS` | bitfield | `0` = master mix; `&1` = stems + master; `&2` = solo stems; `&32` = items seleccionados; `&64` = items vía master; `&128` = pistas seleccionadas vía master; `&512` = metadata; `&2048` = segunda pasada |
| `RENDER_BOUNDSFLAG` | int | `0` = límites propios, `1` = proyecto entero, `2` = selección de tiempo, `3` = todas las regiones, `4` = items seleccionados, `5` = regiones seleccionadas |
| `RENDER_NORMALIZE` | bitfield | `&1` = normalizar; el modo va en `&14` (`0` = LUFS-I, `2` = RMS, `4` = peak, `6` = true peak, `8` = LUFS-M max, `10` = LUFS-S max) |
| `RENDER_NORMALIZE_TARGET` | double | objetivo en **ganancia lineal**: `0.5` = −6,02 dB |
| `RENDER_ADDTOPROJ` | bitfield | `&1` = agregar al proyecto; `&2` = no renderizar archivos que suenan silenciosos |
| `RENDER_STATS` / `RENDER_STATS_SUMMARY` | string | estadísticas del último render; aceptan ejecutar una acción antes de devolverlas (por ejemplo `"42437"` = render en seco) |
| `RENDER_FORMAT2` | string | formato secundario; `""` lo desactiva |

Para normalizar a −14 LUFS: `RENDER_NORMALIZE = 1` y
`RENDER_NORMALIZE_TARGET = 10^(-14/20) = 0,1995`. Ojo: el objetivo es ganancia,
no LUFS; confundirlos hace que el render salga 14 dB bajo.

Sobre `RENDER_ADDTOPROJ`: no hay un valor `0` documentado como "neutro", así que
el puente manda `1` (agregar) o `2` (no agregar, y de paso saltea los silenciosos).

### 4.9 Undo: un bloque por paso

`Undo_BeginBlock()` abre el bloque y `Undo_EndBlock(desc, extraflags)` lo cierra
con una descripción. El puente envuelve **cada paso** del plan en su propio
bloque, con una descripción en español ("Crear pista", "Ajustar volumen de
pista"): es lo que se ve en el historial de undo de REAPER.

Detalles verificados:

- `Undo_CanUndo2(0)` devuelve la descripción de lo último que se puede deshacer
  (en la prueba, "DSH undo test").
- `Undo_GetNumEntries` / `Undo_GetCurEntry` existen y permiten saber cuántos
  pasos hay.
- El bloque se cierra **también cuando el paso falla**: si hubo cambios
  parciales, el usuario tiene que poder deshacerlos. Un bloque abierto para
  siempre desordena el historial.
- Deshacer y rehacer se hacen con las acciones **40029/40030**, no con
  `Undo_DoUndo2`, para que el resultado sea exactamente el mismo que si el
  usuario apretara Ctrl+Z (incluido el refresco de la interfaz).
- Alrededor de la ejecución de todos los pasos: `PreventUIRefresh(1)` …
  `PreventUIRefresh(-1)`, y al final `UpdateArrange()` +
  `TrackList_AdjustWindows(false)`. Un solo refresco en vez de uno por paso.

**Limitación conocida:** un plan de 5 pasos deja 5 entradas de undo. Agrupar todo
el plan en un solo bloque es una mejora pendiente (ver
[roadmap](07-roadmap.md), versión 2).

### 4.10 Nombres de pista

`GetSetMediaTrackInfo_String(tr, 'P_NAME', valor, is_set)`:

```lua
-- leer: devuelve (ok, nombre)
local ok, nombre = reaper.GetSetMediaTrackInfo_String(tr, 'P_NAME', '', false)

-- escribir: el valor va en el tercer argumento
reaper.GetSetMediaTrackInfo_String(tr, 'P_NAME', 'Guitarra', true)
```

En el master, `P_NAME` devuelve vacío (no tiene nombre editable). Otros campos
string útiles: `P_ICON` (ícono de la pista), `P_MCP_LAYOUT`, `P_LANENAME:n`.

**Comparación por nombre.** El STT devuelve "bateria" y la pista se llama
"Batería": comparar bytes no sirve. El puente normaliza (minúsculas, sin acentos,
espacios colapsados) con una tabla de bytes UTF-8 escrita a mano en
`reaper/src/miky/util.lua` (función `U.norm`), sin depender de `utf8` ni del
locale del sistema. Después prueba en este orden: nombre exacto normalizado →
subcadena única → error con la lista de pistas. Nunca "adivina" entre dos
candidatas: si hay ambigüedad, falla y devuelve las opciones.

### 4.11 Acciones: IDs universales, nombres localizados

El ID numérico es universal; el **texto no**. `kbd_getTextFromCmd(id, section)`
devuelve el nombre en el idioma de la instalación:

| ID | Inglés | Español (esta máquina) |
|---|---|---|
| 40062 | Track: Duplicate tracks | Pista: Duplicar pistas |
| 42230 | File: Render project, using the most recent render settings, auto-close render dialog | Archivo: Renderizar el proyecto usando los últimos ajustes y cerrar el diálogo al Terminar |
| 1013 | Transport: Record | Transporte: Grabar |

Eso obliga a dos reglas:

1. **Nunca comparar ni buscar por texto de acción.** Todo va por ID.
2. **El nombre localizado sirve para logs y para `action.info`**, no para decidir
   qué hacer.

Para volcar la lista completa está `kbd_enumerateActions(section, index)` (con
`SectionFromUniqueID` para obtener la sección). De ahí salieron las 6.853
acciones de `research/out/actions.txt`, que es la fuente de los nombres de la
tabla de §4.4.

`NamedCommandLookup` y `ReverseNamedCommandLookup` convierten entre el nombre
simbólico (`_SWS_...`, `_RS...`) y el ID. No se usan: implican depender de
extensiones o de scripts con nombre fijo.

---

## 5. Lo que ReaScript no puede hacer

| Limitación | Qué implica en el diseño |
|---|---|
| **No hay cliente HTTP, WebSocket ni sockets.** | El canal con la app es por archivos. `io.popen` y `os.execute` existen, pero lanzan procesos externos y bloquean el hilo: no se usan. |
| **No hay hilos ni timers propios.** Todo corre en el hilo principal vía `defer`. | Nada de esperas ni de trabajo largo: cada tick hace trabajo acotado; el render se marca como lento y la app espera con timeout largo. |
| **No hay acceso a la interfaz de plugins de terceros.** | Solo se pueden leer y escribir parámetros por índice o nombre, abrir y cerrar la ventana (`TrackFX_SetOpen`) y leer el valor formateado. No se puede "apretar el botón" de un plugin ni parsear su GUI. |
| **No hay acceso a la GUI de REAPER** (menús, diálogos, arrastre) más allá de acciones y algunas funciones de docking. | Se eligen acciones que **no abran diálogos**. Renderizar sin intervención es la 42230, no la 40015. |
| **No hay acceso al historial de undo** más allá de la descripción del último paso y de un contador. | No se puede "volver al estado de hace 10 minutos". El deshacer es lineal. |
| **No hay eventos.** Todo es polling en `defer`. | Latencia mínima de un tick; no se puede reaccionar "al instante" a un cambio de estado. |
| **No hay FFI ni acceso directo a Win32.** `GetMainHwnd()` devuelve el handle, pero no hay con qué usarlo sin una extensión nativa. | No se inyectan teclas ni mouse. La superficie de acción es el catálogo. |
| **`io.seek` y `os.exit` no existen.** | Se lee el archivo entero (con tope de 256 KB). Para cerrar REAPER solo se puede pedir la acción 40004, que es un cierre ordenado; así lo hace `app.quit`, y solo se usa en pruebas. |
| **No hay forma de saber qué "es" un plugin.** Solo nombre, parámetros, rangos y valores formateados. | La IA trabaja con nombres y heurísticas; "cargá un compresor" se resuelve con el nombre que dicta el usuario, no adivinando. |
| **Un error no atrapado en `defer` corta la cadena de ticks.** | Todo va en `pcall`, y el error se escribe en `status.json` para que la app lo muestre. |

---

## 6. Compatibilidad: el REAPER del usuario está en español

El equipo de desarrollo y el usuario final tienen REAPER **en español**. Eso no
cambia la API, pero cambia todo lo que sea texto.

| Qué | ¿Se localiza? | Cómo se maneja |
|---|---|---|
| IDs de acción | No | se usan números, siempre |
| Nombres de acción | **Sí** | solo para logs y `action.info` |
| Nombres de pista, marcador, región | Los pone el usuario | comparación normalizada (sin acentos, minúsculas) |
| Parámetros de pista (`D_VOL`, `I_RECINPUT`…) | No | constantes |
| Nombres de plugin | No | tal como los muestra REAPER |
| Nombres de parámetro de plugin | Depende del plugin | búsqueda por subcadena, con error que lista los disponibles |
| Mensajes de error del puente | Los escribe Miky | en español rioplatense |

Notas prácticas:

- **El dump de acciones del repo está en español.** `research/out/actions.txt`
  tiene los 6.853 nombres en el idioma de la instalación. `actions_en.txt` es una
  **copia idéntica** (mismo hash), no un dump en inglés: no sirve como referencia
  de nombres en inglés.
- **Encoding.** Los archivos se escriben y se leen en UTF-8. En la consola de
  Windows los acentos se ven mal; el contenido está bien. Si un script Lua tiene
  caracteres no ASCII en el código, conviene escribirlos como bytes escapados
  (así está la tabla de acentos de `util.lua`), para no depender de cómo se guardó
  el archivo.
- **Descripciones de undo.** Son lo único que ve el usuario en el historial de
  REAPER, así que van en español y en infinitivo ("Crear pista", "Renderizar").
- **`kbd_getTextFromCmd` en un REAPER en inglés devuelve inglés.** No hay que
  asumir el idioma: si algún día se usa para algo más que logs, hay que tratar el
  texto como opaco.

---

## 7. Cómo verificar un dato de la API

El flujo que se usó para cada hecho de este documento, en orden. Si dudás de un
dato, repetí estos pasos antes de tocar el puente.

### 7.1 Buscar en la documentación de la versión instalada

`research/reascripthelp.html` es la copia local de la doc de 7.84. Cada función
es un ancla:

```powershell
Select-String -Path research\reascripthelp.html -Pattern '<a name="TrackFX_AddByName"'
```

### 7.2 Consultar el JSON parseado

`research/api.json` tiene una entrada por función con las firmas C, Lua, Python y
EEL2, más la descripción completa:

```powershell
# firma Lua + descripción (recortada a 900 caracteres)
.\.venv\Scripts\python.exe research\api_query.py TrackFX_AddByName GetPlayState

# descripción completa, sin recortes
.\.venv\Scripts\python.exe research\api_desc.py GetSetProjectInfo_String

# grep de una línea por función
Select-String -Path research\lua_sigs.txt -Pattern 'TrackFX_'
```

### 7.3 Cuidado con los builtins

`defer`, `atexit`, `get_action_context`, `gmem_*`, `new_array`, `runloop` y
`set_action_options` **no están en `api.json`**: no son funciones de la API C,
son builtins de Lua. Están documentados aparte en `research/lua_builtins.txt`.
Si `api_query.py` responde "NO EXISTE", probá ahí antes de concluir que la
función no existe.

### 7.4 Verificar contra REAPER

La doc puede estar desactualizada o ser ambigua (el caso de `RENDER_FORMAT` es el
ejemplo perfecto: dice "4 bytes" y el valor real es un FourCC invertido). Hay tres
formas de confirmar, de la más rápida a la más completa:

1. **Contra el puente instalado**, sin escribir código:

   ```powershell
   .\.venv\Scripts\python.exe -m miky status
   .\.venv\Scripts\python.exe -m miky send action.info --args '{"id": 42230}'
   .\.venv\Scripts\python.exe -m miky send state.get
   ```

2. **Contra el REAPER simulado**, para la lógica del puente (no para la API
   real): `tests/lua_harness.py` carga `tests/lua/mock_reaper.lua` con `lupa` y
   corre los módulos reales de `reaper/src/`. Sirve para comandos, resolución de
   pistas y protocolo IPC, sin abrir REAPER.

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests\test_lua_bridge.py -q
   ```

3. **Contra el REAPER real**, con un script desechable en `research/out/*.lua`
   que escribe resultados a un `.txt`. Así se generaron `results.txt`,
   `results_b.txt`, `results_c.txt` y `results_d.txt`, que son la evidencia de
   §4.1 a §4.9. Un script así se ejecuta desde *Actions → Show action list → New
   action → Load ReaScript*.

### 7.5 Cuántas funciones hay (y por qué el número engaña)

`research/api.json` tiene **732** funciones. La doc HTML de 7.84 tiene **878**
anclas `<a name="...">`: las 146 que sobran son builtins de EEL2, con prefijo
`eel_` (`eel_defer`, `eel_gfx_*`, `eel_fft_*`…). El parser (`parse_api.py`)
descarta esas y se queda con las que tienen firma `reaper.*`.

Si en algún apunte aparece "792 funciones", no cierra ni con el HTML ni con el
parser: el número correcto para esta versión es 732, y el diff entre anclas y
JSON da exactamente las 146 de EEL2.

---

## 8. Checklist para actualizar REAPER

Cuando salga 7.9x u 8.0:

1. Instalar la versión nueva y **regenerar la doc**: *Help → ReaScript
   documentation*, guardar como `research/reascripthelp.html`.
2. Regenerar el JSON: `.\.venv\Scripts\python.exe research\parse_api.py`
   (reescribe `api.json` y avisa cuántas funciones encontró).
3. Volcar las acciones de nuevo (`kbd_enumerateActions`) y diffear contra
   `research/out/actions.txt` los IDs que usa el puente.
4. Correr `pytest` completo y `tools\build_lua.py --check`.
5. Re-verificar los cuatro puntos que más duelen si cambian:
   - intervalo de `defer` (~31 ms),
   - `RENDER_TARGETS` antes del render,
   - `42230` sincrónico (¿sigue bloqueando hasta terminar?),
   - orden de parámetros de `TrackFX_AddByName`.
6. Actualizar la tabla de §3 (versión, rutas, cantidad de acciones) y la fecha
   de este documento.

Si algo de eso cambia, el resto de este documento sigue siendo válido como
historia, pero deja de ser la verdad de la plataforma.
