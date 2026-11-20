# Conocimiento técnico

Miky aconseja sobre mezcla, dinámica, EQ y grabación. Un modelo de lenguaje
sabe mucho del tema, pero **inventa los números** cuando es chico y rápido: dice
«cortá alrededor de 1 kHz» donde la respuesta útil es «250–400 Hz, Q 2–4».

Este documento explica cómo se le da sustento técnico a los consejos sin
entrenar un modelo ni pagar una base vectorial.

## Cómo funciona

1. Cuando el pedido **es una consulta de criterio** («¿cómo ecualizo la voz
   para que no suene nasal?», «¿esto está bien comprimido?»), Miky busca entre
   sus **fichas** las dos más relevantes.
2. Esas fichas viajan en el contexto (`knowledge`) y la IA tiene la orden de
   apoyarse en esos datos y no inventar otros.
3. En pedidos de acción («subí el bajo 2 dB») **no se manda nada**: no gasta
   tokens ni cambia el comportamiento.

La búsqueda es por palabras clave y raíces, sin dependencias ni modelos
extra (`src/miky/knowledge.py`), y tarda microsegundos.

## Leer la sesión real

Una ficha dice qué es lo normal; para opinar sobre *tu* mezcla hace falta ver
qué tenés cargado y **cómo está ajustado**. Para eso está `fx.params`, que lee
los parámetros reales de los plugins de una pista:

```
fx.params {track: "Voz", limit: 10}
→ Voz › VST: ReaComp (Cockos)
    Threshold -18.0 dB · Ratio 8.0 · Attack 1 ms · Release 100 ms · …
```

Cuando el pedido es una consulta de criterio, la app pide sola los parámetros de
hasta dos pistas (primero la seleccionada) y los manda en `fx_settings`. Con eso
la respuesta deja de ser genérica:

> «Tenés el compresor en 8:1 con ataque de 1 ms y 6 dB de reducción: probá
> 3:1 y 15 ms, que es lo que pide una voz.»

Límites a propósito: 10 parámetros por plugin, 2 plugins por pista y 2 pistas.
Así el contexto no se infla y la latencia no se nota (la lectura tarda ~30 ms).

## Niveles: el balance real

`levels.get` lee el **medidor** de cada pista y del master (`Track_GetPeakInfo`)
y lo entrega en dBFS:

```json
{
  "playing": true,
  "master": {"peak_db": -1.9},
  "tracks": [
    {"name": "Voz", "peak_db": -6.0},
    {"name": "Batería", "peak_db": -18.1}
  ]
}
```

El medidor es instantáneo y decae, así que la app toma **tres muestras
separadas 80 ms** y se queda con el pico de cada pista. Si el transporte está
parado, no se lee nada: cualquier conclusión sobre niveles en silencio sería
falsa (el medidor ya bajó a cero).

Con eso la IA puede comparar pistas entre sí y con el master: «la voz está
12 dB sobre la batería», «el master está en -1,9 dBFS, estás al límite».

## Qué falta para que sea diagnóstico completo

- **Reducción de ganancia**: REAPER no la expone como parámetro general; algunos
  plugins la publican y otros no.
- Comparar plugins entre sí («este compresor contra aquel»).

## Las fichas actuales

| Ficha | Contenido |
|---|---|
| `eq` | Rangos de frecuencia, Q, filtros y shelves, cortar antes de realzar |
| `dinamica` | Threshold, ratio, ataque, release, knee, compresión paralela, sidechain |
| `niveles` | dBFS, headroom, LUFS, niveles de grabación y master |
| `voz` | High-pass, de-esser, compresión, presencia, reverb |
| `bateria` | Bombo, caja, overheads, compresión y fase |
| `espacio` | Reverb, delay, pre-delay y envíos |
| `grabacion` | Ganancia de entrada, latencia, ruido, tomas |
| `mezcla` | Orden de trabajo, buses, referencias |

Para verlas: `python -m miky knowledge` y `python -m miky knowledge -q eq`.

## Cómo agregar una ficha

En `src/miky/knowledge.py`, sumá un `Card` a `CARDS`:

```python
Card(
    "mastering",
    "Masterizado",
    ("master", "masterizar", "lufs", "limite"),
    (
        "Pico máximo -1 dBTP.",
        "Loudness objetivo -14 LUFS para streaming.",
    ),
),
```

Reglas de estilo:

- Datos **concretos** (Hz, dB, ms, ratios, LUFS), no adjetivos.
- Español rioplatense, frases cortas.
- 5–10 viñetas por ficha.
- Si un dato depende del género o del material, decilo («en rock…», «en voz…»).

## Fuentes recomendadas

Todo lo que se escribe acá es **resumen propio**; no se copia texto de libros ni
de foros. Fuentes útiles y su licencia:

| Fuente | Para qué | Licencia |
|---|---|---|
| **REAPER User Guide** (Cockos, PDF gratis) | Técnicas y acciones específicas del DAW | Gratis para leer y citar |
| **Manuales de fabricantes** (FabFilter, iZotope, Waves, Soundtheory) | Guías de EQ, compresión y mastering muy didácticas | Gratis; se resumen con palabras propias |
| **Wikipedia / Wikibooks** (ingeniería de audio) | Definiciones y fundamentos | CC BY-SA (atribuir) |
| **Stack Exchange** (Sound Design, Music Practice) | Casos concretos y recetas | CC BY-SA 4.0 (atribuir) |
| **MIT OpenCourseWare** | Acústica y procesamiento de señales | CC BY-NC-SA |
| **Libros clásicos** (Mixing Secrets, The Art of Mixing, Yamaha SR Handbook) | Criterio y método | De pago: sirven como referencia, no para copiar |

**No conviene** descargar libros o foros enteros y meterlos en el proyecto: es
un problema legal y además empeora las respuestas (el modelo se pierde entre
miles de párrafos irrelevantes).

## Por qué no entrenar ni usar embeddings (todavía)

| Alternativa | Por qué no ahora |
|---|---|
| Fine-tuning del modelo | Caro, no disponible para el modelo rápido que usamos, y no permite citar fuentes |
| Base vectorial (RAG con embeddings) | Suma dependencias pesadas y latencia; con 8–30 fichas la búsqueda por palabras alcanza |
| Scrapear foros/libros | Legalmente riesgoso y ruidoso |

Cuando las fichas pasen de ~40, el paso natural es moverlas a
`%APPDATA%\Miky\knowledge\*.md` (editables por el usuario) y agregar búsqueda
por similitud. La estructura ya está pensada para eso: `relevant()` es la única
función que habría que cambiar.

## Verificación

- `tests/test_knowledge.py`: cada tema encuentra su ficha, las consultas se
  distinguen de las órdenes, y las fichas tienen contenido y etiquetas.
- Prueba real: la misma consulta («¿cómo ecualizo la voz para que no suene
  nasal?») sin fichas respondía un rango genérico; con la ficha `voz` responde
  **250–400 Hz, Q 2–4 y high-pass 80–100 Hz**.
