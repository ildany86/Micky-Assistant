-- Miky · comandos de pistas (track.*)

MIKY = MIKY or {}

MIKY.cmd_tracks = (function()
  local U = MIKY.util
  local ST = MIKY.state

  local handlers = {}

  handlers['track.add'] = {
    undo = true,
    desc = 'Crear pista',
    fn = function(args)
      local name = U.str(args, 'name', { maxlen = 128 })
      local index = U.num(args, 'index')
      local color = U.raw(args, 'color')
      local arm = U.bool(args, 'arm')
      local monitor = U.raw(args, 'monitor')

      local n = ST.count()
      local insert_at
      if index then
        insert_at = math.floor(U.clamp(index - 1, 0, n))
      else
        insert_at = n
      end

      if reaper.APIExists('InsertTrackInProject') then
        reaper.InsertTrackInProject(0, insert_at, 1)
      else
        reaper.InsertTrackAtIndex(insert_at, true)
      end

      local tr = reaper.GetTrack(0, insert_at)
      if not tr then
        U.fail('reaper_error', 'REAPER no creo la pista')
      end

      if name and U.trim(name) ~= '' then
        ST.set_name(tr, name)
      end
      if color ~= nil then
        local native = U.color(color)
        reaper.SetTrackColor(tr, native)
      end
      if arm ~= nil then
        reaper.SetMediaTrackInfo_Value(tr, 'I_RECARM', arm and 1 or 0)
      end
      if monitor ~= nil then
        local mode = 0
        if type(monitor) == 'boolean' then
          mode = monitor and 1 or 0
        else
          local text = U.norm(tostring(monitor))
          if text == 'normal' or text == '1' then
            mode = 1
          elseif text == 'tape' or text == '2' then
            mode = 2
          end
        end
        reaper.SetMediaTrackInfo_Value(tr, 'I_RECMON', mode)
      end

      return { index = insert_at + 1, name = ST.name(tr), track_count = ST.count() }
    end,
  }

  handlers['track.add_many'] = {
    undo = true,
    desc = 'Crear varias pistas',
    fn = function(args)
      local names = U.raw(args, 'names')
      local count = U.num(args, 'count')
      if type(names) ~= 'table' then
        names = nil
      end
      if not names and not count then
        U.fail('missing_arg', 'indica "names" (lista de nombres) o "count"')
      end
      if count then
        count = math.floor(U.clamp(count, 1, 64))
      else
        count = #names
      end

      local created = {}
      for i = 1, count do
        local n = ST.count()
        if reaper.APIExists('InsertTrackInProject') then
          reaper.InsertTrackInProject(0, n, 1)
        else
          reaper.InsertTrackAtIndex(n, true)
        end
        local tr = reaper.GetTrack(0, n)
        local label = names and names[i]
        if label and U.trim(label) ~= '' then
          ST.set_name(tr, label)
        end
        created[#created + 1] = { index = n + 1, name = ST.name(tr) }
      end

      return { created = created, count = #created, track_count = ST.count() }
    end,
  }

  handlers['track.add_like'] = {
    undo = true,
    desc = 'Crear pista parecida a otra',
    fn = function(args)
      local source, source_idx = ST.resolve(U.raw(args, 'track'))
      local name = U.str(args, 'name')
      local copy_fx = U.bool(args, 'copy_fx', { default = true })

      -- Se inserta justo debajo de la pista modelo.
      reaper.InsertTrackInProject(0, source_idx, 0)
      local tr = reaper.GetTrack(0, source_idx)
      if not tr then
        U.fail('reaper_error', 'REAPER no creo la pista')
      end

      -- Mismas propiedades de grabación, nivel y formato de canal.
      local properties = { 'D_VOL', 'D_PAN', 'I_RECINPUT', 'I_RECMODE', 'I_RECMON', 'I_NCHAN', 'I_RECARM' }
      for _, property in ipairs(properties) do
        reaper.SetMediaTrackInfo_Value(tr, property, reaper.GetMediaTrackInfo_Value(source, property))
      end
      local color = reaper.GetTrackColor(source)
      if color and color ~= 0 then
        reaper.SetTrackColor(tr, color)
      end

      local copied_fx = 0
      if copy_fx then
        local count = reaper.TrackFX_GetCount(source)
        for index = 0, count - 1 do
          reaper.TrackFX_CopyToTrack(source, index, tr, -1, false)
          copied_fx = copied_fx + 1
        end
      end

      local final_name = name
      if not final_name or U.trim(final_name) == '' then
        final_name = ST.name(source)
      end
      ST.set_name(tr, final_name)

      return {
        index = source_idx + 1,
        name = ST.name(tr),
        source = ST.name(source),
        fx_count = reaper.TrackFX_GetCount(tr),
        copied_fx = copied_fx,
        input = ST.rec_input_text(reaper.GetMediaTrackInfo_Value(tr, 'I_RECINPUT')),
        track_count = ST.count(),
      }
    end,
  }

  handlers['track.rename'] = {
    undo = true,
    desc = 'Renombrar pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local name = U.str(args, 'name', { required = true, maxlen = 128 })
      ST.set_name(tr, name)
      return { index = idx, name = ST.name(tr) }
    end,
  }

  handlers['track.delete'] = {
    undo = true,
    desc = 'Eliminar pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local name = ST.name(tr)
      reaper.DeleteTrack(tr)
      return { deleted_index = idx, deleted_name = name, track_count = ST.count() }
    end,
  }

  handlers['track.duplicate'] = {
    undo = true,
    desc = 'Duplicar pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local before = ST.count()
      local original_name = ST.name(tr)

      -- Acción nativa "Track: Duplicate tracks" (40062): copia FX, envíos y
      -- contenido. Se usa la acción en vez del chunk porque el chunk puede
      -- disparar diálogos de REAPER si el estado no es consistente.
      reaper.SetOnlyTrackSelected(tr)
      reaper.Main_OnCommand(40062, 0)

      local after = ST.count()
      if after ~= before + 1 then
        U.fail(
          'reaper_error',
          'REAPER no duplico la pista "' .. original_name .. '" (pistas: ' .. before .. ' -> ' .. after .. ')'
        )
      end

      local duplicated = reaper.GetTrack(0, idx)
      return {
        index = idx + 1,
        name = duplicated and ST.name(duplicated) or original_name,
        track_count = after,
      }
    end,
  }

  handlers['track.set_volume'] = {
    undo = true,
    desc = 'Ajustar volumen de pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local db = U.num(args, 'db', { required = true, min = -150, max = 24 })
      reaper.SetMediaTrackInfo_Value(tr, 'D_VOL', U.db_to_vol(db))
      return { index = idx, name = ST.name(tr), volume_db = U.round(db, 1) }
    end,
  }

  handlers['track.adjust_volume'] = {
    undo = true,
    desc = 'Subir o bajar volumen de pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local delta = U.num(args, 'delta_db', { required = true, min = -150, max = 150 })
      local current = reaper.GetMediaTrackInfo_Value(tr, 'D_VOL')
      local target_db = U.clamp(U.vol_to_db(current) + delta, -150, 24)
      reaper.SetMediaTrackInfo_Value(tr, 'D_VOL', U.db_to_vol(target_db))
      return {
        index = idx,
        name = ST.name(tr),
        volume_db = U.round(target_db, 1),
        delta_db = U.round(delta, 1),
      }
    end,
  }

  handlers['track.set_pan'] = {
    undo = true,
    desc = 'Ajustar paneo de pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local pan = U.num(args, 'pan', { required = true, min = -100, max = 100 })
      reaper.SetMediaTrackInfo_Value(tr, 'D_PAN', U.pan_to_norm(pan))
      return { index = idx, name = ST.name(tr), pan = U.round(pan, 0) }
    end,
  }

  local function set_flag(args, parm, field, label)
    local tr, idx = ST.resolve(U.raw(args, 'track'))
    local state = U.bool(args, 'state')
    if state == nil then
      state = reaper.GetMediaTrackInfo_Value(tr, parm) == 0
    end
    reaper.SetMediaTrackInfo_Value(tr, parm, state and 1 or 0)
    local out = { index = idx, name = ST.name(tr) }
    out[field] = state
    return out
  end

  handlers['track.mute'] = {
    undo = true,
    desc = 'Silenciar pista',
    fn = function(args)
      return set_flag(args, 'B_MUTE', 'mute')
    end,
  }

  handlers['track.solo'] = {
    undo = true,
    desc = 'Hacer solo de pista',
    fn = function(args)
      return set_flag(args, 'I_SOLO', 'solo')
    end,
  }

  handlers['track.arm'] = {
    undo = true,
    desc = 'Armar pista para grabar',
    fn = function(args)
      return set_flag(args, 'I_RECARM', 'armed')
    end,
  }

  handlers['track.select'] = {
    undo = false,
    desc = 'Seleccionar pistas',
    fn = function(args)
      local list = U.raw(args, 'tracks')
      local single = U.raw(args, 'track')
      local add = U.bool(args, 'add', { default = false })

      if not add then
        reaper.Main_OnCommand(40297, 0) -- Track: Unselect all tracks
      end

      local selected = {}
      local function select_one(selector)
        local tr, idx = ST.resolve(selector)
        reaper.SetTrackSelected(tr, true)
        selected[#selected + 1] = idx
      end

      if list ~= nil then
        if type(list) ~= 'table' then
          U.fail('invalid_arg', 'el argumento "tracks" debe ser una lista')
        end
        for _, selector in ipairs(list) do
          select_one(selector)
        end
      elseif single ~= nil then
        select_one(single)
      else
        U.fail('missing_arg', 'indica "track" o "tracks"')
      end

      return { selected = selected }
    end,
  }

  handlers['track.set_color'] = {
    undo = true,
    desc = 'Colorear pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local native, r, g, b = U.color(U.raw(args, 'color'))
      reaper.SetTrackColor(tr, native)
      return {
        index = idx,
        name = ST.name(tr),
        color = string.format('#%02x%02x%02x', r, g, b),
      }
    end,
  }

  handlers['track.move'] = {
    undo = true,
    desc = 'Mover pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local target = U.num(args, 'to_index', { required = true })
      local n = ST.count()
      target = math.floor(U.clamp(target, 1, n))
      if target == idx then
        return { index = idx, moved_to = idx, name = ST.name(tr) }
      end

      reaper.SetOnlyTrackSelected(tr)
      local before = target - 1
      if before < 0 then
        before = 0
      end
      if before > n - 1 then
        before = n - 1
      end
      reaper.ReorderSelectedTracks(before, 0)
      return { index = target, moved_to = target, name = ST.name(tr), track_count = n }
    end,
  }

  handlers['track.set_monitor'] = {
    undo = true,
    desc = 'Configurar monitoreo de pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local mode = U.enum(args, 'mode', { 'off', 'normal', 'tape' }, { default = 'normal' })
      local value = 1
      if mode == 'off' then
        value = 0
      elseif mode == 'tape' then
        value = 2
      end
      reaper.SetMediaTrackInfo_Value(tr, 'I_RECMON', value)
      return { index = idx, name = ST.name(tr), monitor = mode }
    end,
  }

  handlers['track.set_input'] = {
    undo = true,
    desc = 'Elegir entrada de grabacion',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local input = U.str(args, 'input', { required = true })
      local text = U.norm(input)
      local value

      if text == 'none' or text == 'nada' or text == 'ninguna' then
        value = -1
      elseif text == 'midi' then
        value = 4096 + (63 << 5)
      elseif text:find('^midi:ch') then
        local ch = tonumber(text:match('ch(%d+)'))
        if not ch or ch < 1 or ch > 16 then
          U.fail('invalid_arg', 'canal MIDI invalido')
        end
        value = 4096 + (63 << 5) + ch
      elseif text:find('^midi:') then
        local dev = tonumber(text:match('^midi:(%d+)'))
        if not dev then
          U.fail('invalid_arg', 'entrada MIDI invalida: usa "midi", "midi:chN" o "midi:N"')
        end
        value = 4096 + (dev << 5)
      else
        -- Ojo: los patrones de Lua no tienen alternancia ("|"), van por separado.
        local channel = text:match('^mono:(%d+)$')
        local kind = nil
        if channel then
          kind = 'mono'
        else
          channel = text:match('^stereo:(%d+)$')
          if channel then
            kind = 'stereo'
          end
        end
        if not kind then
          U.fail('invalid_arg', 'entrada invalida: usa "none", "mono:N", "stereo:N" o "midi"')
        end
        channel = tonumber(channel)
        if channel < 1 or channel > 512 then
          U.fail('invalid_arg', 'numero de canal fuera de rango (1..512)')
        end
        local start = channel - 1 -- I_RECINPUT usa canales 0-based
        if kind == 'stereo' then
          value = 1024 + start
        else
          value = start
        end
      end

      reaper.SetMediaTrackInfo_Value(tr, 'I_RECINPUT', value)
      return { index = idx, name = ST.name(tr), input = input }
    end,
  }

  return handlers
end)()
