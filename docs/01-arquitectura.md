# Arquitectura

Cómo está armado Miky por dentro, para poder mantenerlo (o ampliarlo) sin
tener que releer todo el código cada vez.

## Idea central

Una sola regla ordena todo el diseño: **la IA no ejecuta nada, solo elige qué
comando de una lista cerrada ejecutar**. Todo lo demás (voz, motor, puente,
interfaz) existe para hacer que esa elección sea cómoda, segura y rápida.

```
┌────────────────────────────── tu computadora ───────────────────────────────┐
│                                                                             │
│   micrófono                                                                  │
│      │                                                                       │
│      ▼                                                                       │
│   ┌─────────────┐    ┌──────────────┐    ┌───────────────────────────────┐   │
│   │  captura    │───▶│  VAD Silero  │───▶│  faster-whisper (texto)       │   │
│   │ sounddevice │    │  (segmenta)  │    │  local, CPU, int8             │   │
│   └─────────────┘    └──────────────┘    └───────────────┬───────────────┘   │
│                                                          │ «Miky, ...»       │
│                                                          ▼                   │
│                                             ┌───────────────────────┐        │
│                                             │ palabra clave         │        │
│                                             │ + router local        │        │
│                                             └───────┬───────┬───────┘        │
│                                     comando directo │       │ no coincide     │
│                                                     │       ▼                 │
│                                                     │  ┌──────────────────┐   │
│                                                     │  │ IA en la nube    │   │
│                                                     │  │ (elige comandos) │   │
│                                                     │  └────────┬─────────┘   │
│                                                     ▼           ▼             │
│                                          ┌─────────────────────────────┐      │
│                                          │ motor: valida + confirma    │      │
│                                          │ ejecuta el plan             │      │
│                                          └──────────────┬──────────────┘      │
│                                                         ▼                     │
│                                    %APPDATA%\Miky\ipc  (archivos JSON)        │
│                                                         ▼                     │
│                                          ┌─────────────────────────────┐      │
│                                          │ puente ReaScript dentro de  │      │
│                                          │ REAPER (un solo .lua)       │      │
│                                          └──────────────┬──────────────┘      │
│                                                         ▼                     │
│                                                      REAPER                   │
│                                                         │                     │
│                                             ┌───────────┴──────────┐          │
│                                             ▼                      ▼          │
│                                      plantilla de respuesta   estado nuevo   │
│                                             │                                 │
│                                             ▼                                 │
│                                        SAPI5 (habla)                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Capas y archivos

| Capa | Archivos | Responsabilidad |
|---|---|---|
| **Interfaz** | `ui/icon.py`, `ui/shell.py`, `ui/settings.py`, `ui/confirm.py`, `ui/tray.py`, `ui/theme.py` | Ícono flotante, menú, ajustes, confirmación, bandeja |
| **Orquestación** | `app.py` | Une voz, IA, motor y puente; decide qué estado mostrar |
| **Entrada** | `voice/pipeline.py`, `voice/audio.py`, `voice/vad.py`, `voice/stt.py`, `voice/wake.py` | Captura, segmentación, transcripción, palabra clave |
| **Interpretación** | `router.py`, `ai/*` | Comandos directos primero, IA después |
| **Control** | `engine.py`, `catalog.py`, `data/commands.json` | Validación, confirmación, ejecución, respuesta |
| **Transporte** | `bridge.py` | Protocolo IPC (archivos) |
| **Puente** | `reaper/src/miky/*.lua` → `data/miky_bridge.lua` | Ejecuta la API real de REAPER |
| **Voz de salida** | `voice/tts.py`, `speech.py` | SAPI5 y plantillas de respuesta |
| **Soporte** | `config.py`, `paths.py`, `security.py`, `reaper.py`, `doctor.py`, `log.py` | Config, rutas, DPAPI, instalación, diagnóstico, logs |

## Hilos

Miky es una app de escritorio con varios hilos. Cada uno existe por un motivo
concreto, no por decoración:

| Hilo | Quién | Por qué |
|---|---|---|
| **UI (principal)** | Qt | Todo lo visual. Nunca bloquea: las tareas largas van a otros hilos |
| **Voz** | `VoicePipeline._loop` | Lee el micrófono y corre el VAD de forma continua |
| **Warmup** | `VoicePipeline._warmup` | Carga el modelo de STT sin congelar la interfaz |
| **Comando** | `VoicePipeline._run_command` | Ejecuta el pedido (IA + REAPER) mientras el micrófono sigue vivo |
| **Monitor** | `MikyApp._monitor_loop` | Lee `status.json` cada 0,9 s para saber si REAPER está conectado |
| **TTS** | `SapiTts._run` | Es dueño del objeto COM de SAPI; habla y se puede interrumpir |
| **Confirmación** | `MikyApp._voice_confirm` | Escucha sí/no mientras el hilo de comando espera |
| **Cliente IPC** | el que llama | Serializa los pedidos con un lock: el puente atiende uno por vez |

Las reglas de convivencia:

- La UI **no** ejecuta comandos ni espera al puente: dispara una señal y sigue.
- El hilo de comando **no** toca widgets: usa `QMetaObject`/señales para pedir
  cosas a la UI.
- El hilo de voz **nunca** muere por una excepción: el bucle está envuelto en
  `try/except` y reporta el error sin cortar.
- El TTS se silencia mientras se ejecuta un comando y se pausa la captura
  mientras habla (para no escucharse a sí mismo).

## El recorrido de un pedido

Ejemplo: «Miky, subí el bajo dos dB».

1. **Captura** (`voice/audio.py`): bloques de 512 muestras desde WASAPI, a 16 kHz
   (si el dispositivo solo abre a 48 kHz, se remuestrea).
2. **VAD** (`voice/vad.py`): Silero recibe 512 muestras + 64 de contexto. Cuando
   detecta voz, acumula; cuando hay ~650 ms de silencio, cierra el segmento.
3. **STT** (`voice/stt.py`): faster-whisper transcribe el segmento completo.
4. **Palabra clave** (`voice/wake.py`): «miky/miki/mickey…» al principio. Si no
   está, y el modo es `always`, se descarta.
5. **Router** (`router.py`): normaliza el texto y prueba 23 patrones. «subí el
   bajo dos dB» coincide → `track.adjust_volume` con `delta_db=2`.
   El nombre «bajo» se recupera del **texto original**, no del normalizado.
6. **Motor** (`engine.py`): valida los argumentos contra el catálogo, aplica
   valores por defecto, y si el comando es peligroso pide confirmación.
7. **Transporte** (`bridge.py`): escribe un archivo de pedido y espera la
   respuesta.
8. **Puente** (`ipc.lua`): lo lee, lo ejecuta con `track.adjust_volume`, abre un
   bloque de deshacer, escribe la respuesta.
9. **Respuesta** (`speech.py`): la plantilla del comando arma «Bajo quedó en -4
   dB.» con los datos reales del resultado.
10. **TTS** (`voice/tts.py`): lo dice.

Si en el paso 5 no hubiera coincidencia, el pedido iría a la IA (paso 5b) con el
contexto del proyecto; la IA devolvería una o más llamadas a funciones, que el
motor validaría igual que un comando directo.

## El contexto que ve la IA

Antes de consultar, `app.build_context()` pide `state.get` al puente y arma:

```json
{
  "assistant": {"name": "Miky", "version": "0.1.0b1"},
  "project": {"name": "tema.rpp", "tempo": 96, "length": 62.0, "track_count": 5},
  "transport": {"playing": false, "recording": false, "cursor": 5.0, "cursor_bar": 3},
  "selected_tracks": [2],
  "tracks": [
    {"index": 1, "name": "Hi-hat", "volume_db": 0, "pan": 35, "mute": false,
     "solo": false, "armed": false, "selected": false, "fx_count": 0}
  ],
  "markers": [{"index": 1, "name": "Estribillo", "position": 30.0}],
  "regions": [{"index": 1, "name": "Coro", "start": 10.0, "finish": 20.0}],
  "last_actions": [{"command": "track.add", "args": {"name": "Bajo"}, "ok": true}]
}
```

Se recorta a los campos útiles (sin rutas internas ni datos de más) y se limita
a 64 pistas. `last_actions` guarda las últimas 6 acciones para que el modelo
pueda resolver «otra vez» o «un poco más».

## Decisiones de diseño

### Catálogo cerrado, no ejecución de código

La IA **nunca** escribe Lua ni Python. Elige entre 51 comandos con parámetros
tipados. Motivos:

- un error de interpretación no puede borrar una sesión ni ejecutar algo
  arbitrario;
- los errores son explicables («no encontré la pista X») en vez de un stack
  trace dentro de REAPER;
- se puede probar cada comando por separado;
- el prompt es más corto y la respuesta más precisa que pidiendo código.

La contracara: para cubrir una función nueva hay que escribir el comando. Es un
costo aceptado.

### IPC por archivos, no HTTP ni OSC

ReaScript no tiene cliente HTTP ni WebSocket nativo. Las alternativas eran:

| Opción | Problema |
|---|---|
| HTTP/WebSocket | habría que meter una dependencia (SWS/ReaPack) o un binario |
| OSC | cubre transporte y volumen, pero no pistas, FX ni render |
| Inyectar teclado/mouse | frágil y prohibido por diseño (además de que roba foco) |
| **Archivos en una carpeta** | cero dependencias, depurable a mano, 31 ms de latencia |

El costo (0,9 ms por escritura) es despreciable frente al tick de `defer` de
~31 ms. Detalle en [protocolo](02-protocolo-puente.md).

### Consejos sin ejecución

La IA tiene dos herramientas que no tocan REAPER: miky_ask (preguntar un dato
que falta) y miky_respond (contestar una pregunta de criterio). Cuando el
pedido es una consulta («¿qué hacemos para más espacialidad?»), el motor recibe
una respuesta hablada y no ejecuta ningún paso. Es el único camino por el que la
IA puede hablar sin que haya un comando detrás, y está limitado a texto: no
puede convertir un consejo en una acción.

### Respuesta hablada por plantillas, no por IA

Pedirle a la IA que redacte la confirmación costaría otra consulta (cuota y
~1 s más). Las plantillas usan el resultado real del comando, así que el texto
es exacto y determinista. La IA solo habla cuando necesita preguntar algo.

### Audio por WASAPI y no por ASIO

PortAudio (el backend de `sounddevice`) no trae soporte ASIO en los wheels de
Python. Si REAPER toma la interfaz por ASIO en exclusiva, el asistente no puede
compartirla. Por eso elige por defecto un dispositivo distinto (el micrófono
interno por WASAPI). Detalle en [voz y audio](04-voz-y-audio.md).

### Una sola instancia del puente

Si el script se ejecuta dos veces (por ejemplo porque REAPER lo arranca desde
`__startup.lua` y además se lo pasa por línea de comandos), dos puentes
competirían por los mismos archivos y se pisarían las respuestas. Se resuelve
con un lock: `os.rename` en Windows falla si el destino existe, y eso da un
test-and-set atómico.

### API key cifrada con DPAPI

`security.py` cifra la clave con la cuenta de Windows (`CryptProtectData`). En
el archivo queda `api_key = "dpapi:..."`. Si la copia a otra máquina, la clave
no se puede descifrar y hay que volver a pegarla (que es lo deseable).

## Seguridad: qué puede y qué no puede hacer

**Puede**

- Ejecutar los 51 comandos del catálogo sobre el proyecto abierto en REAPER.
- Escribir audio (render) solo en la carpeta configurada (o en cualquiera si no
  se configuró `safety.allowed_render_roots`).
- Leer el estado del proyecto.

**No puede**

- Ejecutar comandos del sistema, abrir programas, tocar archivos ajenos.
- Inyectar teclado o mouse, ni siquiera dentro de REAPER.
- Modificar la configuración de REAPER ni sus preferencias.
- Ejecutar código que venga del modelo o del usuario.
- Ver ni transmitir audio: al STT le llegan muestras y devuelve texto local.

El puente, además, solo acepta nombres de archivo con un patrón estricto, limita
los pedidos a 32 pasos y 256 KB, y descarta cualquier comando que no esté en su
tabla de handlers.

## Cómo se agrega un comando

1. **Catálogo**: agregar la ficha en `src/miky/data/commands.json` (id,
   categoría, resumen, parámetros, requeridos, `danger`, plantilla hablada,
   ejemplos).
2. **Puente**: implementar el handler en el módulo Lua que corresponda
   (`cmd_tracks.lua`, `cmd_fx.lua`, …) con la firma
   `function(args) -> tabla`. Usar `MIKY.util` para validar y `MIKY.state` para
   resolver pistas/FX.
3. **Recompilar**: `python tools/build_lua.py` (concatena y verifica sintaxis).
4. **Instalar**: `python -m miky install-bridge`.
5. **Probar**: agregar el caso en `tests/test_lua_bridge.py`; correr
   `python -m pytest`. El test `test_todos_los_comandos_del_catalogo_tienen_handler`
   falla si se olvidaron del handler.
6. **Documentar**: `python tools/gen_catalog_doc.py` regenera el catálogo.

Si el comando es peligroso (no se deshace con Ctrl+Z), marcar `"danger": true` y
agregar la pregunta en `engine.CONFIRM_QUESTIONS`.

## Estado y señales de la interfaz

`MikyApp.compute_state()` combina, en este orden de prioridad:

1. `error` (por 2,5 s después de un fallo),
2. `confirm` (hay una confirmación pendiente),
3. `working` (ejecutando un plan),
4. `thinking` / `listening` (lo que diga el pipeline de voz),
5. `speaking` (el TTS está hablando),
6. `offline` (no hay latido del puente),
7. `idle`.

El ícono traduce ese estado a color, halo y punto de estado. La UI lo consulta
cada 120 ms; no hay eventos empujados desde los hilos de trabajo (salvo las
confirmaciones, que sí usan señales porque bloquean).

## Limitaciones conocidas de la beta

- **Sin memoria conversacional**: cada pedido es independiente. «No, la otra» no
  funciona.
- **Sin verificación posterior**: se confía en lo que devuelve el puente. Si un
  comando dice que salió bien pero REAPER hizo otra cosa, Miky no lo detecta
  (salvo en `track.duplicate`, que verifica el conteo de pistas).
- **Render bloqueante**: el render es sincrónico dentro de REAPER y congela el
  puente mientras dura. La app lo tolera (marca `busy` y usa un timeout largo),
  pero durante un render largo no atiende otros pedidos.
- **Plugins de terceros**: se pueden cargar y tocar parámetros expuestos, pero no
  se conoce la interfaz gráfica de cada uno.
- **Un solo proyecto**: siempre opera sobre el proyecto activo de REAPER.
