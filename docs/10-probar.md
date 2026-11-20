# Cómo probar Miky (y cómo dárselo a alguien)

Dos partes: la primera es para vos (dueño), la segunda se la podés copiar y
pegar tal cual a quien vaya a probarlo.

---

## Parte 1 — Para vos: cómo compartirlo

Hay cuatro caminos, de menor a mayor esfuerzo para el que prueba:

| Camino | Para quién | Esfuerzo del tester | Riesgo |
|---|---|---|---|
| **Colaborador del repo** (privado) | 1–3 personas de confianza | Alto: instalar Python y dependencias | Bajo: ves quién entra y lo revocás |
| **ZIP del código** | Alguien técnico | Alto, igual que arriba | Medio: el código sale de tu control |
| **Release con ZIP adjunto** | Técnico, sin dar acceso al repo | Alto | Medio |
| **Ejecutable portable** (todavía no existe) | Cualquiera | Bajo: doble clic | Bajo |

### Opción A — Colaborador (recomendada para empezar)

1. Entrá a `https://github.com/ildany86/Micky-Assistant/settings/access`.
2. **Add people** → buscá por usuario o mail → rol **Read**.
3. Mandale este documento y el link del repo.
4. Cuando termina: el mismo panel → **Remove**.

Ventajas: siempre prueba la última versión (`git pull`), y si subís cambios los
recibe. Desventajas: necesita Python instalado y ~1,5 GB de dependencias.

### Opción B — ZIP del código, sin dar acceso

1. En el repo: **Code → Download ZIP**.
2. Mandale el ZIP por el medio que prefieras (WeTransfer, Drive, Telegram).
3. El tester descomprime y sigue la Parte 2.

Ojo: el ZIP no se actualiza solo. Si corregís algo, hay que reenviarlo.

### Opción C — Release con ZIP adjunto

1. En el repo: **Releases → Draft a new release**.
2. Adjuntá el ZIP como binario y publicá.
3. El tester lo baja del release (si el repo es privado, necesita cuenta con
   acceso igual).

Útil para dejar una versión congelada y que las pruebas sean comparables.

### Opción D — Ejecutable portable (pendiente)

Hoy Miky corre desde el código: no hay `.exe`. Para que lo pruebe alguien sin
Python habría que empaquetarlo con PyInstaller/Nuitka (PySide6 + faster-whisper +
onnxruntime; es un trabajo aparte y conviene hacerlo cuando el producto esté
cerrado). Si querés, es el próximo hito técnico.

### Qué pedirle al tester

- El ZIP de `miky diagnostics` (ver abajo).
- Qué intentó hacer, qué esperaba y qué pasó.
- Captura del ícono si el estado no coincide con lo que cuenta.
- Versión de Windows y de REAPER.

### Checklist de tu lado antes de mandarlo

- [ ] `python -m pytest` en verde (hoy: 408+ tests).
- [ ] `miky doctor` sin rojos propios.
- [ ] El ZIP no lleva tu `config.toml` (el `.gitignore` lo excluye).
- [ ] Le avisaste de las limitaciones (Windows, español rioplatense, beta).
- [ ] Le dijiste que la API key la saca él, gratis.

---

## Parte 2 — Para el que prueba (copiar y pegar)

### Antes de empezar

- **Windows 10 u 11** y **REAPER 7** instalado.
- **Python 3.11 o superior** ([python.org](https://www.python.org/downloads/);
  al instalar, marcá *Add python.exe to PATH*).
- Una **API key de Gemini**, gratis, en
  <https://aistudio.google.com/apikey> (30 segundos).
- Un micrófono. Auriculares ayudan a que no se escuche a sí mismo.

### Instalación (una sola vez)

1. Descomprimí el ZIP en una carpeta, por ejemplo `C:\Miky`.
2. Doble clic en **`instalar.bat`** y esperá (5–10 minutos la primera vez:
   descarga dependencias).
3. Al final te muestra un diagnóstico. Si todo dice `[ok]`, seguí.
4. Doble clic en **`run_miky.bat`**: aparece el ícono flotante.

### Primera configuración

1. **Clic derecho en el ícono → Ajustes**.
2. Pegá tu API key de Gemini y **Guardar**.
3. Clic derecho → **Abrir REAPER con Miky** (o abrí REAPER normalmente).
4. Decí **«Miky…»** seguido de la orden.

### Qué probar (10 minutos)

| Probá esto | Debería pasar |
|---|---|
| «Miky, creá una pista de guitarra» | Aparece la pista y suena un aviso corto |
| «Miky, subí el bajo dos dB» | Cambia el volumen y te lo confirma con voz o sonido |
| «Miky, cargá un compresor en la voz» | Busca y, si hay varios, te ofrece opciones numeradas |
| «Miky, borrá la pista 3» | Pregunta antes de borrar |
| «Miky, grabá» | Pregunta «¿estás listo?» y arranca en silencio |
| «Miky, ¿cómo está el balance?» | Habla de tus niveles reales |
| «Miky, ¿cómo ecualizo la voz?» | Consejo con frecuencias concretas |

### Si algo falla

1. Abrí una consola en la carpeta de Miky y corré:
   ```powershell
   .venv\Scripts\python.exe -m miky diagnostics
   ```
2. Se crea un ZIP en el escritorio (`Miky-diagnostico-FECHA.zip`).
3. Mandalo junto con: qué hiciste, qué esperabas y qué pasó.

El ZIP incluye versiones, el diagnóstico del entorno, los dispositivos de audio,
la configuración **sin la API key** y los últimos logs. **No incluye audio,
proyectos ni tu nombre de usuario.**

### Privacidad y desinstalación

- **El audio nunca sale de tu computadora.** La nube solo recibe el texto de la
  orden y el estado del proyecto.
- **La API key es tuya** y se guarda cifrada con tu usuario de Windows.
- El puente se instala en `%APPDATA%\REAPER\Scripts\Miky` y agrega un bloque a
  `__startup.lua`. Para quitarlo:
  ```powershell
  .venv\Scripts\python.exe -m miky install-bridge --remove
  ```
- Para borrar todo: eliminá la carpeta de Miky y `%APPDATA%\Miky`.

### Limitaciones de esta beta

- Solo Windows.
- Habla español rioplatense; entiende español general pero no otros idiomas.
- No analiza el audio: lee parámetros y medidores, no "escucha" la mezcla.
- Es una beta: puede fallar y conviene no usarla en una sesión de trabajo sin
  guardar antes.
