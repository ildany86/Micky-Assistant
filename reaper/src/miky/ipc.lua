-- Miky · IPC por archivos entre la app (Python) y REAPER (este script)
--
-- Por que archivos: ReaScript no tiene cliente HTTP/WebSocket nativo y no
-- queremos dependencias (SWS/ReaPack) para algo tan basico. El costo medido de
-- abrir+escribir+cerrar un archivo chico es ~0.9 ms, y el tick de defer es de
-- ~31 ms: sobra margen.
--
-- Protocolo:
--   requests/<id>.req.json    -> escrito por la app (rename atomico del lado Python)
--   responses/<id>.res.json   -> escrito por el puente
--   status.json               -> latido del puente (la app lo usa para saber si hay conexion)
--   bridge.lock               -> garantiza una sola instancia del puente por canal

MIKY = MIKY or {}

MIKY.ipc = (function()
  local J = MIKY.json
  local R = MIKY.registry
  local U = MIKY.util

  local IPC = {
    req_dir = nil,
    res_dir = nil,
    status_path = nil,
    lock_path = nil,
    log_path = nil,
    instance = "",
    last_error = nil,
    beat = 0,
    busy = false,
    stats = { ticks = 0, handled = 0, errors = 0 },
  }

  local HEARTBEAT_EVERY_TICKS = 15 -- ~0.5 s
  local LOCK_STALE_SECONDS = 6
  local MAX_STEPS = 32
  local MAX_REQUESTS_PER_TICK = 8
  local MAX_FILE_BYTES = 262144
  local MAX_LOG_BYTES = 512 * 1024

  local function join(a, b)
    return a .. '\\' .. b
  end

  local function read_file(path, max_bytes)
    local f = io.open(path, 'rb')
    if not f then
      return nil
    end
    local size = f:seek('end')
    if size == nil or size > (max_bytes or MAX_FILE_BYTES) then
      f:close()
      return nil, 'archivo demasiado grande'
    end
    f:seek('set', 0)
    local data = f:read('*a')
    f:close()
    return data
  end

  local function write_file(path, data)
    local f = io.open(path, 'wb')
    if not f then
      return false
    end
    local ok = f:write(data)
    f:close()
    return ok ~= nil
  end

  local function log_line(text)
    if not IPC.log_path then
      return
    end
    local f = io.open(IPC.log_path, 'a')
    if not f then
      return
    end
    f:write(os.date('%Y-%m-%d %H:%M:%S') .. '  ' .. tostring(text) .. '\n')
    f:close()
  end

  function IPC.setup()
    -- MIKY_IPC_ROOT permite usar un canal aparte (tests o segunda instancia de REAPER).
    local override = os.getenv('MIKY_IPC_ROOT')
    local base
    if override and override ~= '' then
      base = override
    else
      local appdata = os.getenv('APPDATA')
      if not appdata or appdata == '' then
        return false
      end
      base = join(join(appdata, 'Miky'), 'ipc')
    end
    IPC.base_dir = base
    IPC.req_dir = join(base, 'requests')
    IPC.res_dir = join(base, 'responses')
    IPC.status_path = join(base, 'status.json')
    IPC.lock_path = join(base, 'bridge.lock')
    IPC.log_path = join(base, 'bridge.log')
    return true
  end

  -- ---------------- instancia unica ----------------

  local function lock_timestamp()
    local raw = read_file(IPC.lock_path, 64)
    if not raw then
      return nil
    end
    return tonumber(raw)
  end

  local function refresh_lock()
    local f = io.open(IPC.lock_path, 'w')
    if not f then
      return false
    end
    f:write(tostring(os.time()))
    f:close()
    return true
  end

  -- En Windows os.rename falla si el destino existe: eso lo vuelve un
  -- test-and-set atomico, justo lo que hace falta para no correr dos puentes.
  function IPC.acquire_lock()
    local stamp = lock_timestamp()
    if stamp and (os.time() - stamp) < LOCK_STALE_SECONDS then
      return false
    end
    if stamp then
      os.remove(IPC.lock_path)
    end
    local token = tostring(os.time()) .. '-' .. tostring({}):gsub('[^%w]', '')
    local tmp = IPC.lock_path .. '.' .. token
    local f = io.open(tmp, 'w')
    if not f then
      return false
    end
    f:write(tostring(os.time()))
    f:close()
    local renamed = os.rename(tmp, IPC.lock_path)
    if not renamed then
      os.remove(tmp)
      return false
    end
    return true
  end

  function IPC.release_lock()
    if IPC.lock_path then
      os.remove(IPC.lock_path)
    end
  end

  -- ---------------- respuesta y estado ----------------

  local function respond(id, payload)
    local ok, encoded = pcall(J.encode, payload)
    if not ok then
      IPC.last_error = 'no se pudo serializar la respuesta: ' .. tostring(encoded)
      log_line(IPC.last_error)
      return false
    end
    local path = join(IPC.res_dir, id .. '.res.json')
    local written = write_file(path, encoded)
    if not written then
      IPC.last_error = 'no se pudo escribir ' .. path
      log_line(IPC.last_error)
    end
    return written
  end

  function IPC.write_status()
    if not IPC.status_path then
      return false
    end
    local info = {
      v = 1,
      bridge = MIKY.VERSION,
      protocol = MIKY.PROTOCOL,
      instance = IPC.instance,
      reaper = reaper.GetAppVersion(),
      project = reaper.GetProjectName(0),
      project_path = reaper.GetProjectPath(),
      ts = os.time(),
      beat = IPC.beat,
      busy = IPC.busy,
      -- 1 = tocando, 4 = grabando (máscara de GetPlayState).
      playing = (reaper.GetPlayState() & 1) ~= 0,
      recording = (reaper.GetPlayState() & 4) ~= 0,
      last_error = IPC.last_error,
      handled = IPC.stats.handled,
      errors = IPC.stats.errors,
      ticks = IPC.stats.ticks,
      command_count = #R.list(),
      resource_path = reaper.GetResourcePath(),
    }
    local ok, encoded = pcall(J.encode, info)
    if not ok then
      return false
    end
    local tmp = IPC.status_path .. '.' .. tostring({}):gsub('[^%w]', '') .. '.tmp'
    if not write_file(tmp, encoded) then
      return false
    end
    -- os.rename no sobrescribe en Windows: hay que borrar el destino primero.
    os.remove(IPC.status_path)
    local renamed = os.rename(tmp, IPC.status_path)
    if not renamed then
      os.remove(tmp)
      return false
    end
    refresh_lock()
    return true
  end

  -- ---------------- ejecucion ----------------

  local function execute_steps(steps)
    local results = {}
    local failure = nil
    local started = reaper.time_precise()

    local any_slow = false
    for _, step in ipairs(steps) do
      if type(step) == 'table' and R.is_slow(step.cmd) then
        any_slow = true
      end
    end

    if any_slow then
      IPC.busy = true
      pcall(IPC.write_status) -- avisa que el puente va a quedar bloqueado
    end

    reaper.PreventUIRefresh(1)
    local ok_loop, loop_err = pcall(function()
      for index, step in ipairs(steps) do
        if type(step) ~= 'table' or type(step.cmd) ~= 'string' then
          failure = { code = 'bad_request', message = 'paso ' .. index .. ' invalido' }
          break
        end
        local ok, res = pcall(R.run_with_undo, step)
        if ok then
          results[#results + 1] = { cmd = step.cmd, ok = true, result = res }
        else
          local err = res
          if type(err) ~= 'table' then
            err = { code = 'command_failed', message = tostring(err) }
          end
          results[#results + 1] = { cmd = step.cmd, ok = false, error = err }
          failure = {
            code = err.code or 'command_failed',
            message = err.message or 'error desconocido',
            step = index,
            cmd = step.cmd,
            candidates = err.candidates,
          }
          break
        end
      end
    end)
    reaper.PreventUIRefresh(-1)
    reaper.UpdateArrange()
    reaper.TrackList_AdjustWindows(false)

    if not ok_loop then
      failure = { code = 'bridge_error', message = tostring(loop_err) }
      IPC.last_error = tostring(loop_err)
      log_line('error ejecutando pasos: ' .. tostring(loop_err))
    end

    if any_slow then
      IPC.busy = false
      pcall(IPC.write_status)
    end

    return results, failure, reaper.time_precise() - started
  end

  local function process_file(name)
    local path = join(IPC.req_dir, name)
    local id = name:match('^([%w_%-]+)%.req%.json$')
    if not id then
      os.remove(path)
      return
    end

    local raw = read_file(path)
    if raw == nil then
      -- Archivo en transito o ilegible: se reintenta en el proximo tick.
      return
    end

    local ok_decode, request = pcall(J.decode, raw)
    if not ok_decode or type(request) ~= 'table' then
      respond(id, {
        v = 1,
        id = id,
        ok = false,
        results = {},
        error = { code = 'bad_request', message = 'JSON invalido: ' .. tostring(request) },
        bridge_ts = os.time(),
      })
      os.remove(path)
      return
    end

    local steps = request.steps
    if steps == nil then
      steps = { { cmd = request.cmd, args = request.args } }
    end
    if type(steps) ~= 'table' or #steps == 0 or #steps > MAX_STEPS then
      respond(id, {
        v = 1,
        id = id,
        ok = false,
        results = {},
        error = { code = 'bad_request', message = 'se esperaban entre 1 y ' .. MAX_STEPS .. ' pasos' },
        bridge_ts = os.time(),
      })
      os.remove(path)
      return
    end

    local results, failure, elapsed = execute_steps(steps)

    IPC.stats.handled = IPC.stats.handled + 1
    respond(id, {
      v = 1,
      id = id,
      ok = failure == nil,
      results = results,
      error = failure,
      bridge_ts = os.time(),
      elapsed_ms = U.round(elapsed * 1000, 1),
    })
    os.remove(path)
  end

  function IPC.pump()
    if not IPC.req_dir then
      return
    end

    -- IMPORTANTE: EnumerateFiles cachea el listado del directorio. Llamarlo con
    -- indice -1 invalida esa cache; sin esto el puente no ve los pedidos nuevos.
    reaper.EnumerateFiles(IPC.req_dir, -1)

    local names = {}
    local index = 0
    while index < 512 do
      local name = reaper.EnumerateFiles(IPC.req_dir, index)
      if not name then
        break
      end
      if name:match('%.req%.json$') then
        names[#names + 1] = name
      end
      index = index + 1
    end

    if #names == 0 then
      return
    end

    table.sort(names)
    for k = 1, math.min(#names, MAX_REQUESTS_PER_TICK) do
      local ok, err = pcall(process_file, names[k])
      if not ok then
        IPC.last_error = 'error procesando ' .. tostring(names[k]) .. ': ' .. tostring(err)
        IPC.stats.errors = IPC.stats.errors + 1
        log_line(IPC.last_error)
      end
    end
  end

  -- Pedidos de una sesion anterior (la app se cerro de golpe): si se ejecutan
  -- al abrir REAPER, se corre una orden vieja que nadie pidió.
  function IPC.purge_stale_requests(max_age_s)
    if not IPC.req_dir then
      return 0
    end
    reaper.EnumerateFiles(IPC.req_dir, -1)
    local now = os.time()
    local max_age = max_age_s or 120
    local removed = 0
    local index = 0
    while index < 512 do
      local name = reaper.EnumerateFiles(IPC.req_dir, index)
      if not name then
        break
      end
      if name:match('%.req%.json$') then
        local millis = tonumber(name:match('^m(%d+)'))
        if millis then
          local age = now - math.floor(millis / 1000)
          if age > max_age then
            os.remove(IPC.req_dir .. '/' .. name)
            removed = removed + 1
          end
        end
      end
      index = index + 1
    end
    if removed > 0 then
      log_line('descarté ' .. removed .. ' pedido(s) viejo(s) de una sesión anterior')
    end
    return removed
  end

  function IPC.main()
    if not IPC.setup() then
      return
    end

    if not IPC.acquire_lock() then
      log_line('ya hay otra instancia del puente activa en este canal; no arranco')
      return
    end

    IPC.instance = tostring(os.time()) .. '-' .. tostring({}):gsub('[^%w]', '')
    reaper.atexit(function()
      log_line('puente detenido')
      IPC.release_lock()
    end)

    -- Si el log creció demasiado, se reinicia (no hay rotación real en Lua).
    local existing = read_file(IPC.log_path, MAX_LOG_BYTES + 1)
    if existing == nil then
      os.remove(IPC.log_path)
    end
    log_line('puente v' .. MIKY.VERSION .. ' iniciado · instancia ' .. IPC.instance .. ' · REAPER ' .. reaper.GetAppVersion())

    pcall(IPC.write_status)
    pcall(IPC.purge_stale_requests)

    local function tick()
      local ok, err = pcall(IPC.pump)
      if not ok then
        IPC.last_error = tostring(err)
        IPC.stats.errors = IPC.stats.errors + 1
        log_line('error en el tick: ' .. tostring(err))
      end

      IPC.stats.ticks = IPC.stats.ticks + 1
      IPC.beat = IPC.beat + 1

      if IPC.stats.ticks % HEARTBEAT_EVERY_TICKS == 0 then
        local ok_status, err_status = pcall(IPC.write_status)
        if not ok_status then
          IPC.last_error = tostring(err_status)
        end
      end

      reaper.defer(tick)
    end

    reaper.defer(tick)
  end

  return IPC
end)()
