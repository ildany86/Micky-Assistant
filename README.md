# Miky

![Miky, asistente de voz para REAPER](docs/img/hero.png)

**Español** · [English](README.en.md)

**Asistente de voz para REAPER.** Un micrófono flotante en la pantalla: le hablás
y él maneja la sesión. Escucha y responde en tu computadora; solo la
interpretación del lenguaje viaja a la nube.

![El ícono en sus distintos estados](docs/img/icono.gif)

Miky no es un plugin de REAPER, no es una ventana de aplicación y no toca nada
fuera de REAPER: es un ícono que se arrastra por la pantalla y un motor que
ejecuta un catálogo cerrado de comandos sobre la API del DAW.

---

## Qué hace hoy (beta 0.1)

- **Te escucha siempre** (palabra clave «Miky») o solo cuando tocás el ícono.
- **Habla en español argentino** con voz de hombre (Tomás), o con la voz local de Windows si no hay internet.
- **Entiende** pedidos en español rioplatense y los convierte en acciones.
- **Controla REAPER** por dentro: pistas, plugins, envíos, edición de items,
  transporte, marcadores, tempo y render.
- **Busca plugins por descripción** («un compresor estilo bus de SSL») y, si hay varios, te da opciones numeradas.
- **Pregunta antes de romper algo**: borrar pistas, renderizar o guardar encima.
- **Pregunta «¿estás listo?» antes de grabar** y arranca en silencio, para que su voz no quede en la toma.
- **Sigue funcionando sin internet** para las órdenes básicas (router local).
- **Te responde consejos** de grabación y mezcla si le preguntás (sin tocar nada).

Qué puede pedirle (ejemplos reales):

> «Miky, creá una pista de guitarra y cargale ReaEQ»
> «Miky, subí el bajo dos dB»
> «Miky, grabá»
> «Miky, poné el tempo en 96 y activá el metrónomo»
> «Miky, renderizá la mezcla»

El catálogo completo (55 comandos en esta beta) está en
[`docs/03-catalogo-comandos.md`](docs/03-catalogo-comandos.md).

## Cómo funciona

```
  vos hablás
      │
      ▼
  [ micrófono ]──VAD──►[ texto local ]──palabra clave──►┌──────────────┐
                                                       │ router local │──► comando directo
                                                       └──────┬───────┘
                                                              │ (si no coincide)
                                                              ▼
                                                    ┌───────────────────┐
                                                    │ IA en la nube     │  Gemini por defecto
                                                    │ (elige comandos)  │  (proveedor cambiables)
                                                    └────────┬──────────┘
                                                             ▼
                                                    ┌───────────────────┐
                                                    │ motor + validador │  catálogo cerrado
                                                    └────────┬──────────┘
                                                             ▼
                                              %APPDATA%\Miky\ipc  (archivos)
                                                             ▼
                                                    ┌───────────────────┐
                                                    │ puente ReaScript  │  dentro de REAPER
                                                    └────────┬──────────┘
                                                             ▼
                                                          REAPER
                                                             │
                                                             ▼
                                                    respuesta hablada
```

Todo el audio se procesa local (faster-whisper para entender, SAPI para hablar).
La nube solo recibe el texto de la orden y el estado del proyecto, nunca audio.

## Puesta en marcha

Requisitos: Windows 10/11, REAPER 7, Python 3.11+.

```powershell
# 1. entorno
cd "E:\Proyecto X"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"

# 2. puente dentro de REAPER (una sola vez)
.\.venv\Scripts\python.exe tools\build_lua.py
.\.venv\Scripts\python.exe -m miky install-bridge

# 3. revisar que todo esté en orden
.\.venv\Scripts\python.exe -m miky doctor

# 4. abrir el asistente
run_miky.bat
```

La primera vez hay que pegar la API key de Gemini: clic derecho en el ícono →
**Ajustes**. Se saca gratis en <https://aistudio.google.com/apikey> y se guarda
cifrada con tu usuario de Windows.

Después: abrí REAPER (podés hacerlo desde el menú del ícono, «Abrir REAPER con
Miky») y decí **«Miky…»**.

Guía detallada: [`docs/05-instalacion-uso.md`](docs/05-instalacion-uso.md).

## Comandos de consola

```powershell
miky                 # abre el asistente (ícono flotante)
miky doctor          # diagnóstico completo del entorno y la conexión
miky status          # ¿está vivo el puente?
miky send track.add --args '{"name":"Guitarra"}'
miky tools           # catálogo de comandos disponibles
miky devices         # micrófonos detectados (y cuál elegiría)
miky voices          # voces de Windows instaladas
miky listen          # prueba de voz en consola
miky install-bridge  # reinstalar el puente en REAPER
miky diagnostics     # empaqueta info y logs para reportar un problema
```

## Estructura

```
src/miky/            la aplicación en Python
  app.py             orquestador (voz + IA + motor + puente)
  bridge.py          cliente del protocolo IPC
  catalog.py         catálogo cerrado y validación
  engine.py          ejecución de planes y confirmaciones
  router.py          comandos directos, sin IA
  ai/                Gemini (y cualquier API compatible con OpenAI)
  voice/             audio, VAD, STT, TTS, palabra clave
  ui/                ícono flotante, bandeja, ajustes
  data/              commands.json, puente compilado, logo
reaper/src/miky/     el puente Lua (se compila en un solo archivo)
tools/               build, pruebas reales, generación de docs
tests/               pruebas del puente (Lua) y del núcleo (Python)
docs/                arquitectura, protocolo, catálogo, roadmap
```

## Documentación

| Documento | Para qué |
|---|---|
| [Visión del producto](docs/00-vision-producto.md) | Qué es Miky y por qué está hecho así |
| [Arquitectura](docs/01-arquitectura.md) | Cómo está construido por dentro |
| [Protocolo del puente](docs/02-protocolo-puente.md) | Cómo se hablan la app y REAPER |
| [Catálogo de comandos](docs/03-catalogo-comandos.md) | Qué se le puede pedir |
| [Voz y audio](docs/04-voz-y-audio.md) | Micrófono, modelos, latencia, ASIO |
| [Instalación y uso](docs/05-instalacion-uso.md) | Paso a paso |
| [Referencias de REAPER](docs/06-referencias-reaper.md) | API, ReaPack y datos verificados |
| [Hoja de ruta](docs/07-roadmap.md) | Qué viene después |
| [Conocimiento técnico](docs/08-conocimiento.md) | Fichas de mezcla y audio que sostienen los consejos |
| [Presentación](docs/09-presentacion.md) | Resumen del producto en una página |
| [Cómo probar](docs/10-probar.md) | Guía para quien lo prueba y cómo compartirlo |

## Estado

Beta 0.1, en desarrollo activo. Probada de punta a punta contra REAPER 7.85 en
Windows 11: todos los comandos seguidos, render real y cierre limpio, sin fallas
(`tools/live_test.py`).

## Licencia

**Propietario. Todos los derechos reservados.** El código se publica para
consulta y evaluación; no se autoriza su redistribución, modificación comercial
ni uso en productos derivados sin permiso escrito del autor.

Si se distribuye, revisar además las licencias de los componentes de voz y de
los modelos de reconocimiento (algunas variantes de Whisper y las voces de
edge-tts tienen condiciones propias; ver
[hoja de ruta](docs/07-roadmap.md#riesgos-abiertos)).
