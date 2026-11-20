# Aviso de copyright y licencia

**Miky — asistente de voz para REAPER**
Copyright (C) 2026 Daniel Lugo

Este programa es software libre: podés redistribuirlo y/o modificarlo bajo los
términos de la **GNU General Public License, versión 3** (o cualquier versión
posterior), publicada por la Free Software Foundation.

El texto completo de la licencia está en [LICENSE](LICENSE).

Este programa se distribuye con la esperanza de que sea útil, pero **SIN NINGUNA
GARANTÍA**, ni siquiera la garantía implícita de comerciabilidad o idoneidad para
un fin particular. Ver la GNU General Public License para más detalles.

## Qué significa en la práctica

- **Podés** usar Miky gratis, en tu casa o en tu estudio.
- **Podés** mirar el código, modificarlo y compartir tus mejoras.
- **Si distribuyes una versión modificada**, tiene que ir también bajo GPL-3.0 y
  con el código disponible: nadie puede cerrarlo ni venderlo como propietario.
- **No hay garantía**: es una beta; guardá tu proyecto antes de usarla en una
  sesión importante.

## Componentes de terceros

Miky usa bibliotecas y servicios que conservan sus propias licencias:

| Componente | Licencia |
|---|---|
| PySide6 (Qt for Python) | LGPL-3.0 |
| faster-whisper / CTranslate2 | MIT |
| onnxruntime | MIT |
| Silero VAD | MIT |
| sounddevice | MIT |
| edge-tts | GPL-3.0 |
| google-genai | Apache-2.0 |
| REAPER y su API | Cockos (software propietario; Miky solo lo controla) |

Los modelos de reconocimiento que descarga faster-whisper tienen sus propias
condiciones (MIT para los modelos de OpenAI publicados en Hugging Face).

## Donaciones

Miky es gratis y libre. Si te resulta útil, podés colaborar con el desarrollo:
ver [DONAR.md](DONAR.md). Las donaciones son voluntarias y no compran licencias
ni soporte.
