-- Miky · registro de comandos: fusiona los modulos, agrega los comandos base
-- y ejecuta cada paso dentro de su propio bloque de undo.

MIKY = MIKY or {}

MIKY.registry = (function()
  local U = MIKY.util
  local R = { handlers = {} }

  local function add(module)
    for id, handler in pairs(module) do
      if R.handlers[id] then
        error('comando duplicado en el registro: ' .. id)
      end
      R.handlers[id] = handler
    end
  end

  add(MIKY.cmd_tracks)
  add(MIKY.cmd_fx)
  add(MIKY.cmd_transport)
  add(MIKY.cmd_content)
  add(MIKY.cmd_sends)
  add(MIKY.cmd_items)

  local quit_scheduled = false

  -- ---------- Comandos base del puente ----------

  R.handlers['ping'] = {
    undo = false,
    desc = 'Ping',
    fn = function()
      return {
        pong = true,
        bridge = MIKY.VERSION,
        protocol = MIKY.PROTOCOL,
        reaper = reaper.GetAppVersion(),
      }
    end,
  }

  R.handlers['bridge.info'] = {
    undo = false,
    desc = 'Informacion del puente',
    fn = function()
      return {
        bridge = MIKY.VERSION,
        protocol = MIKY.PROTOCOL,
        reaper = reaper.GetAppVersion(),
        resource_path = reaper.GetResourcePath(),
        command_count = #R.list(),
        commands = R.list(),
      }
    end,
  }

  R.handlers['state.get'] = {
    undo = false,
    desc = 'Consultar estado',
    fn = function(args)
      return MIKY.state.snapshot(args)
    end,
  }

  -- Niveles instantaneos: sirve para opinar sobre el balance de la mezcla.
  -- REAPER entrega el valor del medidor (0..1+, puede pasar de 1 si satura).
  R.handlers['levels.get'] = {
    undo = false,
    desc = 'Leer los niveles del medidor',
    fn = function(args)
      local limit = U.num(args, 'limit', { default = 40, min = 1, max = 200 }) or 40

      local function db_from_peak(value)
        if not value or value <= 0 then
          return nil
        end
        return math.max(-120, 20 * math.log(value, 10))
      end

      local tracks = {}
      local count = reaper.CountTracks(0)
      for index = 0, math.min(count, limit) - 1 do
        local tr = reaper.GetTrack(0, index)
        local peak = reaper.Track_GetPeakInfo(tr, 0)
        tracks[#tracks + 1] = {
          index = index + 1,
          name = MIKY.state.name(tr),
          peak = peak,
          peak_db = db_from_peak(peak),
        }
      end

      local master = reaper.GetMasterTrack(0)
      local master_peak = reaper.Track_GetPeakInfo(master, 0)
      return {
        playing = reaper.GetPlayState() & 1 == 1,
        recording = reaper.GetPlayState() & 2 == 2,
        master = {
          peak = master_peak,
          peak_db = db_from_peak(master_peak),
        },
        tracks = tracks,
      }
    end,
  }

  R.handlers['action.info'] = {
    undo = false,
    desc = 'Consultar accion de REAPER',
    fn = function(args)
      local id = U.num(args, 'id', { required = true })
      local name = reaper.kbd_getTextFromCmd(id, 0)
      return { id = id, name = name or '' }
    end,
  }

  -- Solo para desarrollo/tests: cierra REAPER despues de responder.
  R.handlers['app.quit'] = {
    undo = false,
    desc = 'Cerrar REAPER',
    fn = function()
      if not quit_scheduled then
        quit_scheduled = true
        reaper.defer(function()
          reaper.Main_OnCommand(40004, 0) -- File: Quit
        end)
      end
      return { quitting = true }
    end,
  }

  -- ---------- Ejecucion ----------

  function R.get(cmd)
    return R.handlers[cmd]
  end

  function R.is_slow(cmd)
    local h = R.handlers[cmd]
    return h ~= nil and h.slow == true
  end

  function R.list()
    local ids = {}
    for id in pairs(R.handlers) do
      ids[#ids + 1] = id
    end
    table.sort(ids)
    return ids
  end

  function R.run(step)
    local cmd = step and step.cmd
    local handler = cmd and R.handlers[cmd]
    if not handler then
      U.fail('unknown_command', 'comando desconocido: ' .. tostring(cmd))
    end
    local args = U.args_table(step.args)
    local ok, result = pcall(handler.fn, args)
    if not ok then
      if type(result) == 'table' and result.code then
        error(result, 0)
      end
      error({ code = 'command_failed', message = tostring(result) }, 0)
    end
    return result or {}
  end

  function R.run_with_undo(step)
    local handler = R.handlers[step.cmd]
    if not handler or handler.undo == false then
      return R.run(step)
    end
    reaper.Undo_BeginBlock()
    local ok, result = pcall(R.run, step)
    local desc = handler.desc or step.cmd
    if ok then
      reaper.Undo_EndBlock(desc, 0)
      return result
    end
    -- Un punto de undo aun en el error: si hubo cambios parciales, se pueden deshacer.
    reaper.Undo_EndBlock(desc, 0)
    error(result, 0)
  end

  return R
end)()
