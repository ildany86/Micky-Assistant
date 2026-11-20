# Miky — asistente de voz para REAPER

![Miky](img/hero.png)

**Miky es un micrófono flotante que maneja tu sesión de REAPER con la voz.**
Le hablás en español rioplatense y él crea pistas, carga plugins, rutea envíos,
edita, graba y renderiza. No es un plugin, no es una ventana y no toca nada fuera
de REAPER.

![Estados del ícono](img/icono.gif)

---

## El problema

Mezclar y grabar es un trabajo con las dos manos ocupadas. Cada decisión chica
—subir el bajo, buscar ese compresor, abrir la matriz de ruteo, mover el cursor—
obliga a soltar el instrumento, buscar el mouse y navegar menús. Y las ideas se
enfrían mientras se busca el plugin.

Los asistentes de voz genéricos no ayudan: no conocen el proyecto, no saben qué
plugins tenés, y cuando se equivocan de comando pueden romper una sesión.

## La propuesta

Un ícono que se arrastra por la pantalla y se queda ahí, discreto. Le hablás y
ejecuta. Nada más:

- **Sin ventana**: no hay panel que tapar ni que cerrar.
- **Sin plugin**: no se instala dentro de REAPER, no toca el proyecto de forma
  rara, no rompe la cadena de arranque.
- **Sin acceso demás**: solo puede ejecutar el catálogo cerrado de comandos de
  REAPER. No abre programas, no navega archivos, no hace nada fuera del DAW.

## Qué hace

| Capacidad | Detalle |
|---|---|
| **Hablarle y que ejecute** | «Miky, subí el bajo dos dB», «grabá», «poné el tempo en 96» |
| **55 comandos** | Pistas, plugins, envíos, ítems, transporte, marcadores, tempo, render |
| **Buscar plugins** | Por descripción («un compresor estilo SSL»), con tus **favoritos de REAPER** primero |
| **Preguntar antes de romper** | Borrar pistas, renderizar o guardar encima piden confirmación |
| **Grabar sin su voz** | Pregunta «¿estás listo?» y arranca en silencio |
| **Avisar sin molestar** | Un sonido corto si salió bien, voz solo si hay que explicar algo |
| **Opinar con fundamento** | Lee tus plugins y tus niveles reales y aconseja con datos, no con generalidades |
| **Funcionar sin internet** | Las órdenes básicas las resuelve un router local, sin nube |

### Cómo se siente

> **Vos:** «Miky, creá una pista de guitarra y cargale el compresor que uso siempre.»
> **Miky:** *(tono corto)* «Listo, cargué Eamut BusComp en Guitarra.»
>
> **Vos:** «¿Está bien comprimida la voz?»
> **Miky:** «El compresor de la voz está en 8:1 con ataque de 1 ms: para una voz
> principal eso es duro y te está matando el transiente. Probá 3:1 y 15 ms.»

## Cómo funciona

```
voz → micrófono → VAD → reconocimiento local → palabra clave
    → router local (órdenes directas, 0,04 ms)
    → o IA en la nube (interpreta lo ambiguo) → validador
    → puente ReaScript dentro de REAPER → acción + respuesta hablada
```

- **El audio nunca sale de tu computadora.** La nube recibe texto y estado del
  proyecto.
- **Catálogo cerrado**: la IA no puede inventar comandos; propone sobre una lista
  validada y el motor rechaza lo que no existe.
- **La IA es un proveedor intercambiable** (Gemini por defecto, con la clave del
  usuario; también OpenAI-compatible o local).

Más detalle: [arquitectura](01-arquitectura.md) · [protocolo](02-protocolo-puente.md) ·
[cómo piensa](08-conocimiento.md).

## Por qué es distinto

1. **No invade.** Un ícono, cero ventanas, cero plugins.
2. **Conoce tu sesión.** Sabe qué pistas tenés, qué plugins cargaste y cómo están
   ajustados, y cuánto mide cada medidor.
3. **No inventa.** Los consejos se apoyan en fichas técnicas y en datos reales;
   las acciones se validan contra un catálogo.
4. **Respeta tu trabajo.** Confirma lo destructivo y nunca dice que hizo algo que
   no ejecutó.

## Estado actual

| | |
|---|---|
| Versión | **0.1.0 beta 1** |
| Plataforma | Windows 10/11 · REAPER 7.x · Python 3.11+ |
| Comandos | 55 en el catálogo · 60 en el puente |
| Router local | 57 reglas, ~0,04 ms |
| Pruebas | **408 tests** + prueba en vivo contra REAPER 7.85 |
| Latencia típica | 1,5 s reconocimiento · 0,9 s IA · ~1 s voz (o 0 si está en caché) |

## Lo que todavía no hace

- **No escucha audio**: lee medidores y parámetros, pero no analiza el sonido.
- **No es multiplataforma**: hoy solo Windows.
- **Habla español rioplatense**: el reconocimiento entiende español general, pero
  las respuestas y el vocabulario están pensados para Argentina.
- **No reemplaza tu criterio**: aconseja, no mezcla por vos.

## Requisitos

Windows 10/11, REAPER 7, Python 3.11+ y una API key gratuita de Gemini.
La puesta en marcha está en el [README](../README.md#puesta-en-marcha).

## Licencia

Propietario, todos los derechos reservados. Ver [LICENSE.md](../LICENSE.md).
