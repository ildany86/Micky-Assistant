-- Miky · marcadores, regiones y renderizado (marker.*, region.*, render.*)

MIKY = MIKY or {}

MIKY.cmd_content = (function()
  local U = MIKY.util

  local handlers = {}

  handlers['marker.add'] = {
    undo = true,
    desc = 'Crear marcador',
    fn = function(args)
      local name = U.str(args, 'name', { default = 'Marcador' })
      local pos = U.num(args, 'position')
      if not pos then
        pos = reaper.GetCursorPosition()
      end
      local color = 0
      if U.raw(args, 'color') ~= nil then
        color = reaper.ColorToNative(U.color(U.raw(args, 'color'))) | 0x1000000
      end
      local idx = reaper.AddProjectMarker2(0, false, pos, 0, name, -1, color)
      if not idx or idx < 0 then
        U.fail('reaper_error', 'REAPER no pudo crear el marcador')
      end
      return { name = name, position = U.round(pos, 3), index = idx }
    end,
  }

  handlers['region.add'] = {
    undo = true,
    desc = 'Crear region',
    fn = function(args)
      local name = U.str(args, 'name', { default = 'Region' })
      local start = U.num(args, 'start')
      local finish = U.num(args, 'finish')
      if not start or not finish then
        local s, e = reaper.GetSet_LoopTimeRange(false, true, 0, 0, false)
        if e <= s then
          U.fail('missing_arg', 'indica "start" y "finish" (o crea una seleccion de tiempo primero)')
        end
        start, finish = s, e
      end
      if finish <= start then
        U.fail('invalid_arg', 'el final de la region debe ser mayor que el comienzo')
      end
      local idx = reaper.AddProjectMarker2(0, true, start, finish, name, -1, 0)
      if not idx or idx < 0 then
        U.fail('reaper_error', 'REAPER no pudo crear la region')
      end
      return {
        name = name,
        start = U.round(start, 3),
        finish = U.round(finish, 3),
        index = idx,
      }
    end,
  }

  local mode_map = {
    mix = { settings = 0, bounds = 1 },
    entire = { settings = 0, bounds = 1 },
    time_selection = { settings = 0, bounds = 2 },
    regions = { settings = 0, bounds = 3 },
    selected_items = { settings = 32, bounds = 4 },
    stems = { settings = 2, bounds = 1 },
    stems_master = { settings = 1, bounds = 1 },
  }

  handlers['render.start'] = {
    undo = false,
    desc = 'Renderizar',
    slow = true, -- el render bloquea el hilo: el puente lo trata con timeout largo
    fn = function(args)
      local mode = U.enum(
        args,
        'mode',
        { 'last', 'mix', 'entire', 'time_selection', 'regions', 'selected_items', 'stems', 'stems_master' },
        { default = 'last' }
      )
      local out_dir = U.str(args, 'out_dir')
      local pattern = U.str(args, 'pattern')
      local normalize = U.num(args, 'normalize_lufs', { min = -40, max = 0 })
      local format = U.enum(args, 'format', { 'last', 'wav' }, { default = 'last' })
      local add_to_project = U.bool(args, 'add_to_project', { default = false })
      local overwrite = U.bool(args, 'overwrite', { default = false })

      if out_dir and U.trim(out_dir) ~= '' then
        reaper.GetSetProjectInfo_String(0, 'RENDER_FILE', out_dir, true)
      end
      if pattern and U.trim(pattern) ~= '' then
        reaper.GetSetProjectInfo_String(0, 'RENDER_PATTERN', pattern, true)
      end
      if format == 'wav' then
        -- "evaw" == FourCC de WAV como lo espera RENDER_FORMAT (settings por defecto)
        reaper.GetSetProjectInfo_String(0, 'RENDER_FORMAT', 'evaw', true)
      end

      local mapping = mode_map[mode]
      if mapping then
        reaper.GetSetProjectInfo(0, 'RENDER_SETTINGS', mapping.settings, true)
        reaper.GetSetProjectInfo(0, 'RENDER_BOUNDSFLAG', mapping.bounds, true)
      end

      if normalize then
        -- &1 = normalizar, modo LUFS-I; el objetivo se expresa en ganancia lineal
        reaper.GetSetProjectInfo(0, 'RENDER_NORMALIZE', 1, true)
        reaper.GetSetProjectInfo(0, 'RENDER_NORMALIZE_TARGET', 10 ^ (normalize / 20), true)
      end

      reaper.GetSetProjectInfo(0, 'RENDER_ADDTOPROJ', add_to_project and 1 or 2, true)

      local _, targets = reaper.GetSetProjectInfo_String(0, 'RENDER_TARGETS', '', false)

      -- Si el archivo ya existe, REAPER abre un diálogo modal ("ya existe, ¿lo
      -- reemplazo?") que congela el puente. Mejor decidirlo acá: sin permiso
      -- explícito se rechaza, con overwrite se borra antes de renderizar.
      local existing = {}
      for raw_path in tostring(targets):gmatch('[^\r\n]+') do
        local path = U.trim(raw_path)
        if path ~= '' and path:match('^%a:[/\\]') then
          local handle = io.open(path, 'r')
          if handle then
            handle:close()
            existing[#existing + 1] = path
          end
        end
      end
      if #existing > 0 then
        if not overwrite then
          U.fail(
            'render_exists',
            'ya existe el archivo "' .. existing[1] .. '". Pedilo de nuevo con overwrite=true si queres reemplazarlo'
          )
        end
        for _, path in ipairs(existing) do
          os.remove(path)
        end
      end

      local started = reaper.time_precise()

      reaper.Main_OnCommand(42230, 0) -- Render + cerrar dialogo al terminar

      local elapsed = reaper.time_precise() - started
      return {
        mode = mode,
        targets = targets,
        overwritten = #existing > 0,
        elapsed_seconds = U.round(elapsed, 2),
      }
    end,
  }

  return handlers
end)()
