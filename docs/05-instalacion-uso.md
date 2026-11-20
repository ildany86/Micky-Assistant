# Instalación y uso

## Requisitos

| Qué | Detalle |
|---|---|
| Sistema | Windows 10 u 11 (64 bits) |
| DAW | REAPER 7 (probado en 7.84) |
| Python | 3.11 o superior (probado en 3.12) |
| Internet | para la IA; la voz online también lo usa (si no hay, cae a la voz local) |
| Micrófono | por defecto usa el interno (WASAPI); la interfaz queda para REAPER por ASIO (ver [voz y audio](04-voz-y-audio.md)) |

## Instalación

### 1. Entorno de Python

Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"
```

`.[voice]` incluye el reconocimiento local (`faster-whisper`, `onnxruntime`).
Si no lo instalás, Miky funciona igual pero sin micrófono.

### 2. Puente dentro de REAPER

```powershell
.\.venv\Scripts\python.exe tools\build_lua.py
.\.venv\Scripts\python.exe -m miky install-bridge
```

Esto hace tres cosas:

1. compila los módulos Lua en un solo archivo `miky_bridge.lua`,
2. lo copia a `%APPDATA%\REAPER\Scripts\Miky\`,
3. agrega un bloque a `%APPDATA%\REAPER\Scripts\__startup.lua` para que arranque
   con REAPER.

El puente es un script de fondo: no aparece en el menú de REAPER, no agrega
botones y no cambia la interfaz. Para quitarlo: `miky install-bridge --remove`.

### 3. Verificación

```powershell
.\.venv\Scripts\python.exe -m miky doctor
```

Todo lo que diga `[ok]` está en orden. Los `[!]` son avisos que conviene mirar;
los `[x]` hay que resolverlos.

### 4. API key de Gemini

1. Entrá a <https://aistudio.google.com/apikey> con tu cuenta de Google.
2. «Create API key» → copiá la clave (`AIza…`).
3. Abrí Miky, clic derecho en el ícono → **Ajustes** → pegala → **Guardar**.

Se guarda cifrada con tu usuario de Windows (DPAPI), no en texto plano. También
se puede definir con la variable de entorno `MIKY_API_KEY` o `GEMINI_API_KEY`.

La capa gratuita no pide tarjeta. Alcanza para uso personal: cientos de órdenes
por día, y las órdenes básicas ni siquiera gastan cuota.

## Uso diario

Doble clic en **`run_miky.bat`**. Aparece el ícono flotante; lo arrastrás a donde
quede cómodo y la posición se recuerda.

Si REAPER no está abierto: clic derecho en el ícono → **Abrir REAPER con Miky**.

### Interacciones con el ícono

| Acción | Qué hace |
|---|---|
| Clic | activa el micrófono (push-to-talk) o corta la voz si está hablando |
| Clic derecho | menú: escuchar ahora, ajustes, abrir REAPER, reinstalar puente, salir |
| Doble clic | ajustes |
| Arrastrar | mover el ícono (se guarda la posición) |
| Ctrl + rueda | cambiar el tamaño del ícono |

### Cómo hablarle

Modo **siempre escuchando** (por defecto):

> **«Miky, creá una pista de guitarra»**
> **«Miky, subí el bajo dos dB»**
> **«Miky, grabá»**
> **«Miky, renderizá la mezcla»**

También sirve decir «Miky» y esperar: el ícono se pone celeste (*te escucho*) y
ahí decís la orden.

Modo **push to talk**: tocás el ícono y hablás, sin palabra clave.

### Ejemplos por tarea

| Querés… | Decí… |
|---|---|
| armar una sesión | «Miky, creá pistas para bombo, redo, hi-hat y overheads» |
| preparar una toma | «Miky, armá la guitarra y poné la entrada en mono 1» |
| ajustar la mezcla | «Miky, bajá la voz 3 dB y paneá la guitarra a la izquierda» |
| cargar procesamiento | «Miky, cargá ReaEQ en la voz» |
| ubicarte | «Miky, andá al compás 32» |
| marcar estructura | «Miky, creá una región llamada Estribillo del 1:10 al 1:40» |
| exportar | «Miky, exportá todas las pistas por separado en WAV» |

## Herramientas de diagnóstico

| Comando | Para qué |
|---|---|
| `miky doctor` | entorno, REAPER, puente, micrófono, voces, catálogo |
| `miky doctor --network` | además prueba la conexión y la API key contra Gemini |
| `miky status` | ¿hay latido del puente? ¿qué proyecto tiene abierto? |
| `miky devices` | micrófonos detectados y cuál elegiría |
| `miky voices` | voces de Windows instaladas |
| `python tools\voice_selftest.py` | sintetiza una frase, la pasa por VAD y la transcribe |
| `python tools\ui_smoke.py 4` | levanta el ícono 4 segundos y lo cierra (prueba de humo) |
| `python tools\live_test.py` | prueba de integración real: abre REAPER, ejecuta 55 pedidos, renderiza y cierra |
| `python -m miky bench` | mide cuánto tarda cada etapa en tu máquina |
| `python -m miky plugins` | lista los plugins instalados, tus favoritos y (con `-q compresor`) busca por descripción |
| `python tools\render_states.py` | regenera las imágenes de los estados del ícono |
| `python tools\render_faces.py` | regenera la vista grande de las caras |
| `python tools\gen_catalog_doc.py` | regenera el catálogo de comandos |

## Configuración

Archivo: `%APPDATA%\Miky\config.toml`. Se puede editar a mano (reiniciar Miky) o
desde Ajustes.

```toml
[ai]
provider = "gemini"                      # gemini | openai | local | mock
model = "gemini-3.5-flash-lite"          # el rápido, para el día a día
model_strong = "gemini-3.5-flash"         # respaldo cuando el rápido no resuelve
api_key = "dpapi:..."                    # cifrada; no editar a mano
base_url = ""                            # solo para openai/local

[voice]
enabled = true
wake_word = "miky"
mode = "always"                          # always | push_to_talk
input_device = ""                        # vacío = automático (prefiere el interno)
stt_model = "base"                       # base (rápido) | small (más preciso, 3x más lento)
stt_beam = 1                              # 1 = rápido; 5 = más preciso y el doble de lento
tts_engine = "edge"                      # edge (online, argentina) | sapi (local)
edge_voice = "es-AR-TomasNeural"         # hombre, argentino
tts_voice = ""                           # solo para el motor local
output_device = ""                       # vacío = salida predeterminada
chime = true                             # aviso sonoro al escuchar "Miky"
speak_replies = true
silence_ms = 550
vad_threshold = 0.62                     # más alto = más estricto con el ruido
feedback = "mixto"                       # mixto | sonidos | voz
follow_up_seconds = 8                    # tras responder, escucha sin pedir "Miky"
vocabulary = ["Eamut", "SSL", "Waves"]  # palabras propias que debe reconocer bien
corrections = ["eamoot=Eamut"]           # lo que transcribe mal = lo que quiso decir

[ui]
position = [1800, 900]
scale = 1.0

[safety]
confirm_destructive = true
ask_before_record = true                 # pregunta "¿estás listo?" antes de grabar
```

Cambiar de proveedor de IA (por ejemplo a Groq o a un LM Studio local):

```toml
[ai]
provider = "local"
model = "qwen2.5-7b-instruct"
base_url = "http://127.0.0.1:1234/v1"
api_key = ""
```

## Arranque automático con Windows

1. `Win + R` → `shell:startup` → Enter.
2. Crear un acceso directo a `run_miky.bat` en esa carpeta.

## Actualizar

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"
.\.venv\Scripts\python.exe tools\build_lua.py
.\.venv\Scripts\python.exe -m miky install-bridge
```

## Desinstalar

```powershell
.\.venv\Scripts\python.exe -m miky install-bridge --remove
```

Después se puede borrar la carpeta del proyecto y `%APPDATA%\Miky`.

## Problemas frecuentes

| Síntoma | Qué revisar |
|---|---|
| «El puente de REAPER no está activo» | REAPER abierto desde Miky; `miky status`; `miky install-bridge` |
| El ícono está gris | no hay conexión con el puente (REAPER cerrado o sin el script) |
| No entiende pedidos complejos | falta la API key: Ajustes; `miky doctor` |
| «Se agotó la cuota» | esperá unos minutos; la capa gratuita tiene límite por minuto y por día |
| No me escucha | `miky devices`; Ajustes → Micrófono → «Automático» (nunca «Asignador de sonido») |
| Escucha por la interfaz y no por la notebook | la config tenía un pseudo-dispositivo; poner «Automático» |
| Habla con voz de mujer | Ajustes → Motor → «Online · español argentino» |
| Miky habla pero no lo escucho | la salida está puesta en otro dispositivo | Ajustes → Salida → «Predeterminada de Windows» |
| Reconoce mal los nombres de las pistas | probar `stt_model = "small"` (más preciso, pero tarda ~5 s por orden) |
| No abre el mezclador | «Miky, abrí el mixer» (comando `view.mixer`) |
| Se escucha a sí mismo | usar auriculares; el micrófono se silencia mientras habla, pero no con parlantes fuertes |
| «No encontré el plugin» | usar el nombre tal como aparece en REAPER, o cargarlo a mano una vez y copiar el nombre exacto |

El log completo está en `%APPDATA%\Miky\logs\miky.log` y el del puente en
`%APPDATA%\Miky\ipc\bridge.log`.
