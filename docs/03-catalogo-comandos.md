# Catálogo de comandos

> Documento generado desde `src/miky/data/commands.json` con `python tools/gen_catalog_doc.py`.
> No editar a mano: los cambios van en el JSON y se vuelve a generar.

La beta expone **55 comandos**. Este es el universo cerrado de cosas que Miky
puede hacerle a REAPER. La IA elige entre estos comandos y nada más: no puede ejecutar
código ni inventar operaciones.

## Cómo se leen las fichas

- **id**: identificador interno (el que usa el motor y el puente Lua).
- **Parámetros**: lo que acepta el comando. Los marcados con \* son obligatorios.
- **Pide confirmación**: acciones que no se deshacen con Ctrl+Z (o que escriben archivos).
- **Respuesta hablada**: plantilla de lo que dice Miky al terminar.

Los índices de pista y de plugin son **1-based** (la primera pista es la 1). Una pista se
puede indicar por número (`"2"`) o por nombre (`"Guitarra"`); si se omite, se usa la pista
seleccionada en REAPER.

## Resumen

| Categoría | Comandos |
|---|---|
| Pistas | 17 |
| Plugins y procesamiento | 10 |
| Transporte | 9 |
| Proyecto | 6 |
| Marcadores y regiones | 2 |
| Renderizado | 1 |
| Vista de REAPER | 2 |
| Ruteo y envíos | 5 |
| Edición de items | 3 |

## Pistas

### `track.add`

Crea una pista nueva en el proyecto.

**Parámetros**

- `name` (texto): Nombre de la pista nueva, por ejemplo "Guitarra" o "Batería". \*
- `index` (entero) de 1 a 512: Posición donde insertarla (1 = arriba de todo). Si se omite, va al final.
- `color` (texto): Color de la pista: rojo, naranja, amarillo, verde, celeste, azul, violeta, rosa, gris o "#RRGGBB".
- `arm` (verdadero/falso): Si es true, la deja armada para grabar.

Dice: «Listo, creé la pista {name}.»
Ejemplos: «creá una pista que se llame Guitarra» · «agregá una pista de batería al final»

### `track.add_many`

Crea varias pistas de una sola vez (mejor que llamar varias veces a track.add).

**Parámetros**

- `names` (lista) lista de texto: Lista de nombres, en el orden en que se crean.
- `count` (entero) de 1 a 64: Cantidad de pistas sin nombre a crear. Usar solo si no se dan nombres.

Dice: «Listo, creé {count} pistas.»
Ejemplos: «creá cuatro pistas de batería: bombo, redo, hi-hat y overheads»

### `track.rename`

Le cambia el nombre a una pista existente.

**Parámetros**

- `track` (texto): Pista destino: nombre ("Guitarra") o número ("2"). Vacío = la pista seleccionada. \*
- `name` (texto): Nombre nuevo. \*

Dice: «Renombré la pista a {name}.»
Ejemplos: «renombrá la pista 2 como Voz principal»

### `track.delete`

Elimina una pista y todo su contenido. Pide confirmación al usuario.

**Parámetros**

- `track` (texto): Pista a eliminar: nombre o número. Vacío = la pista seleccionada. \*

**Pide confirmación antes de ejecutar.**
Dice: «Eliminé la pista {deleted_name}.»
Ejemplos: «borrá la pista de prueba»

### `track.duplicate`

Duplica una pista completa (con sus plugins y contenido) justo debajo.

**Parámetros**

- `track` (texto): Pista a duplicar: nombre o número. \*

Dice: «Dupliqué la pista.»
Ejemplos: «duplicá la pista de voz»

### `track.set_volume`

Pone el volumen de una pista en un valor absoluto en dB.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `db` (número) de -150 a 24: Volumen en dB. 0 = sin cambios, -6 = la mitad, -infinito se aproxima con -150. \*

Dice: «Puse {name} en {volume_db} dB.»
Ejemplos: «poné la guitarra en -6 dB»

### `track.adjust_volume`

Sube o baja el volumen de una pista una cantidad de dB respecto de donde está.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `delta_db` (número) de -60 a 60: Cuántos dB sumar (positivo) o restar (negativo). Ej: 2 para subir 2 dB, -3 para bajar 3 dB. \*

Dice: «{name} quedó en {volume_db} dB.»
Ejemplos: «subí la guitarra 2 dB» · «bajá la voz 3 dB»

### `track.set_pan`

Panea una pista a izquierda o derecha.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `pan` (número) de -100 a 100: De -100 (izquierda) a 100 (derecha). 0 = centro. \*

Dice: «Paneé {name} al {pan}.»
Ejemplos: «paneá la guitarra a la izquierda» · «poné el bajo al centro»

### `track.mute`

Silencia o desilencia una pista.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `state` (verdadero/falso): true = silenciar, false = desilenciar. Si se omite, invierte el estado actual.

Dice: «Listo, cambié el mute de {name}.»
Ejemplos: «silenciá el bajo» · «desilenciá la voz»

### `track.solo`

Activa o desactiva el solo de una pista.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `state` (verdadero/falso): true = solo, false = sacar solo. Si se omite, invierte.

Dice: «Listo, cambié el solo de {name}.»
Ejemplos: «hacé solo en la batería» · «sacá todos los solos»

### `track.arm`

Arma o desarma una pista para grabar.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `state` (verdadero/falso): true = armar, false = desarmar. Si se omite, invierte.

Dice: «Listo, cambié el armado de {name}.»
Ejemplos: «armá la guitarra para grabar»

### `track.select`

Selecciona una o varias pistas en REAPER.

**Parámetros**

- `track` (texto): Una pista por nombre o número.
- `tracks` (lista) lista de texto: Varias pistas por nombre o número.
- `add` (verdadero/falso): Si es true, suma a la selección actual en vez de reemplazarla.

Dice: «Seleccioné las pistas.»
Ejemplos: «seleccioná todas las pistas de batería»

### `track.set_color`

Le pone color a una pista.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `color` (texto): rojo, naranja, amarillo, verde, celeste, azul, violeta, rosa, gris o "#RRGGBB". \*

Dice: «Pinté {name}.»
Ejemplos: «pintá la batería de rojo»

### `track.move`

Mueve una pista a otra posición de la lista.

**Parámetros**

- `track` (texto): Pista a mover: nombre o número. \*
- `to_index` (entero) de 1 a 512: Posición final, 1 = arriba de todo. \*

Dice: «Moví {name} a la posición {index}.»
Ejemplos: «mové la guitarra arriba de la batería»

### `track.set_monitor`

Configura el monitoreo de entrada de una pista.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `mode` (texto) valores: `off`, `normal`, `tape`: off = sin monitoreo, normal = siempre, tape = solo cuando no está reproduciendo. \*

Dice: «Monitoreo de {name} en {mode}.»
Ejemplos: «desactivá el monitoreo de esta pista»

### `track.set_input`

Elige la entrada de grabación de una pista.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `input` (texto): none (sin entrada), mono:1, mono:2, stereo:1, stereo:2, midi, midi:ch1..16 o midi:N (dispositivo). \*

Dice: «Entrada de {name} en {input}.»
Ejemplos: «poné la entrada de la guitarra en mono 1»

### `track.add_like`

Crea una pista nueva copiando la configuración de otra: entrada, monitoreo, armado, nivel, paneo, color y toda la cadena de plugins (sin copiar el audio grabado).

**Parámetros**

- `track` (texto): Pista modelo: nombre o número (por ejemplo "Guitarra"). \*
- `name` (texto): Nombre de la pista nueva. Si se omite, repite el nombre de la pista modelo.
- `copy_fx` (verdadero/falso): Copiar la cadena de plugins. Por defecto sí.

Dice: «Listo, creé {name} igual a {source}.»
Ejemplos: «quiero grabar otra pista de guitarra igual a la que ya tengo» · «hacé otra pista como la de voz»

## Plugins y procesamiento

### `fx.add`

Carga un plugin (instrumento o efecto) en una pista. Acepta el nombre exacto o una descripción por tipo y marca; si la descripción coincide con varios, Miky ofrece las opciones para elegir.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `name` (texto): Nombre exacto ("ReaEQ", "FabFilter Pro-Q 4") o descripción: "un compresor estilo bus de SSL", "un equalizador tipo pultec", "un ecualizador de FabFilter". \*
- `position` (entero) de 1 a 64: Posición en la cadena de la pista (1 = primero). Si se omite, va al final.

Dice: «Cargué {name} en {track_name}.»
Ejemplos: «cargá ReaEQ en la pista 2» · «poné un compresor en la voz»

### `fx.remove`

Quita un plugin de la cadena de una pista.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `fx` (texto): Plugin a quitar: nombre ("ReaEQ") o posición ("2"). Si se omite, el último de la cadena.

Dice: «Saqué {removed}.»
Ejemplos: «sacá el último plugin de la voz»

### `fx.bypass`

Activa o desactiva (bypass) un plugin sin quitarlo.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `fx` (texto): Plugin por nombre o posición.
- `enabled` (verdadero/falso): true = activo, false = en bypass. Si se omite, invierte el estado.

Dice: «Listo, cambié el bypass de {fx}.»
Ejemplos: «desactivá el reverb de la voz»

### `fx.set_param`

Cambia un parámetro de un plugin. El parámetro se busca por nombre (por ejemplo "threshold" o "ratio").

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `fx` (texto): Plugin por nombre o posición. \*
- `param` (texto): Nombre (o parte del nombre) del parámetro, por ejemplo "threshold", "ratio", "gain". \*
- `value` (número): Valor en la escala real del parámetro (dB, Hz, etc.). Si normalized es true, va de 0 a 1. \*
- `normalized` (verdadero/falso): Si es true, value va de 0 a 1 sobre todo el rango del parámetro.

Dice: «Puse {param} en {value}.»
Ejemplos: «bajá el threshold del compresor a -18 dB» · «poné el ratio en 4 a 1»

### `fx.search`

Busca en los plugins instalados los que coinciden con una descripción (tipo, marca o nombre) y devuelve los nombres reales. Sirve para responder «¿qué compresores tengo?» o para descubrir el nombre exacto antes de cargar.

**Parámetros**

- `query` (texto): Descripción o parte del nombre: «compresor», «reverb de placa», «waves», «pultec». \*
- `limit` (entero): Cuántos candidatos devolver (por defecto 8).

Dice: «Encontré {count}: {summary}.»
Ejemplos: «¿qué compresores tengo instalados?» · «¿tenés algún pultec?»

### `fx.installed`

Lista todos los plugins que REAPER tiene instalados, con la cantidad y los fabricantes.

_Sin parámetros._

Dice: «Tenés {count} plugins instalados.»
Ejemplos: «¿cuántos plugins tengo?»

### `fx.params`

Lee los parámetros reales de los plugins cargados en una pista (threshold, ratio, ataque, frecuencia, ganancia, etc.) para poder opinar sobre cómo está ajustado realmente.

**Parámetros**

- `track` (texto): Pista: nombre o número. Si se omite, la seleccionada.
- `fx` (texto): Solo este plugin (por nombre). Si se omite, todos los de la pista.
- `limit` (entero): Cuántos parámetros por plugin (por defecto 12).

Ejemplos: «¿cómo está ajustado el compresor de la voz?» · «¿qué tiene cargado la batería?»

### `fx.favorites`

Lista los plugins marcados como favoritos en el explorador de plugins de REAPER (la carpeta Favoritos).

_Sin parámetros._

Dice: «Tus favoritos: {summary}.»
Ejemplos: «¿cuáles son mis plugins favoritos?» · «¿qué tengo en favoritos?»

### `fx.list`

Lista los plugins cargados en una pista para saber qué hay.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*

Ejemplos: «¿qué plugins tiene la pista de voz?»

### `fx.open`

Abre la ventana de un plugin para verlo o tocarlo a mano.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `fx` (texto): Plugin por nombre o posición.

Dice: «Abrí {fx}.»
Ejemplos: «abrí la interfaz del compresor»

## Transporte

### `transport.play`

Empieza a reproducir desde el cursor.

_Sin parámetros._

Dice: «Dale.»
Ejemplos: «dale» · «reproducí» · «play»

### `transport.stop`

Detiene la reproducción o la grabación.

_Sin parámetros._

Dice: «Paré.»
Ejemplos: «pará» · «stop» · «detené»

### `transport.pause`

Pausa la reproducción sin volver al cursor.

_Sin parámetros._

Dice: «Pausado.»
Ejemplos: «pausá»

### `transport.record`

Arranca a grabar en las pistas armadas.

_Sin parámetros._

Dice: «Grabando.»
Ejemplos: «grabá» · «a grabar» · «record»

### `transport.set_position`

Mueve el cursor a un compás o a un tiempo en segundos.

**Parámetros**

- `bar` (entero) mínimo 1: Compás destino, contando desde 1.
- `beat` (número) mínimo 1: Pulso dentro del compás (1 = primer pulso).
- `seconds` (número) mínimo 0: Tiempo destino en segundos, si se prefiere al compás.

Dice: «Me fui al compás {bar}.»
Ejemplos: «andá al compás 32» · «volvé al principio del estribillo»

### `transport.goto_start`

Lleva el cursor al comienzo del proyecto.

_Sin parámetros._

Dice: «Al principio.»
Ejemplos: «andá al principio»

### `transport.goto_end`

Lleva el cursor al final del proyecto.

_Sin parámetros._

Dice: «Al final.»
Ejemplos: «andá al final de la sesión»

### `transport.set_loop`

Define y activa o desactiva el loop.

**Parámetros**

- `start` (número) mínimo 0: Inicio del loop en segundos.
- `finish` (número) mínimo 0: Fin del loop en segundos.
- `enabled` (verdadero/falso): true = activar loop, false = desactivar.

Dice: «Listo, configuré el loop.»
Ejemplos: «activá el loop de grabación» · «hacé loop entre el compás 1 y el 8»

### `transport.goto_marker`

Lleva el cursor a un marcador o región por su nombre.

**Parámetros**

- `name` (texto): Nombre del marcador o región. \*

Dice: «Fui a {name}.»
Ejemplos: «andá al marcador Estribillo»

## Proyecto

### `project.save`

Guarda el proyecto actual.

_Sin parámetros._

Dice: «Guardado.»
Ejemplos: «guardá» · «guardá los cambios»

### `project.save_as`

Guarda el proyecto con un nombre o en una carpeta nueva. Usar solo si el usuario dictó la ruta exacta.

**Parámetros**

- `path` (texto): Ruta completa del archivo .rpp, por ejemplo "D:\\Sesiones\\Tema 3.rpp". \*

**Pide confirmación antes de ejecutar.**
Dice: «Guardé el proyecto en {path}.»
Ejemplos: «guardá el proyecto como "Tema 3" en la carpeta Sesiones»

### `project.undo`

Deshace la última acción.

_Sin parámetros._

Dice: «Deshecho.»
Ejemplos: «deshacé» · «undo»

### `project.redo`

Rehace la última acción deshecha.

_Sin parámetros._

Dice: «Rehecho.»
Ejemplos: «rehacé»

### `project.set_tempo`

Cambia el tempo (BPM) del proyecto.

**Parámetros**

- `bpm` (número) de 5 a 960: Tempo en pulsos por minuto. \*

Dice: «Tempo en {bpm}.»
Ejemplos: «poné el tempo en 120» · «cambiá a 96 BPM»

### `project.set_metronome`

Activa o desactiva el metrónomo.

**Parámetros**

- `enabled` (verdadero/falso): true = activar, false = desactivar. Si se omite, invierte.

Dice: «Listo, cambié el metrónomo.»
Ejemplos: «prendé el metrónomo» · «apagá el click»

## Marcadores y regiones

### `marker.add`

Crea un marcador en el cursor o en una posición dada.

**Parámetros**

- `name` (texto): Nombre del marcador. \*
- `position` (número) mínimo 0: Posición en segundos. Si se omite, usa el cursor.

Dice: «Marqué {name}.»
Ejemplos: «marcá el comienzo del estribillo»

### `region.add`

Crea una región entre dos tiempos.

**Parámetros**

- `name` (texto): Nombre de la región. \*
- `start` (número) mínimo 0: Inicio en segundos.
- `finish` (número) mínimo 0: Fin en segundos.

Dice: «Creé la región {name}.»
Ejemplos: «creá una región llamada Estribillo»

## Renderizado

### `render.start`

Renderiza el proyecto (mezcla completa, stems o regiones) con los ajustes actuales de REAPER.

**Parámetros**

- `mode` (texto) valores: `last`, `mix`, `entire`, `time_selection`, `regions`, `selected_items`, `stems`, `stems_master`: mix/entire = mezcla completa; time_selection = solo la selección de tiempo; regions = todas las regiones; stems = todas las pistas por separado; stems_master = stems + mezcla; last = respetar lo último configurado en REAPER.
- `out_dir` (texto): Carpeta de destino. Si se omite, se usa la carpeta configurada en Miky.
- `pattern` (texto): Nombre de archivo, admite comodines de REAPER como $project. Si se omite se usa el configurado.
- `format` (texto) valores: `last`, `wav`: wav usa los ajustes por defecto de WAV de REAPER; last respeta el último formato usado.
- `normalize_lufs` (número) de -40 a 0: Normalizar a este nivel de loudness integrado, por ejemplo -14. Si se omite, no normaliza.
- `add_to_project` (verdadero/falso): Si es true, agrega los archivos renderizados al proyecto.
- `overwrite` (verdadero/falso): Pisa el archivo si ya existe. Sin esto, si el nombre coincide con un archivo previo el render se rechaza para no bloquear REAPER con un diálogo.

**Pide confirmación antes de ejecutar.**
Dice: «Listo, terminó el render.»
Ejemplos: «renderizá la mezcla» · «exportá todas las pistas por separado en WAV» · «renderizá a -14 LUFS»

## Vista de REAPER

### `view.mixer`

Muestra u oculta el mezclador de REAPER.

**Parámetros**

- `visible` (verdadero/falso): true = mostrar, false = ocultar. Si se omite, alterna.

Dice: «Mezclador {state_text}.»
Ejemplos: «abrí el mixer» · «mostrame el mezclador» · «cerrá el mixer»

### `view.routing`

Abre o cierra la ventana de ruteo (la matriz de envíos y conexiones entre pistas). Alterna: si estaba abierta, la cierra.

_Sin parámetros._

Dice: «Listo.»
Ejemplos: «abrí la matriz de ruteo» · «mostrame los ruteos» · «cerrá la ventana de ruteo»

## Ruteo y envíos

### `track.output`

Manda el audio de una pista a un par de salidas físicas de la placa (1/2, 3/4, 5/6…), además de la mezcla principal. Sirve para armar una mezcla de monitoreo aparte, por ejemplo para los auriculares.

**Parámetros**

- `track` (texto): Pista: nombre o número. \*
- `pair` (entero): Par de salidas físicas: 1 = salidas 1/2, 2 = salidas 3/4, 3 = salidas 5/6.
- `level_db` (número): Nivel de esa salida en dB. Si se omite, 0 dB.
- `mono` (verdadero/falso): Mezclar a mono en esa salida.

Dice: «{track} ahora sale también por las salidas {channels}.»
Ejemplos: «mandá la batería a las salidas 3 y 4» · «ruteá el bajo a la salida 3/4»

### `track.output_clear`

Quita todas las salidas físicas de una pista (deshace un ruteo de monitoreo).

**Parámetros**

- `track` (texto): Pista: nombre o número. \*

Dice: «Saqué las salidas físicas de {track}.»
Ejemplos: «sacá el ruteo de monitoreo de la batería» · «quitá las salidas físicas del bajo»

### `send.add`

Crea un envío de una pista a otra (por ejemplo, para mandar la voz a un reverb).

**Parámetros**

- `from` (texto): Pista que envía: nombre o número. Si se omite, la pista seleccionada.
- `to` (texto): Pista que recibe: nombre o número. \*
- `level_db` (número) de -150 a 12: Nivel del envío en dB. Si se omite, queda en 0 dB.
- `mode` (texto) valores: `post_fader`, `pre_fx`, `post_fx`: Punto de toma de la señal. Por defecto post_fader.

Dice: «Envié {from} a {to}.»
Ejemplos: «mandá la voz al reverb» · «creá un envío de la guitarra al bus de efectos»

### `send.remove`

Quita un envío entre dos pistas.

**Parámetros**

- `from` (texto): Pista que envía: nombre o número. Si se omite, la pista seleccionada.
- `to` (texto): Pista que recibe: nombre o número. \*

Dice: «Saqué el envío de {from} a {to}.»
Ejemplos: «sacá el envío de la voz al reverb»

### `send.set_level`

Cambia el nivel de un envío existente.

**Parámetros**

- `from` (texto): Pista que envía: nombre o número. Si se omite, la pista seleccionada.
- `to` (texto): Pista que recibe: nombre o número. \*
- `db` (número) de -150 a 24: Nivel del envío en dB (0 = sin atenuación, -6 = la mitad). \*

Dice: «Envío de {from} a {to} en {level_db} dB.»
Ejemplos: «subí el envío de la voz al reverb 3 dB»

## Edición de items

### `item.keep_between`

Recorta los items seleccionados para dejar solo lo que cae entre dos marcadores (o dos tiempos). Borra lo de afuera.

**Parámetros**

- `start_marker` (texto): Nombre del marcador o región donde empieza lo que se conserva.
- `end_marker` (texto): Nombre del marcador o región donde termina lo que se conserva.
- `start` (número) mínimo 0: Inicio en segundos, si no se usa un marcador.
- `end` (número) mínimo 0: Fin en segundos, si no se usa un marcador.
- `track` (texto): Si no hay items seleccionados, recorta todos los items de esta pista (nombre o número).

Dice: «Recorté el item: dejé de {start} a {finish}.»
Ejemplos: «dejá del item solo lo que va desde el marcador estrofa hasta el marcador estribillo» · «recortá este item entre 1:10 y 1:40»

### `item.split_at_cursor`

Corta en dos los items seleccionados en el cursor.

**Parámetros**

- `position` (número) mínimo 0: Segundo donde cortar. Si se omite, usa el cursor.

Dice: «Corté {splits} item.»
Ejemplos: «cortá este audio acá»

### `item.delete_selected`

Borra los items seleccionados del proyecto.

_Sin parámetros._

Dice: «Borré {deleted} item.»
Ejemplos: «borrá lo que tengo seleccionado»
