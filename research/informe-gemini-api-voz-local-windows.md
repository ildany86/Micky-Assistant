# Informe técnico — Gemini API (function calling) + voz local en Windows 11 CPU-only
**Fecha de research:** 6 de noviembre de 2026 · **Máquina objetivo verificada localmente**

---

## 0. Datos verificados de ESTA máquina (no estimados)

| Ítem | Valor real medido |
|---|---|
| SO | Windows 11 Pro, build **26300** |
| CPU | Intel **i7-8665U** @ 1.90 GHz (4c/8t, Whiskey Lake) |
| RAM | **15.8 GB** |
| Python | **3.14.6** (64-bit) — *crítico para wheels* |
| numpy | 2.5.3 |
| REAPER | instalado en `C:\Program Files\REAPER (x64)\reaper.exe` |
| Driver ASIO | `RTHDASIO64.dll` presente (familia Roland/Edirol) |
| Voces SAPI5 visibles | **solo 2**: `Microsoft Zira Desktop` (en-US), `Microsoft Helena Desktop` (es-ES) |
| Voces OneCore (WinRT) | `Microsoft Helena`, `Microsoft Laura`, `Microsoft Pablo` (todas es-ES) |
| Host APIs que ve PortAudio | MME, DirectSound, WASAPI, WDM-KS — **NO ASIO** |

> Estas mediciones cambian varias respuestas: ver §B.4 (voces) y §B.5 (ASIO).

---

# TEMA A — Google Gemini API

## A.0 Contexto importante: hay DOS APIs vivas

Google movió la documentación de `ai.google.dev/gemini-api/docs/*` a `aistudio.google.com/docs/*` (las URLs viejas redirigen). La API principal ahora es la **Interactions API** (`client.interactions.create(...)`, con `steps` de tipo `function_call`), y `generate_content` quedó catalogada como **"Generate Content API (Legacy)"** — pero sigue soportada y es la que el SDK documenta con `types.FunctionDeclaration` / `response.function_calls`.

- Doc vigente de function calling (Interactions): <https://aistudio.google.com/docs/function-calling>
- Índice completo de docs para agentes: <https://aistudio.google.com/llms.txt> · todo en un archivo: <https://aistudio.google.com/llms-full.txt>

**Consejo práctico:** si querés el patrón `types.Tool` + `response.function_calls` que pediste, usá `generate_content` (funciona, es estable). Si querés el estado multi-turno del lado del servidor, mirá Interactions con `previous_interaction_id` (§A.7).

---

## A.1 SDK oficial: `google-genai` (nuevo) — `google-generativeai` está muerto

| | **NUEVO (usar)** | legacy (NO usar) |
|---|---|---|
| Paquete pip | `google-genai` | `google-generativeai` |
| Versión actual | **3.0.0** (PyPI, Apache-2.0) | discontinuado |
| Import | `from google import genai` · `from google.genai import types` | `import google.generativeai as genai` |
| Config | `genai.Client(...)` | `genai.configure(api_key=...)` |

Fuentes: <https://pypi.org/project/google-genai/> · <https://github.com/googleapis/python-genai> · <https://googleapis.github.io/python-genai/>

```bash
pip install -U "google-genai>=3.0,<4"
```

> ⚠️ El propio README avisa que el **Automatic Function Calling (AFC)** cambia en la próxima major: ya no se podrá invocar AFC desde `Models.generate_content`, solo desde `Chats`. **Recomendación: no uses AFC; declarás las funciones a mano y manejás el loop vos.** Así el código no se rompe.

### Ejemplo mínimo real: function calling manual (Generate Content, SDK 3.0.0)

```python
import json, os
from google import genai
from google.genai import types

client = genai.Client()          # toma GEMINI_API_KEY / GOOGLE_API_KEY del entorno

# 1) Declaración de la tool
decl = types.FunctionDeclaration(
    name="abrir_proyecto",
    description="Abre un proyecto de REAPER por nombre.",
    parameters_json_schema={                      # JSON Schema crudo
        "type": "object",
        "properties": {
            "nombre": {"type": "string", "description": "Nombre del proyecto, ej. 'Proyecto X'"},
            "solo_lectura": {"type": "boolean"},
        },
        "required": ["nombre"],
    },
)
tool = types.Tool(function_declarations=[decl])

config = types.GenerateContentConfig(
    tools=[tool],
    system_instruction="Sos un asistente de estudio. Respondé en español rioplatense, breve.",
    temperature=0.2,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)

# 2) Llamada
resp = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Abrí el proyecto Proyecto X, en solo lectura",
    config=config,
)

# 3) Leer las function calls
if resp.function_calls:
    fc = resp.function_calls[0]
    print(fc.name, dict(fc.args))          # -> 'abrir_proyecto' {'nombre': 'Proyecto X', ...}
    resultado = {"ok": True, "pista": "Proyecto X"}

    # 4) Devolver el resultado al modelo
    follow = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text="Abrí el proyecto Proyecto X")]),
            resp.candidates[0].content,                       # el turno 'model' con el function_call
            types.Content(role="tool", parts=[
                types.Part.from_function_response(name=fc.name, response=resultado)
            ]),
        ],
        config=config,
    )
    print(follow.text)
```

Notas finas:
- `parameters_json_schema=` acepta JSON Schema crudo; la variante vieja es `parameters=types.Schema(...)` (tipado, más verboso). Ambas existen en 3.0.0.
- `dict(fc.args)` — `fc.args` es un `MapComposite`, no un dict puro.
- `types.Part.from_function_response(name=..., response=...)` exige que `response` sea un objeto JSON (dict), no un string suelto.
- El rol del turno de respuesta es `"tool"`.

---

## A.2 Modelos disponibles hoy (nov 2026) con capa gratuita y function calling

Todos los de la tabla soportan **function calling + structured outputs** (verificado en las fichas de modelo). IDs exactos:

| Model ID | Estado | Free tier | Function calling | Notas |
|---|---|---|---|---|
| `gemini-3.8-flash` | Stable (sep 2026) | ✅ sí | ✅ | "más inteligente de los Flash"; 1M in / 65K out |
| `gemini-3.6-flash` | Stable | ✅ sí | ✅ | generación previa, buen balance |
| `gemini-3.5-flash-lite` | Stable (jul 2026) | ✅ sí | ✅ | **recomendado para producción liviana** |
| `gemini-3.1-flash-lite` | Stable | ✅ sí | ✅ | más barato aún |
| `gemini-3-flash-preview` | Preview | ✅ sí | ✅ | preview: no para prod |
| `gemini-2.5-flash` | **Deprecado** | residual | ✅ | desde 1-dic-2026 rutea a `gemini-3.5-flash-lite` |
| `gemini-2.5-flash-lite` | Legacy (sin deprecar) | residual | ✅ | acceso limitado a usuarios previos |
| `gemini-2.0-flash` | **SHUT DOWN** | ❌ | — | ya no existe |
| `gemini-4-argon` | Stable | ❌ **0 req** | ✅ | flagship, solo pago |
| `gemini-3.1-pro-preview` | Preview | ❌ | ✅ | solo pago |
| `gemma-4-31b-it`, `gemma-4-26b-a4b-it` | Open | ✅ sí | parcial | 30 RPM / 14.400 RPD |

**Recomendación para un asistente que llama funciones, liviano y en producción:**
1. **`gemini-3.5-flash-lite`** — la mejor relación latencia/costo/cuota (500 RPD gratis, 4.000 RPM en Tier 1). Es la que Google sugiere para proyectos nuevos.
2. **`gemini-3.8-flash`** — si necesitás razonamiento multi-paso o tool-calls encadenadas; pero solo 20 RPD gratis.
3. **`gemini-3.6-flash`** — punto medio si 3.8 te resulta caro.

Fuentes: <https://aistudio.google.com/docs/models> · <https://aistudio.google.com/docs/models/gemini-3.5-flash-lite> · <https://aistudio.google.com/docs/models/gemini-3.8-flash>

---

## A.3 Límites del free tier (⚠️ dato de terceros, ver disclaimer)

Google **dejó de publicar la tabla de RPM/TPM/RPD en los docs**. La página de rate limits ahora manda a `https://aistudio.google.com/rate-limit` (los números dependen de tu proyecto). Lo que sigue son lecturas de AI Studio publicadas por terceros el **21–22 de octubre de 2026**:

| Modelo | RPM | TPM (input) | RPD |
|---|---|---|---|
| `gemini-3.8-flash`, `3.6-flash`, `3-flash`, `2.5-flash` | **5** | 250.000 | **20** |
| `gemini-3.5-flash-lite`, `3.1-flash-lite` | **15** | 250.000 | **500** |
| `gemini-2.5-flash-lite` | 10 | — | 20 |
| `gemini-4-argon`, `3.1-pro-preview`, `2.5-pro` | 0 | 0 | **0** |
| `gemma-4` | 30 | — | 14.400 |
| `gemini-embedding-2` | — | — | 1.000 |

Reglas confirmadas en los docs oficiales:
- **No hace falta tarjeta** para el free tier. Sigue existiendo.
- Los límites son **por proyecto, no por API key** (5 keys ≠ 5× cuota).
- RPD resetea a **medianoche hora del Pacífico**.
- Alcanza con superar **cualquiera** de los tres límites para recibir `429 RESOURCE_EXHAUSTED`.
- Free tier ⇒ **Google usa tus prompts/responses para entrenar** y "human reviewers may read" el contenido. ⚠️ No metas datos de clientes.
- En EEE/CH/UK solo se permite Paid para exponer API clients a usuarios.
- Tier 1 = cuenta de facturación + **prepagá ≥ USD 5**. El crédito de USD 300 de Google Cloud **no** aplica a Gemini desde marzo 2026.

> 🚩 **Disclaimer:** la tabla de RPM/TPM/RPD **NO la pude leer de una fuente oficial** (la página real requiere sesión en AI Studio y renderiza por JS). Los valores provienen de dos artículos independientes que dicen haberlos leído en AI Studio el 21 y 22 de octubre de 2026: <https://imisofts.com/blog/gemini-api-free-tier-limits/> y <https://apidog.com/blog/gemini-api-free-tier/>. **Verificá tu cuota real en <https://aistudio.google.com/rate-limit> antes de diseñar el retry/backoff.** Los 20 RPD de 3.8-flash son dramáticos: para un asistente de uso diario, `3.5-flash-lite` (500 RPD) es la única opción viable gratis.

Fuente oficial de reglas: <https://aistudio.google.com/docs/rate-limits> · <https://aistudio.google.com/docs/pricing>

---

## A.4 Cómo se pasa la API key

```python
from google import genai

client = genai.Client(api_key="AIza...")   # 1) explícita
client = genai.Client()                    # 2) desde entorno
```

Variables de entorno que el SDK lee solo:
- `GEMINI_API_KEY` ← recomendada
- `GOOGLE_API_KEY` ← **tiene precedencia** si están las dos

```powershell
# PowerShell, persistente para el usuario
setx GEMINI_API_KEY "AIza..."
```
```python
import os
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
```

Para Vertex/Agent Platform es otro camino (`enterprise=True`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`) — no lo necesitás si usás AI Studio.

---

## A.5 Structured output

Sí, soportado, y con **dos generaciones de API** en el mismo SDK:

**Generate Content (legacy, sigue andando):**
```python
from pydantic import BaseModel
from google.genai import types

class Comando(BaseModel):
    accion: str
    parametros: dict
    confianza: float

resp = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Parseá: 'subí el fader 3 a -6 dB'",
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=Comando,      # nuevo; también existe response_schema=
    ),
)
print(resp.text)      # JSON válido garantizado
print(resp.parsed)    # instancia de Comando
```

**Interactions (nuevo):**
```python
inter = client.interactions.create(
    model="gemini-3.8-flash",
    input="Parseá: 'subí el fader 3 a -6 dB'",
    response_format={"type": "text", "mime_type": "application/json",
                     "schema": Comando.model_json_schema()},
)
print(inter.output_text)
```

### ¿Se puede combinar con function calling?
**Sí, pero solo en la familia Gemini 3** — la doc lo marca como **Preview**:
> "Gemini 3 lets you combine Structured Outputs with built-in tools, including Grounding with Google Search, URL Context, Code Execution, File Search, and **Function Calling**." — <https://aistudio.google.com/docs/structured-output#tools>

En la práctica: pasás `tools=[tool]` **y** `response_mime_type`/`response_json_schema` en el mismo `GenerateContentConfig`. En modelos 2.5 esto devolvía `400 INVALID_ARGUMENT`. **Probálo con tu modelo antes de apostar la arquitectura** (no encontré un ejemplo oficial de *generate_content* + tools + schema; el ejemplo oficial es con Interactions).

### Limitaciones del schema (importante para no pelearse)
- Subconjunto de JSON Schema: `string, number, integer, boolean, object, array, null`.
- **Se ignoran silenciosamente** (no dan error, pero no se enforcean): `minLength`, `maxLength`, `minProperties`, `maxProperties`, `uniqueItems`, `contains`, `minContains`, `maxContains`. Validá eso en tu código (Pydantic `model_validate_json`).
- Sí se enforcean: `enum`, `format` (date-time/date/time), `minimum`/`maximum`, `minItems`/`maxItems`, `required`, `additionalProperties`.
- Schemas muy anidados o con mucho branching → `400 INVALID_ARGUMENT` ("state machine too large"). Aplaná, achicá enums, usá `null` en vez de opcionales.

Fuente: <https://aistudio.google.com/docs/structured-output>

---

## A.6 Español y latencia

- **Español: excelente.** Los modelos 3.x son multilingües nativos; el rioplatense (voseo, "che", "boludo" como muletilla) se entiende bien, pero para *parsing de comandos* no confíes en la comprensión libre: usá `enum` en el schema (`accion: Literal["subir","bajar","abrir",...]`) y descripciones en español de Argentina. Los TTS de Gemini (`gemini-3.8-flash-tts`) cubren 130 idiomas y aceptan acento regional, pero son **solo pago** para tu caso práctico.
- **Latencia** — consideraciones reales:
  - El costo/latencia de salida **incluye thinking tokens**. En `gemini-3.8-flash` el thinking soporta `low|medium|high`; **`minimal` NO está soportado y devuelve error**. Para un asistente de voz, poné `ThinkingConfig(thinking_level="low")` o usá Flash-Lite (que igual tiene thinking).
  - `3.5-flash-lite` es el de menor TTFT de la familia; para comandos de 1-2 s de audio + respuesta corta es el adecuado.
  - El free tier **no garantiza capacidad** ("Specified rate limits are not guaranteed") y castiga preview/experimental.
  - Streaming (`generate_content_stream` / `chat.send_message_stream`) baja mucho la latencia percibida: emití el texto a TTS por frase, no por token.
  - No encontré cifras oficiales de TTFT por modelo para nov 2026 → **no invento números**; medí vos con `time.perf_counter()`.

---

## A.7 Historial multi-turno con function calling

### Opción 1 — `chats` (cliente-side state, la que pediste)

`chat.send_message` guarda el historial automáticamente. El truco es **devolver el function response como mensaje del chat**, no rearmar todo:

```python
from google.genai import types

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        tools=[tool],
        system_instruction="Asistente de estudio. Español rioplatense.",
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    ),
)

def turno(texto: str) -> str:
    resp = chat.send_message(texto)
    # puede haber 0, 1 o N function calls
    while resp.function_calls:
        partes = []
        for fc in resp.function_calls:
            try:
                out = DESPACHO[fc.name](**dict(fc.args))
                payload = {"result": out}
            except Exception as e:
                payload = {"error": str(e)}      # dejá que el modelo se recupere
            partes.append(types.Part.from_function_response(name=fc.name, response=payload))
        # el historial del chat ya incluye el turno 'model' con el function_call
        resp = chat.send_message(partes)
    return resp.text

print(turno("¿Qué pistas hay en el proyecto?"))
print(turno("Y cuál tiene más plugins?"))   # mantiene contexto
```

Puntos clave:
- `chat.send_message(partes)` acepta una **lista de `types.Part`**; el SDK las empaqueta con rol `user`, y el backend las interpreta como tool results porque son `function_response`.
- `chat.get_history()` devuelve `list[types.Content]` si necesitás persistirla (SQLite/JSON) y rehidratar con `client.chats.create(model=..., history=...)`.
- El historial **no se trimea solo**: en un asistente always-on vas a crecer. Cortá por turnos o por tokens (`client.models.count_tokens`).

### Opción 2 — Interactions API (estado server-side, más simple)

```python
i1 = client.interactions.create(model="gemini-3.8-flash", input="Hola, soy Dani", tools=[tool])
i2 = client.interactions.create(model="gemini-3.8-flash", input="¿Cómo me llamo?",
                                previous_interaction_id=i1.id, tools=[tool])
```
Ventaja: no reenviás historial (menos tokens, menos latencia). Desventaja: dependés de que Google guarde el estado. Doc: <https://aistudio.google.com/docs/interactions>

---

# TEMA B — Voz local en Windows 11, CPU-only

## B.1 STT offline — comparativa

| | **faster-whisper** | **whisper.cpp** | **Vosk** | **Windows nativo** |
|---|---|---|---|---|
| Paquete / binario | `faster-whisper` **1.2.1** (+ `ctranslate2` **4.8.5**) | `.zip` precompilado, código **v1.9.5** (oct 2026) | `vosk` **0.3.45** | `System.Speech` (SAPI5) / `Windows.Media.SpeechRecognition` (WinRT) |
| Licencia | MIT (código y modelos Whisper) | MIT | Apache-2.0 | propietario (parte del SO) |
| Modelo ES | `Systran/faster-whisper-{tiny,base,small,medium}` | `ggml-{tiny,base,small}.bin` | `vosk-model-small-es-0.42` | paquete de idioma "Voz" |
| Descarga | tiny ~75 MB · base ~145 MB · small ~484 MB | base ~142 MB · small ~466 MB | **~39 MB** | 0 (si ya está el pack) |
| RAM (proceso) | tiny ~300 MB · base ~0,6 GB · **small ~1,5 GB** | base ~0,6 GB · small ~1,2 GB | **~80-150 MB** | ~100 MB |
| Velocidad CPU | small int8: 13 min de audio en **1m42s** con 8 threads (i7-12700K) | small fp32: 2m05s (mismo bench) | **streaming, tiempo real holgado** | tiempo real |
| Calidad ES | **muy buena**, con puntuación y mayúsculas | muy buena (mismo modelo) | **media-baja**, sin puntuación | baja-media, depende del pack |
| Streaming | pseudo (chunks) | sí (`--stream`) | **sí, nativo por palabra** | sí |
| Python 3.14 | ✅ `ctranslate2` 4.8.5 tiene wheels cp314 | n/a (binario) | ✅ wheel `py3-none-win_amd64` | ⚠️ requiere pythonnet/winrt |

**Traducción a tu i7-8665U:** es ~2,5–3× más lento que el i7-12700K del benchmark. Esperá para `small` int8 un RTF ≈ 0,30–0,45 ⇒ **un comando de 3 s tarda ~1,0–1,4 s** en transcribir. Con `base` bajás a ~0,5–0,7 s con algo menos de precisión. Con `tiny`, ~0,3 s pero la precisión en español rioplatense se cae.

### Recomendación
**`faster-whisper` con `small` int8** para comandos cortos, y `base` si la latencia manda:

```python
from faster_whisper import WhisperModel

model = WhisperModel(
    "Systran/faster-whisper-small",   # o "small" — baja el CT2 de HF
    device="cpu",
    compute_type="int8",
    cpu_threads=4,                   # dejá 4 hilos libres para REAPER
    num_workers=1,
    download_root=r"E:\Proyecto X\.tools\models",
)

segments, info = model.transcribe(
    audio_float32_16k,               # numpy float32 mono 16 kHz
    language="es",
    beam_size=1,                     # beam 5 duplica latencia sin ganar en comandos
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=400),
    condition_on_previous_text=False, # evita alucinación en cascada
    initial_prompt="Comandos de estudio: fader, pan, bus, plugin, compresor, REAPER, "
                   "che, dale, pista, master. Español rioplatense.",
)
texto = " ".join(s.text.strip() for s in segments)
```

- `initial_prompt` es la forma barata de "sesgar" vocabulario (nombres de plugins, jerga). No es hotword boosting real, pero funciona.
- `condition_on_previous_text=False` es **clave** en comandos aislados: si no, Whisper inventa a partir del comando anterior.
- No necesita FFmpeg instalado (usa PyAV).

**Vosk** solo si el requisito es RAM <150 MB y latencia de streaming palabra-por-palabra; su precisión en rioplatense es notablemente peor y no pone puntuación. **`vosk` en PyPI no se actualiza desde dic-2022** — bandera amarilla de mantenimiento.

**Windows nativo:** `System.Speech.Recognition` (SAPI5) desde Python necesita `pythonnet`/`clr` y un `Grammar`/`Choices` cerrado (funciona bien solo para comandos fijos); `Windows.Media.SpeechRecognition` necesita el paquete `winrt-*`/`winsdk`, permiso de micrófono y el pack de voz es-ES, y **puede requerir "reconocimiento de voz online" activado**, lo que rompe el requisito offline. En esta máquina no hay pack de reconocimiento es-ES instalado (solo TTS). **No lo recomiendo.**

Fuentes: <https://pypi.org/project/faster-whisper/> · <https://github.com/SYSTRAN/faster-whisper> · <https://github.com/ggml-org/whisper.cpp/releases> · <https://huggingface.co/ggerganov/whisper.cpp> · <https://alphacephei.com/vosk/models> · <https://pypi.org/project/vosk/>

### whisper.cpp: dónde están los binarios (dato fino)
La release **v1.9.5 no trae assets**. Los `.zip` precompilados (`whisper-bin-x64.zip`, `whisper-bin-win-cpu-arm64.zip`, `whisper-blas-bin-x64.zip`) se publican en el **tag nightly** (ej. `b5454`, 6-oct-2026). Verificado vía GitHub API: `v1.9.5 → assets=0`, `b5454 → assets=12`. Descargá de <https://github.com/ggml-org/whisper.cpp/releases> eligiendo el tag nightly, no la release "bonita".

---

## B.2 VAD para "siempre escuchando"

| | `silero-vad` | `webrtcvad` | `faster-whisper` `vad_filter` |
|---|---|---|---|
| Paquete | **`silero-vad` 6.2.3** (+ `silero-vad[onnx-cpu]`) | `webrtcvad-wheels` **2.0.14.post1** (el `webrtcvad` original 2.0.10 **no tiene wheels**) | incluido |
| Licencia | **MIT** | MIT | MIT |
| Modelo | ~2 MB | reglas DSP, 0 MB | Silero embebido |
| CPU | **<1 ms por chunk de 30 ms en 1 thread** | ~0,1 ms | n/a (offline) |
| Sample rate | 8k / 16k | 8/16/32/48k, frames de 10/20/30 ms | — |
| Para streaming | ✅ | ✅ | ❌ (solo recorta silencios >2 s en batch) |

**Recomendación:** `silero-vad` en ONNX (sin torch), ventana de 512 samples @16 kHz, `threshold=0.5`, `min_silence_duration_ms=500`, `speech_pad_ms=100`. Es el estándar de facto y no te come CPU mientras REAPER procesa.

```python
# pip install "silero-vad[onnx-cpu]"   (igual necesita torch>=1.12 como base)
import torch
from silero_vad import load_silero_vad, VADIterator
vad = load_silero_vad(onnx=True)
it = VADIterator(vad, threshold=0.5, sampling_rate=16000,
                 min_silence_duration_ms=500, speech_pad_ms=100)
# por cada frame de 512 muestras int16→float32:
evento = it(torch.from_numpy(frame))   # {'start': n} / {'end': n} / None
```

No uses `webrtcvad` para esto: es más frágil con ruido de fondo y no distingue bien música de voz (relevante en un estudio). Sí es útil como pre-filtro ultraliviano si ni siquiera querés cargar ONNX.

---

## B.3 Wake word offline

| | `openWakeWord` | `pvporcupine` (Picovoice) | Casero VAD+Whisper |
|---|---|---|---|
| Versión | **0.6.0** (feb-2024, sin updates) | **4.0.3** (motor v4.0.0, dic-2025) | — |
| Código | Apache-2.0 | propietario | tuyo |
| **Modelos preentrenados** | **CC-BY-NC-SA 4.0 ⇒ NO comercial** | licencia Picovoice | — |
| Access key | ❌ no | ✅ **sí, obligatoria** (Console) | ❌ |
| Español | ❌ **solo inglés** | ✅ **sí, soporta es** | ✅ |
| CPU | ~1 core liviano | muy liviano | caro (corrés Whisper siempre) |

**La letra chica que importa:**
- openWakeWord: el **código** es Apache-2.0, pero los modelos vienen **CC BY-NC-SA 4.0** ("due to the inclusion of datasets with unknown or restrictive licensing"). **No podés distribuirlo comercialmente.** Y los modelos son de frases en inglés (`alexa`, `hey jarvis`, `hey mycroft`…). Podés entrenar el tuyo (su pipeline usa TTS, mayormente inglés) — es tu única vía limpia.
- pvporcupine: requiere `access_key`. El free tier de Picovoice es para uso personal/no comercial; para distribuir hay que licenciar. **No pude verificar los términos exactos vigentes de la licencia** (la página de pricing de Picovoice no la pude leer); asumí que comercial ⇒ pago y confirmá en <https://picovoice.ai/pricing/>.

**Recomendación práctica:**
- **Uso personal en tu máquina:** `pvporcupine` con keyword español desde la Console. Es el más preciso, el más liviano y el único con español listo. Cuesta una access key gratis.
- **Si vas a distribuir:** entrená un modelo propio de openWakeWord (evitando los .onnx/tflite preentrenados) o comprá licencia Porcupine.
- **Ojo con la frase:** "che" es monosílabo y acústicamente pobre para detección. Usá 2–3 sílabas: *"che asistente"*, *"hola máquina"*, *"dale loco"* (esta última va a dar falsos positivos). Y siempre VAD antes del wake word para no correr el detector 24/7.

Fuentes: <https://pypi.org/project/openwakeword/> · <https://github.com/Picovoice/porcupine>

---

## B.4 TTS offline

### Lo que REALMENTE hay en esta máquina (medido, no supuesto)

```
SAPI5 (System.Speech / SAPI.SpVoice):
  Microsoft Zira Desktop   | en-US | Female
  Microsoft Helena Desktop | es-ES | Female      ← la única en español

OneCore (Windows.Media.SpeechSynthesis, WinRT):
  Microsoft Helena - Spanish (Spain)
  Microsoft Laura  - Spanish (Spain)
  Microsoft Pablo  - Spanish (Spain)
```

**Respuesta directa a tu pregunta:** Windows 11 **no** trae "Helena, Laura, Sabina y Pablo" por defecto. Trae lo que corresponda al **pack de idioma instalado**. En tu caso (es-ES instalado, es-MX no) tenés Helena/Laura/Pablo en OneCore y **solo Helena Desktop en SAPI5**. **Sabina y Raúl son es-MX** y aparecen recién si agregás *Español (México)* en Configuración → Hora e idioma → Idioma y región → Agregar idioma, con la característica **Voz** tildada.

Diferencia clave: los sufijos **"Desktop"** son las voces SAPI5 viejas (concatenativas, robóticas). Las **OneCore/"Mobile"** (Helena, Laura, Pablo sin sufijo) son mejores pero **no las ve SAPI5/`pyttsx3` directamente**; se usan vía WinRT (`Windows.Media.SpeechSynthesis.SpeechSynthesizer`).

### Cómo usarlas desde Python

**Opción A — SAPI5 con comtypes (menor latencia, sin capas):**
```python
import comtypes.client as cc
voice = cc.CreateObject("SAPI.SpVoice")
for v in voice.GetVoices():
    print(v.GetDescription())          # "Microsoft Helena Desktop - Spanish (Spain)"
voice.Voice = voice.GetVoices()["Microsoft Helena Desktop"]
voice.Rate = 0                          # -10..10
voice.Speak("Listo, abriendo el proyecto.")          # async
voice.WaitUntilDone(10_000)                          # ms
```
Latencia de arranque: **~50–150 ms**. Calidad: robótica pero inteligible.

**Opción B — `pyttsx3` 2.99 (MPL-2.0):** wrapper multiplataforma sobre SAPI5. Más cómodo (`engine.say()` + `runAndWait()`), pero **`runAndWait()` bloquea y no se lleva bien con asyncio/hilos**; para un asistente siempre-escuchando vas a pelear con el loop. Preferí comtypes para producción.

**Opción C — OneCore por WinRT** (para usar Laura/Pablo, mejor calidad):
```python
# pip install winrt-runtime winrt-Windows.Media.SpeechSynthesis winrt-Windows.Storage.Streams
import asyncio
from winrt.windows.media.speechsynthesis import SpeechSynthesizer

async def decir(texto: str):
    synth = SpeechSynthesizer()
    synth.voice = SpeechSynthesizer.all_voices[2]     # filtrar por .display_name / .language
    stream = await synth.synthesize_text_to_stream_async(texto)
    ...
```
⚠️ Requiere Windows 11 + paquetes `winrt-*`; **no verifiqué que haya wheels para Python 3.14** — es el punto más frágil.

### Alternativas de más calidad

| Motor | Paquete / versión | Licencia | Voces ES | Tamaño | Latencia | Veredicto |
|---|---|---|---|---|---|---|
| **Piper** | `piper-tts` **1.8.0** | **GPL-3.0-or-later** ⚠️ | `es_ES-davefx-medium`, `es_ES-sharvard-medium`, `es_MX-ald-medium`, `es_MX-claude-high` | ~63 MB/voz (onnx) + json | ~100–300 ms al primer chunk, RTF <0,1 en CPU | **mejor calidad/latencia offline**; GPL contaminante si distribuís |
| **Kokoro** | `kokoro` **0.9.4** | Apache-2.0 | voces `ef_dora`, `em_alex`, `em_santa` | ~330 MB (arrastra torch) | 0,5–1 s (torch en CPU) | calidad muy buena, pero pesado para 16 GB con REAPER abierto |
| **edge-tts** | `edge-tts` **7.3.1** | ⚠️ **sin licencia clara** | `es-AR-ElenaNeural`, `es-AR-TomasNeural` (¡rioplatense nativo!) | 0 | 300–800 ms (red) | **online**, no offline; usa el servicio de lectura de Edge sin contrato ⇒ riesgo de ToS y de que corte. **No para producto.** |
| SAPI5 | SO | propietario | Helena Desktop | 0 | 50–150 ms | fallback gratis |

**Recomendación:** Piper con `es_AR`/`es_MX` si el proyecto es personal o GPL-compatible; si necesitás licencia permisiva y distribuible, **Kokoro (Apache-2.0)** o SAPI5 Helena. Las voces `es-AR-ElenaNeural` / `es-AR-TomasNeural` de edge-tts son las que mejor suenan en rioplatense, pero atarte a un servicio no documentado para un asistente local es mala idea.

Fuentes: <https://pypi.org/project/piper-tts/> · <https://github.com/OHF-Voice/piper1-gpl> · <https://huggingface.co/rhasspy/piper-voices> · <https://pypi.org/project/pyttsx3/> · <https://github.com/rany2/edge-tts>

---

## B.5 Captura de micrófono y el conflicto con ASIO/REAPER

### `sounddevice` vs `pyaudio`

| | `sounddevice` **0.5.6** | `PyAudio` **0.2.14** |
|---|---|---|
| Licencia | MIT | MIT |
| Base | PortAudio (DLL incluida en el wheel) | PortAudio (compilado) |
| **Wheel para Python 3.14** | ✅ `py3-none-any` (anda ya) | ❌ **no hay cp314** → intenta compilar y falla sin MSVC+PortAudio |
| API | numpy directo, `RawInputStream`, callbacks | bytes, `stream.read()` |
| WASAPI settings | `sd.WasapiSettings(exclusive=False)` | `paWasapiStreamInfo` |

**Usá `sounddevice`.** En tu Python 3.14.6, PyAudio es directamente un problema de instalación.

### El problema real del ASIO (esto es lo importante)

Verificado en tu máquina con `sd.query_hostapis()`:

```
0 MME             devices=4
1 Windows DirectSound devices=4
2 Windows WASAPI  devices=2
3 Windows WDM-KS  devices=8
```

**No aparece ASIO.** El wheel de PortAudio que viene con `sounddevice` se compila **sin el SDK de ASIO** (Steinberg no permite redistribuirlo). Conclusión dura: **desde Python no podés abrir el driver ASIO en absoluto** — ni para compartir ni para tomar el dispositivo.

Y el conflicto es peor de lo que parece:

1. Un driver **ASIO abre la interfaz en modo exclusivo a nivel kernel**, salteándose por completo el *Windows Audio Engine* (WASAPI).
2. Cuando REAPER tiene la interfaz tomada por ASIO, cualquier intento de abrir **ese mismo endpoint físico** por WASAPI shared falla con `AUDCLNT_E_DEVICE_IN_USE` (PortAudio lo suele reportar como `PaErrorCode -9996` "Invalid device" o `-9999` "Unanticipated host error"), **o peor: abre y devuelve silencio**.
3. **No hay checkbox de Windows que lo arregle.** El "Permitir que las aplicaciones tomen control exclusivo" del panel de sonido aplica a WASAPI, no a ASIO. ASIO ni pasa por ahí.
4. Los drivers ASIO **single-client** (la mayoría, incluido el RTHDASIO64 de Roland) además rechazan un segundo cliente ASIO. Los multi-client (RME, algunos Focusrite) permiten 2+ apps ASIO, pero **eso no habilita WASAPI** sobre el mismo device.

**Soluciones, ordenadas por practicidad:**

1. **✅ Usar otro dispositivo físico para el asistente (lo que yo haría).** Tu máquina tiene el array de micrófonos Realtek en WASAPI (48 kHz, 2 ch) — verificado en `sd.query_devices()`, device `#9 "Varios micrófonos (Realtek(R) Audio)"`. REAPER se queda con la interfaz ASIO; el asistente escucha por el micrófono onboard. Cero conflicto, cero latencia agregada, cero riesgo.
   ```python
   import sounddevice as sd
   sd.default.device = (9, None)   # (input, output) — ajustá con sd.query_devices()
   ```
2. **Cambiar REAPER a WASAPI shared** cuando usás el asistente. Perdés latencia baja (sube a ~10–30 ms) pero Windows puede mezclar y el asistente comparte el device. Inviable si estás grabando.
3. **Dispositivo virtual** (VB-Audio Cable / VoiceMeeter): sirve para *routing* de la salida del TTS, pero **no captura la interfaz ASIO**. No resuelve el micrófono.
4. **Salida de audio del asistente por la placa onboard**, no por la interfaz. Si el TTS sale por el mismo device ASIO, vas a tener el mismo problema al reproducir.

### Snippet de captura robusta (WASAPI shared, 16 kHz)

```python
import sounddevice as sd, numpy as np, queue

q: queue.Queue[np.ndarray] = queue.Queue()

def cb(indata, frames, time_info, status):
    if status:
        print("audio status:", status)     # input overflow típico si el loop se traba
    q.put(indata[:, 0].copy())             # mono float32

def main():
    stream = sd.InputStream(
        samplerate=16000,                  # una sola palabra, sin guión bajo
        channels=1,
        dtype="float32",
        blocksize=512,                     # 32 ms @16k → frame ideal para Silero
        device=9,
        extra_settings=sd.WasapiSettings(exclusive=False),   # clave: shared
        callback=cb,
    )
    with stream:
        while True:
            frame = q.get()                # 512 float32
            # 1) VAD barato primero
            # 2) solo si hay utterance, acumular y mandar a Whisper
```

Dos trampas concretas:
- El nombre del parámetro es `samplerate=` (una sola palabra). `sample_rate=` tira `TypeError`.
- **No abras el stream a 44.1 kHz para después resamplear en Python.** Pedile 16 kHz directo a WASAPI: en tu Realtek el mix del driver está a 48 kHz, así que la conversión la hace el driver en C, no tu loop en Python.
- `sd.WasapiSettings(exclusive=False)` es obligatorio; el default de WASAPI en PortAudio puede negociar exclusivo y ahí perdés el device.

### Presupuesto de CPU/RAM en esta máquina

| Componente | CPU | RAM |
|---|---|---|
| Silero VAD ONNX (idle) | ~2-3 % de 1 core | ~50 MB |
| faster-whisper `small` int8 (durante 3 s de audio) | ~250-300 % (4 threads) por ~1,2 s | ~1,5 GB |
| faster-whisper `base` int8 | ~200 % por ~0,6 s | ~0,7 GB |
| Piper TTS (síntesis de una frase) | ~60 % por ~0,3 s | ~200 MB |
| **Total en reposo** | **<5 %** | **~300 MB** |

Con 16 GB y REAPER abierto, `small` entra cómodo. Si REAPER está renderizando, bajá a `base` o poné `cpu_threads=2`.

---

## 0-bis. Stack recomendado (resumen ejecutivo)

```
Wake word   : pvporcupine (es, access key gratis)   ·o· openWakeWord con modelo propio si distribuís
VAD         : silero-vad 6.2.3 ONNX, 16 kHz, 512-sample frames
STT         : faster-whisper 1.2.1 + Systran/faster-whisper-small (int8, cpu_threads=4, language="es")
LLM         : google-genai 3.0.0 → gemini-3.5-flash-lite (500 RPD gratis; 3.8-flash solo 20 RPD)
TTS         : Piper 1.8.0 es_AR/es_MX (GPL) ·o· SAPI5 "Microsoft Helena Desktop" (0 descarga)
Audio I/O   : sounddevice 0.5.6, WASAPI shared, device = mic onboard Realtek (NO el device de REAPER)
Python      : 3.14.6 funciona, pero si podés creá un venv 3.12 para STT/TTS (más wheels disponibles)
```

---

## 1. Lo que NO pude verificar (leé esto antes de confiar)

| Afirmación | Estado |
|---|---|
| RPM/TPM/RPD exactos del free tier | 🚩 **Solo fuentes terciarias** (imisofts, apidog, 21-22 oct 2026). Los docs oficiales ya no publican la tabla. Verificá en `aistudio.google.com/rate-limit`. |
| `generate_content` + `tools` + `response_schema` en la misma request | 🚩 Documentado **solo para la Interactions API** y marcado *Preview* para Gemini 3. No encontré ejemplo oficial en el path legacy. **Probalo con un request real antes de diseñar alrededor.** |
| Precios/TTL de Picovoice free tier | 🚩 No pude abrir la página de pricing; asumí no-comercial. Confirmá en picovoice.ai. |
| Términos exactos de edge-tts | 🚩 El paquete no declara licencia en PyPI; usa un servicio de Microsoft sin contrato. Tratalo como no apto para producción. |
| Nombres exactos de voces Piper `es_*` | 🚩 Los tomé de memoria del repo `rhasspy/piper-voices`; verificá el listado en HuggingFace antes de hardcodear. |
| Wheels de `winrt-*` para Python 3.14 | 🚩 No verificado. Si falla, quedate en SAPI5/comtypes. |
| `openwakeword` 0.6.0 sobre numpy 2.5 / Python 3.14 | 🚩 No probado; el paquete es de feb-2024 y depende de onnxruntime + scipy. Alto riesgo de incompatibilidad. |
| TTFT / latencia por modelo Gemini | 🚩 No hay cifras oficiales públicas en nov 2026. Medí. |
| Que `piper-tts` 1.8.0 tenga wheel para cp314 | 🚩 PyPI mostró `py3-none-any` (pure Python + onnxruntime), así que *debería* andar, pero no lo instalé. |

## 2. Fuentes principales

**Gemini API**
- <https://pypi.org/project/google-genai/> · <https://github.com/googleapis/python-genai> · <https://googleapis.github.io/python-genai/>
- <https://aistudio.google.com/docs/models> · <https://aistudio.google.com/docs/pricing> · <https://aistudio.google.com/docs/rate-limits>
- <https://aistudio.google.com/docs/function-calling> · <https://aistudio.google.com/docs/structured-output> · <https://aistudio.google.com/docs/interactions>
- <https://aistudio.google.com/llms.txt>
- Terceros (límites free tier): <https://imisofts.com/blog/gemini-api-free-tier-limits/> · <https://apidog.com/blog/gemini-api-free-tier/>

**Voz local**
- <https://pypi.org/project/faster-whisper/> · <https://github.com/SYSTRAN/faster-whisper>
- <https://github.com/ggml-org/whisper.cpp/releases> · <https://huggingface.co/ggerganov/whisper.cpp>
- <https://alphacephei.com/vosk/models> · <https://pypi.org/project/vosk/>
- <https://pypi.org/project/silero-vad/> · <https://github.com/snakers4/silero-vad>
- <https://pypi.org/project/webrtcvad-wheels/>
- <https://pypi.org/project/openwakeword/> · <https://github.com/Picovoice/porcupine>
- <https://pypi.org/project/piper-tts/> · <https://huggingface.co/rhasspy/piper-voices>
- <https://pypi.org/project/pyttsx3/> · <https://github.com/rany2/edge-tts>
- <https://pypi.org/project/sounddevice/> · <https://python-sounddevice.readthedocs.io/>
