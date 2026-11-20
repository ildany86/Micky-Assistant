# Voz y audio

Todo el audio se procesa en tu computadora. La nube solo recibe texto… y ahora
también devuelve la voz de respuesta (opcional, se puede usar la voz local).

```
micrófono ──► VAD ──► segmento de voz ──► faster-whisper ──► texto
                                                              │
                                                     palabra clave «Miky»
                                                              │
                                                          comando
                                                              │
                                             ┌────────────────▼───────────────┐
                                             │ motor + IA + puente → REAPER   │
                                             └────────────────┬───────────────┘
                                                              │
                                     voz online (Tomás) ◄─────┤
                                     o voz local (SAPI) ──────┘
```

## Componentes

| Etapa | Tecnología | Dónde corre | Consumo medido |
|---|---|---|---|
| Captura | `sounddevice` (PortAudio, WASAPI) | local | ~1 % CPU |
| Detección de voz | Silero VAD por ONNX (2 MB) | local | 0,24 ms por bloque de 32 ms |
| Reconocimiento | `faster-whisper` `base` int8 + hotwords | local, CPU | ~1,7 s por cada 4 s de audio |
| Diálogo | Gemini (u otra API) | nube | ~300–900 ms |
| Respuesta | `edge-tts` (voz argentina) con respaldo SAPI5 | nube + local | ~1,8 s de síntesis, reproducción inmediata |

## El micrófono: qué elige y por qué

Este fue el punto que más problemas trajo en la primera prueba, así que quedó
blindado:

1. **Nunca se eligen los pseudo-dispositivos de Windows** («Asignador de sonido»,
   «Controlador primario», «Mezcla estéreo», «Sound Mapper»). No son dispositivos
   reales: redirigen al predeterminado del sistema, que normalmente es la
   interfaz. Elegirlos hacía que Miky escuchara por la iD14 aunque hubiera un
   micrófono interno disponible. Ahora se filtran de la lista y, si una
   configuración vieja los tenía guardados, se descartan al cargar.
2. **Preferencia por el micrófono interno**: entre los dispositivos WASAPI, gana
   el que tiene «realtek», «micrófono» o «mic» en el nombre.
3. **Reintento automático**: si el dispositivo elegido no abre (por ejemplo,
   porque REAPER lo tomó por ASIO), Miky prueba automáticamente el siguiente
   candidato en vez de quedarse sordo.
4. **Selección manual** en Ajustes → *Micrófono*, con la lista completa.

### El conflicto con ASIO

Si REAPER usa tu interfaz por **ASIO**, el driver la toma en exclusiva a nivel
del sistema y Windows no la comparte. Desde Python ni siquiera se puede abrir
ese dispositivo (PortAudio no trae ASIO en los paquetes de Python).

Por eso el asistente usa el micrófono interno de la notebook (WASAPI) y la placa
queda dedicada al DAW. Es la única combinación estable mientras grabes con la
interfaz.

Si querés usar el micrófono de la interfaz para hablarle a Miky, tenés que
configurar REAPER con WASAPI compartido (perdés latencia baja) o conectar un
micrófono al equipo. No hay forma de compartir un dispositivo ASIO exclusivo.

## Reconocimiento (STT)

- Modelo por defecto: `Systran/faster-whisper-base` (~145 MB). En un i7 de octava
  generación tarda **~1,7 s** por una frase de 4 s: es el punto de equilibrio
  para hablarle.
- `small` (~484 MB) entiende mejor, pero en este procesador tarda **~5,6 s** por
  la misma frase: se puede activar en la config (`stt_model = "small"`) si
  preferís precisión a velocidad.
- **Hotwords**: antes de transcribir, Miky le pasa al modelo los nombres reales
  de tus pistas (`Guitarra`, `Batería`, `Bombo`…) **más tu vocabulario propio**
  (`voice.vocabulary`): marcas de plugins, nombres de proyectos, siglas. Así
  «Eamut» no se transcribe como «e amut» y los nombres propios salen bien.
- `beam_size=5` (más preciso), `condition_on_previous_text=False` para que no
  invente a partir de la orden anterior, y un prompt inicial con jerga de estudio.
- Forzado a español.

**Decodificación**: por defecto `beam_size=1` (greedy). Con `beam_size=5`
el texto sale un poco mejor pero tarda el doble; en una frase de 4,8 s medí
1,4 s contra 3,8 s. Para un asistente que responde al instante, velocidad gana.

**Transcripción especulativa**: cuando la frase lleva 180 ms de silencio, Miky
empieza a transcribir mientras el VAD todavía espera para cerrar (550 ms). Si
seguís hablando, se descarta; si no, el texto ya está listo. Ahorra ~0,37 s por
orden y no se activa mientras REAPER está grabando (el CPU es del DAW).

Medición propia (frase de 3,85 s, i7-8665U, CPU, int8):

| Configuración | Tiempo de transcripción |
|---|---|
| `base` + beam 1 | 1,38 s |
| `base` + beam 5 | 1,70 s |
| `small` + beam 1 | 6,16 s |
| `small` + beam 5 | 5,64 s |

## Detección de voz (VAD)

El umbral de voz (`voice.vad_threshold`, por defecto 0,5) decide cuándo empieza una
frase. Subirlo a 0,60–0,65 evita que la música o un video abran segmentos; si el
asistente "no te escucha" cuando hablás bajo, bajalo a 0,45.

Silero VAD corre sobre `onnxruntime` con el modelo de 2 MB, sin `torch`. Cierra
la frase tras ~550 ms de silencio y descarta segmentos de menos de 220 ms. Si el
modelo no está, cae a un detector por energía.

## Palabra de activación

En modo `always`, Miky escucha pero **solo actúa si lo nombrás**. «Miky» no es una
palabra del español, así que el transcriptor la escribe de muchas formas. Por eso
la detección combina tres cosas:

1. **Lista de variantes** de lo que realmente devuelve el reconocimiento:

   ```
   miky · miki · miqui · micki · mickey · mikey · mike · mig · miggy · migui
   viki · viky · viqui · biki · biqui · niki · bigui · maiki · mayki · miqi
   ```

   (La «v» y la «b» aparecen porque en español suenan igual, y la «m» inicial se
   confunde con «v» cuando el audio es corto.)

2. **Distancia de edición 1**: si la primera palabra se parece a «miky» con una
   sola letra de diferencia, cuenta igual. Así entra cualquier forma nueva sin
   tener que listarla.

3. **Cuidado con el prompt**: el nombre *no* se agrega al prompt inicial ni a las
   hotwords del modelo. Se probó y pasa lo contrario de lo esperado: Whisper lo
   interpreta como texto ya dicho y lo **borra** de la transcripción («crea una
   pista…» sin «Miky»), con lo que la palabra clave nunca se detecta. Por eso la
   tolerancia se resuelve después, al comparar el texto.

Prefijos aceptados: «hola», «che», «oye», «ey», «dale», «ok», «okey», «bueno»,
«escuchá», «atendé». Decir **«Ok Miky, …»** o **«Che Miky, …»** ayuda: la palabra
extra le da al modelo más contexto antes del nombre.

Cuando lo detecta, suena un **aviso corto** (se puede apagar en Ajustes) y el
ícono se pone celeste brillante. Si decís solo «Miky», espera la orden siguiente.
Si decís «Miky, grabá», ejecuta en el momento.

## Cómo se pronuncian las palabras

La voz es rioplatense, así que lee «REAPER» como palabra española. Antes de
sintetizar, Miky reemplaza las palabras problemáticas por su escritura fonética:

| Se escribe | Se dice |
|---|---|
| `REAPER` | «Ríper» |
| `Miky` | «Miki» |

## Acciones largas: render y grabación

Un render bloquea a REAPER mientras dura (es una única llamada de script), así
que Miky **no puede atenderte en el medio**. Para que no quedes esperando a
oscuras:

1. Antes de arrancar dice **«Renderizando. Esto puede tardar; no voy a poder
   atenderte hasta que termine.»**
2. Si igual le hablás, responde al instante que está ocupado y que, si querés
   cortarlo, lo canceles en la ventana de REAPER.
3. Al terminar avisa **«Listo, terminó el render.»**

Lo mismo vale para grabaciones largas.

## Interrumpir a Miky (barge-in)

Si le hablás mientras está respondiendo, **se calla y te escucha**. Para eso se
mide el nivel del micrófono mientras habla: tiene que sostenerse ~260 ms por
encima de `voice.barge_in_level` (0,12 por defecto) para cortar la respuesta, así
no la corta un golpe de mesa ni un pico del propio audio.

Después de interrumpirlo, la frase que sigue se toma como una orden **sin
necesidad de la palabra clave**, porque ya estaba hablándole a él.

Si Miky se corta solo (el audio de los parlantes entra al micrófono), subí
`barge_in_level` o poné `barge_in = false`.

## Corrección de la transcripción

Whisper inventa las palabras que no conoce: marcas, nombres de pistas, siglas. Antes
de interpretar, Miky corrige dos cosas:

1. **Vocabulario propio** (`voice.vocabulary`): «e amut», «eamoot», «EAMOOT» y
   «monitorcorrect» terminan todos en «Eamut» y «MonitorCorrect».
2. **Correcciones explícitas** (`voice.corrections`), pares `mal=bueno` para lo que
   la difusa no adivina.

La comparación es por palabra (o dos o tres juntas) y nunca se come palabras
vecinas: «subí la bateria» se corrige a «subí la Batería» sin perder el «subí».

## Respuesta hablada

Hay dos motores y se elige en Ajustes → *Motor*:

| Motor | Voz | Requiere internet | Ventaja |
|---|---|---|---|
| **Online (recomendado)** | `es-AR-TomasNeural` — hombre, argentino | sí | la más natural y con acento local |
| Local de Windows | SAPI5 (Helena, español de España) | no | funciona sin conexión |

El motor online se sintetiza con `edge-tts` y se reproduce por el dispositivo que
elijas en Ajustes → *Salida*. Si falla (sin internet, servicio caído), **cae solo
a la voz local** y lo deja anotado en el log: nunca te quedás mudo.

En la lista de voces online están Tomás y Elena (Argentina), Jorge y Dalia
(México), Álvaro y Elvira (España) y Mario (Paraguay).

Las respuestas no las redacta la IA: se arman con plantillas locales a partir del
resultado real de cada comando. Eso ahorra cuota, evita latencia extra y hace
que Miky diga exactamente lo que pasó («Puse Batería en -4 dB»).

### Hablar poco: modo de respuesta

En Ajustes → *Respuesta* hay tres modos:

| Modo | Qué hace |
|---|---|
| **Mixto** (recomendado) | Suena un aviso corto cuando salió bien; habla solo si hubo un error, una pregunta o un consejo |
| **Solo sonidos** | Nunca habla resultados: solo sonidos. Habla únicamente preguntas y consejos |
| **Todo hablado** | Dice cada resultado (el comportamiento clásico) |

Son dos sonidos distintos: uno que sube (`ok`) y uno que baja (`error`). Y el ícono
acompaña: **«?» violeta** mientras piensa o ejecuta, **«!» rojo** si algo falló.

## Confirmaciones

Las acciones que no se deshacen con Ctrl+Z piden confirmación por voz («sí»,
«dale», «no», «cancelá») o con los botones que aparecen al lado del ícono. Si no
hay respuesta en 12 segundos, se cancela.

### Grabar pregunta primero

Grabar es el único caso donde el orden importa: si Miky dijera «Grabando» con la
toma ya corriendo, su voz quedaría dentro del audio.

El flujo es:

1. Se ejecutan los pasos previos (por ejemplo activar el metrónomo) y Miky lo
   comenta.
2. Pregunta **«¿Estás listo para grabar?»** y espera.
3. Cualquier respuesta positiva («sí», «dale», «listo», «vamos») **arranca la
   grabación en silencio**: no dice nada más.
4. Cualquier negativa («no», «pará», «dejá») cancela todo: no se graba nada.

Se puede desactivar con `safety.ask_before_record = false` en la configuración.

## Seguir hablando sin repetir «Miky»

Después de que Miky responde, queda escuchando **8 segundos** sin exigir la
palabra clave: podés encadenar «activá el metrónomo» y «dale, grabemos» en dos
frases seguidas. Pasado ese tiempo vuelve a pedir «Miky».

Se ajusta con `voice.follow_up_seconds` (0 lo desactiva).

## Tus favoritos mandan

REAPER tiene una carpeta **Favoritos** en el explorador de plugins. Miky la lee
(de `reaper-fxfolders.ini`) y la usa como primera opción:

1. Si pedís «un compresor» y hay **un solo favorito** que coincide, lo carga sin
   preguntar.
2. Si hay **varios**, te ofrece esos.
3. Si no hay ninguno, busca en todos los plugins instalados como siempre.

Los favoritos marcados que ya no están instalados se avisan: «los marcados no están
instalados: Eamut Drums Compressor».

## Medir la precisión

`tools/voice_accuracy.py` sintetiza 20 frases reales, las transcribe con el
modelo de verdad y mide dos cosas: el error de palabra (WER) y, sobre todo, el
**porcentaje de frases que terminan en el comando correcto**.

```powershell
.venv\Scripts\python.exe tools\voice_accuracy.py            # voz real (edge)
.venv\Scripts\python.exe tools\voice_accuracy.py --engine sapi  # sin internet
```

Línea base medida en esta máquina (beta 0.2):

| | Antes | Después de tolerar conjugaciones |
|---|---|---|
| Comando correcto | 60 % (12/20) | **90 % (18/20)** |
| WER | 22,5 % | ~28 %* |
| Reconocimiento | 1,44 s | **1,2–1,4 s** |

\* El WER sube porque se mide el texto crudo; lo que importa es el comando.
Whisper normaliza los imperativos («poné» → «pone», «grabá» → «graba») y el
router ahora acepta esas formas, más las erratas típicas («12b», «paniala»,
«abril a matriz»).

## Elegir entre varios plugins

Cuando pedís algo como «un compresor» y hay varios candidatos, Miky busca en la
lista real de plugins instalados y **te ofrece las opciones numeradas**:

> «Encontré 5: 1, Compciter; 2, 1175 Compressor; 3, ReaComp; 4, ReaXcomp;
> 5, VComp Mono. ¿Cuál querés?»

Respondés «el 3» o «el del SSL» y lo carga. Si la descripción es específica
(«compresor estilo bus de SSL») y hay un solo candidato, lo carga directo.

## Latencia esperada

Medición con `miky bench` (mediana de 3): reconocimiento 1,5 s para 4,8 s de
audio, IA 0,88 s con 2.084 tokens de entrada, síntesis 1,1 s (0 si está en caché).

| Escenario | Tiempo hasta la acción |
|---|---|
| Comando directo («dale», «subí el bajo 2 dB») | ~2–3 s |
| Orden con IA (una consulta a Gemini) | ~3,5–4,5 s |
| Ejecución en REAPER por comando | 15–60 ms |

El reconocimiento es el tramo más lento (~1,7 s). El cuello de botella es la CPU:
con `base` ya está en el límite razonable para hablar; `small` duplica la espera.

## Problemas típicos

| Síntoma | Causa probable | Solución |
|---|---|---|
| El ícono late pero no ejecuta nada | el VAD no cierra el segmento o el micrófono está muy bajo | mirar el log: por cada frase tiene que aparecer `escuché: …`. Si no aparece, `miky listen` muestra el estado en vivo |
| Escucha por la interfaz y no por la notebook | configuración vieja con «Asignador de sonido» | Ajustes → Micrófono → «Automático» |
| No me escucha nunca | dispositivo tomado por REAPER | cambiar de micrófono; ver arriba |
| Transcribe mal | modelo `base` o ruido | poner `stt_model = "small"` |
| Habla con voz de mujer | motor en «Local de Windows» | Ajustes → Motor → «Online · español argentino» |
| No habla | sin internet y sin voces SAPI en español | instalar el paquete de voz del idioma |
| Habla pero no lo escucho | la salida elegida no es la que usás para monitorear | Ajustes → Salida → «Predeterminada» (o la interfaz) y «Probar voz» |
| Corta la primera palabra | segmentación agresiva | subir `silence_ms` a 800–900 |
| Se come la orden después de «Miky» | hablaste muy rápido | decí «Miky» y esperá el aviso |
