# Protocolo del puente

Especificación del canal entre la aplicación (Python) y REAPER (el script Lua
que corre adentro). Es deliberadamente aburrido: archivos JSON en una carpeta y
un latido. Nada de sockets, ni de dependencias, ni de magia.

## Dónde vive el canal

```
%APPDATA%\Miky\ipc\
├── requests\           la app deja pedidos acá
│   └── <id>.req.json
├── responses\          el puente deja respuestas acá
│   └── <id>.res.json
├── status.json         latido del puente
├── bridge.lock         garantiza una sola instancia
└── bridge.log          log del puente (arranques, errores)
```

`%APPDATA%` es `C:\Users\<usuario>\AppData\Roaming`. La misma ruta se calcula de
los dos lados: Python con `paths.ipc_root()`, Lua con `os.getenv("APPDATA")`.

Para aislar el canal (tests o una segunda instancia de REAPER) se puede definir
`MIKY_IPC_ROOT`; Python y el puente la respetan.

## Un pedido

```json
{
  "v": 1,
  "id": "m1793964957123-4512-00001",
  "steps": [
    {"cmd": "track.add", "args": {"name": "Guitarra", "color": "azul"}},
    {"cmd": "fx.add", "args": {"track": "Guitarra", "name": "ReaEQ"}}
  ]
}
```

| Campo | Tipo | Obligatorio | Detalle |
|---|---|---|---|
| `v` | entero | sí | Versión del protocolo (hoy `1`) |
| `id` | texto | sí | Identifica el pedido y la respuesta. Solo `[A-Za-z0-9_-]`, hasta 48 caracteres |
| `steps` | lista | sí | Entre 1 y 32 pasos |
| `steps[].cmd` | texto | sí | Un comando del catálogo |
| `steps[].args` | objeto | no | Argumentos; se validan contra el catálogo antes de enviarse |

También se acepta la forma corta de un solo paso (`{"v":1,"id":"...","cmd":"ping"}`),
aunque la app siempre manda `steps`.

El nombre del archivo es `<id>.req.json`. El `id` lo genera la app con la forma
`m<epoch_ms>-<pid>-<contador>` para que sea único y ordenable.

**Escritura atómica**: la app escribe primero un `.tmp` y después hace
`os.replace(tmp, destino)`. En Windows eso es atómico, así que el puente nunca
lee un archivo a medio escribir.

## Una respuesta

```json
{
  "v": 1,
  "id": "m1793964957123-4512-00001",
  "ok": true,
  "results": [
    {"cmd": "track.add", "ok": true,
     "result": {"index": 1, "name": "Guitarra", "track_count": 1}},
    {"cmd": "fx.add", "ok": true,
     "result": {"index": 1, "name": "VST: ReaEQ (Cockos)", "track": 1, "fx_count": 1}}
  ],
  "error": null,
  "bridge_ts": 1793964957,
  "elapsed_ms": 31.4
}
```

| Campo | Detalle |
|---|---|
| `ok` | `true` solo si **todos** los pasos salieron bien |
| `results` | Un elemento por paso ejecutado, en orden |
| `results[].result` | Datos concretos de lo que pasó (índices, nombres, conteos) |
| `results[].error` | `{code, message}` si ese paso falló |
| `error` | Error del pedido completo: `{code, message, step, cmd}` |
| `bridge_ts` | Hora del puente (`os.time()`) |
| `elapsed_ms` | Lo que tardó el puente en ejecutar |

La respuesta se escribe **una sola vez**, con nombre único (`<id>.res.json`), así
que no hay riesgo de sobrescritura ni de renombrado fallido.

## Semántica de lote

- Los pasos se ejecutan **en orden**, dentro de un mismo `PreventUIRefresh`.
- Cada paso abre y cierra **su propio bloque de deshacer** con una descripción
  legible («Crear pista», «Cambiar parámetro de plugin»). Así Ctrl+Z deshace una
  acción del asistente por vez.
- **Se corta en el primer error**. Los pasos anteriores quedan aplicados (y
  deshacibles) y están en `results`.
- El error incluye `step` (1-based) y `cmd`, para que la app pueda decir qué
  falló y qué sí se hizo.

Ejemplo de fallo parcial:

```json
{
  "ok": false,
  "results": [
    {"cmd": "track.add", "ok": true, "result": {"index": 2, "name": "Guitarra"}},
    {"cmd": "track.mute", "ok": false,
     "error": {"code": "track_not_found",
               "message": "no encontre la pista \"Teclados\". pistas actuales: 1=Hi-hat, 2=Guitarra"}}
  ],
  "error": {"code": "track_not_found", "message": "no encontre la pista …", "step": 2, "cmd": "track.mute"}
}
```

## El latido (`status.json`)

```json
{
  "v": 1,
  "bridge": "0.1.0b1",
  "protocol": 1,
  "instance": "1793964952-table0000000006B9B750",
  "reaper": "7.84/x64",
  "project": "miky_live_test.rpp",
  "project_path": "C:\\…\\Media",
  "ts": 1793964957,
  "beat": 75,
  "busy": false,
  "last_error": null,
  "handled": 44,
  "errors": 0,
  "ticks": 75,
  "command_count": 45,
  "resource_path": "C:\\Users\\…\\AppData\\Roaming\\REAPER"
}
```

El puente lo reescribe cada ~0,5 s (15 ticks de `defer`). La app decide que el
puente está vivo por la **fecha de modificación del archivo**, no por `ts`:
`alive = (ahora - mtime) < heartbeat_stale_ms` (3,5 s por defecto). `instance`
sirve para detectar si hay dos puentes peleando por el canal.

Caso especial `busy`: cuando se lanza un render, el puente se marca `busy` antes
de bloquearse. Como el render es sincrónico y puede durar minutos, la app
considera vivo al puente mientras `busy` sea verdadero (hasta el timeout de
render configurado), aunque el latido esté viejo.

## Una sola instancia

Si el script arranca dos veces, dos bucles de `defer` competirían por los mismos
archivos: uno ejecutaría el comando y el otro encontraría la carpeta vacía, y
ambos pelearían por `status.json`.

Solución: `bridge.lock` contiene un timestamp. Al arrancar:

1. si el lock existe y tiene menos de 6 s → otra instancia está viva, **este
   script no arranca** (lo deja anotado en `bridge.log`);
2. si está viejo → se borra y se toma;
3. el lock se refresca en cada latido y se libera con `reaper.atexit`.

La toma es un test-and-set atómico usando `os.rename`: en Windows el renombrado
falla si el destino ya existe, y eso evita la carrera entre dos arranques
simultáneos.

## La trampa de `EnumerateFiles`

`reaper.EnumerateFiles(dir, index)` **cachea el listado del directorio**. Si el
puente se limita a enumerar, nunca ve los archivos nuevos. La llamada con
`index = -1` invalida esa caché. Por eso `pump()` empieza siempre así:

```lua
reaper.EnumerateFiles(IPC.req_dir, -1)  -- invalida la caché
-- recién después: enumerate 0..n
```

Es el detalle que hace que todo esto funcione; si alguna vez el puente «se
queda dormido», lo primero que hay que mirar es esa línea.

## Códigos de error

| Código | Cuándo | Qué puede hacer la app |
|---|---|---|
| `unknown_command` | el puente no conoce el id | error de programación; avisar |
| `bad_request` | JSON inválido, sin pasos o más de 32 | no debería pasar (la app valida antes) |
| `missing_arg` | falta un argumento obligatorio | pedir el dato que falta |
| `invalid_arg` | argumento de tipo o valor incorrecto | explicar el formato esperado |
| `track_required` | no se indicó pista y no hay una sola seleccionada | preguntar cuál |
| `track_not_found` | no existe la pista, o ninguna coincide con el nombre | repetir con las pistas disponibles (vienen en el mensaje) |
| `track_ambiguous` | el nombre coincide con varias pistas | preguntar cuál |
| `fx_not_found` | el plugin no está en la pista o no existe | cargarlo a mano e copiar el nombre real |
| `fx_ambiguous` | el nombre coincide con varios plugins | pedir el número |
| `param_not_found` | el parámetro no existe en el plugin | el mensaje lista los disponibles |
| `param_ambiguous` | el nombre coincide con varios parámetros | pedir el número |
| `no_armed_track` | se pidió grabar sin pistas armadas | armar primero |
| `project_unsaved` | se pidió guardar un proyecto sin ruta | usar `save_as` |
| `marker_not_found` | no existe el marcador o región | listar los que hay |
| `command_failed` | error inesperado dentro de un handler | mostrar el mensaje |
| `bridge_error` | excepción fuera de los handlers | revisar `bridge.log` |

Todos los mensajes están en español, pensados para decirse en voz alta.

## Límites

| Límite | Valor | Dónde |
|---|---|---|
| Pasos por pedido | 32 | `ipc.lua`, `bridge.py` |
| Tamaño del pedido | 256 KB | `ipc.lua` |
| Pedidos por tick | 8 | `ipc.lua` |
| Tiempo de espera de un comando | 8 s (30 s si hay render) | `config.toml` |
| Tiempo de espera de render | 30 min | `config.toml` |

## Cómo depurarlo a mano

```powershell
miky status                          # ¿hay latido? ¿qué proyecto? ¿está ocupado?
miky send track.add --args '{"name":"Prueba"}'
```

Mirar las carpetas también sirve: si un archivo queda en `requests/` sin su
respuesta, el puente no lo tomó (¿está corriendo? ¿es otra instancia?); si queda
en `responses/`, la app no lo leyó (¿se colgó?).

El log del puente está en `%APPDATA%\Miky\ipc\bridge.log` y solo anota arranques,
errores y detenciones (no cada comando, para no ensuciar).

En el lado Python:

```powershell
type %APPDATA%\Miky\logs\miky.log
```

## Seguridad del canal

- El puente **solo** ejecuta ids que existan en su tabla de handlers: no hay
  `loadstring` ni `dofile` de nada que venga en el pedido.
- Los nombres de archivo se validan con `^([%w_%-]+)%.req%.json$`; cualquier otra
  cosa se borra sin ejecutar.
- Los argumentos se validan dos veces: en Python contra el catálogo (tipos,
  rangos, enums) y en Lua contra el sentido común de cada handler (pistas que
  existen, índices en rango, colores válidos).
- El puente no escribe fuera de su carpeta, salvo lo que REAPER guarda o
  renderiza por un comando explícito.
- Como cualquier script de REAPER, corre con los permisos del usuario: la
  contención real viene del catálogo cerrado, no del sistema operativo.
