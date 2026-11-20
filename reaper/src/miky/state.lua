-- Miky · estado del proyecto y resolucion de pistas/FX

MIKY = MIKY or {}

MIKY.state = (function()
  local S = {}
  local U = MIKY.util

  local MONITOR_NAMES = { [0] = 'off', [1] = 'normal', [2] = 'tape' }

  function S.count()
    return reaper.CountTracks(0)
  end

  function S.master()
    return reaper.GetMasterTrack(0)
  end

  -- 1-based; los indices negativos cuentan desde el final (-1 = ultima pista).
  function S.track_at(index)
    local n = S.count()
    local i = math.floor(index)
    if i < 0 then
      i = n + i + 1
    end
    if i < 1 or i > n then
      return nil, i
    end
    return reaper.GetTrack(0, i - 1), i
  end

  function S.name(tr)
    if not tr then
      return ''
    end
    if tr == reaper.GetMasterTrack(0) then
      return 'Master'
    end
    local _, name = reaper.GetSetMediaTrackInfo_String(tr, 'P_NAME', '', false)
    return name or ''
  end

  -- Salidas físicas que expone el dispositivo de audio abierto en REAPER.
  function S.audio_outputs()
    local count = reaper.GetNumAudioOutputs()
    local pairs_list = {}
    for index = 0, count - 1, 2 do
      local left = reaper.GetOutputChannelName(index)
      local right = reaper.GetOutputChannelName(index + 1)
      if left == nil or left == '' then
        left = 'salida ' .. (index + 1)
      end
      if right ~= nil and right ~= '' and right ~= left then
        pairs_list[#pairs_list + 1] = left .. ' / ' .. right
      else
        pairs_list[#pairs_list + 1] = left
      end
    end
    return { count = count, pairs = pairs_list }
  end

  function S.set_name(tr, name)
    reaper.GetSetMediaTrackInfo_String(tr, 'P_NAME', name, true)
  end

  function S.index_of(tr)
    local num = reaper.GetMediaTrackInfo_Value(tr, 'IP_TRACKNUMBER')
    if num and num > 0 then
      return math.floor(num)
    end
    return nil
  end

  function S.selected_indices()
    local out = {}
    local n = S.count()
    for i = 1, n do
      local tr = reaper.GetTrack(0, i - 1)
      if reaper.GetMediaTrackInfo_Value(tr, 'I_SELECTED') > 0 then
        out[#out + 1] = i
      end
    end
    return out
  end

  local function track_list_hint()
    local n = S.count()
    if n == 0 then
      return 'el proyecto no tiene pistas'
    end
    local names = {}
    for i = 1, math.min(n, 12) do
      local nm = S.name(reaper.GetTrack(0, i - 1))
      if nm == '' then
        nm = '(sin nombre)'
      end
      names[#names + 1] = tostring(i) .. '=' .. nm
    end
    local suffix = n > 12 and (' ... (+' .. (n - 12) .. ')') or ''
    return 'pistas actuales: ' .. table.concat(names, ', ') .. suffix
  end

  -- Resuelve una pista a partir de un selector flexible:
  --   nil / ""      -> la unica pista seleccionada (si hay exactamente una)
  --   numero        -> indice 1-based (negativo = desde el final)
  --   texto         -> nombre exacto (sin acentos ni mayusculas) o subcadena unica
  --   {index=,name=}-> combinacion
  function S.resolve(selector)
    local n = S.count()

    if selector == nil or selector == '' then
      local sel = S.selected_indices()
      if #sel == 1 then
        return reaper.GetTrack(0, sel[1] - 1), sel[1]
      elseif #sel > 1 then
        U.fail(
          'track_ambiguous',
          'hay ' .. #sel .. ' pistas seleccionadas; indica cual. ' .. track_list_hint()
        )
      end
      U.fail('track_required', 'no hay ninguna pista seleccionada; indica la pista. ' .. track_list_hint())
    end

    if type(selector) == 'table' then
      if selector.index ~= nil then
        return S.resolve(selector.index)
      end
      if selector.name ~= nil then
        return S.resolve(selector.name)
      end
      U.fail('invalid_arg', 'selector de pista invalido: se esperaba index o name')
    end

    if type(selector) == 'number' then
      local tr = S.track_at(selector)
      if not tr then
        U.fail(
          'track_not_found',
          'no existe la pista ' .. tostring(selector) .. ' (el proyecto tiene ' .. n .. ')'
        )
      end
      return tr, S.index_of(tr)
    end

    if type(selector) == 'string' then
      local query = U.norm(selector)
      if query == 'master' then
        return S.master(), 0
      end

      -- "2", "-1", "pista 2", "track 2", "canal 2" -> indice
      local numeric = query:match('^(%-?%d+)$')
      if not numeric then
        numeric = query:match('^pista%s+(%-?%d+)$')
      end
      if not numeric then
        numeric = query:match('^canal%s+(%-?%d+)$')
      end
      if not numeric then
        numeric = query:match('^track%s+(%-?%d+)$')
      end
      if numeric then
        return S.resolve(tonumber(numeric))
      end

      local exact, exact_idx
      local partial = {}
      for i = 1, n do
        local tr = reaper.GetTrack(0, i - 1)
        local nm = U.norm(S.name(tr))
        if nm == query then
          exact, exact_idx = tr, i
          break
        end
        if nm ~= '' and nm:find(query, 1, true) then
          partial[#partial + 1] = { tr = tr, idx = i, name = S.name(tr) }
        elseif #nm >= 3 and query:find(nm, 1, true) then
          -- "la pista de bajo" contiene "bajo": el nombre está dentro del pedido.
          partial[#partial + 1] = { tr = tr, idx = i, name = S.name(tr) }
        end
      end
      if exact then
        return exact, exact_idx
      end
      if #partial == 1 then
        return partial[1].tr, partial[1].idx
      end
      if #partial > 1 then
        local names = {}
        for _, p in ipairs(partial) do
          names[#names + 1] = tostring(p.idx) .. '=' .. p.name
        end
        U.fail(
          'track_ambiguous',
          'varias pistas coinciden con "' .. selector .. '": ' .. table.concat(names, ', ')
        )
      end

      -- Último recurso: tolerar una letra de diferencia ("guitarra rimtica").
      if #query >= 4 then
        local close = {}
        for i = 1, n do
          local tr = reaper.GetTrack(0, i - 1)
          local nm = U.norm(S.name(tr))
          if #nm >= 4 and math.abs(#nm - #query) <= 2 and U.distance(nm, query) <= 1 then
            close[#close + 1] = { tr = tr, idx = i, name = S.name(tr) }
          end
        end
        if #close == 1 then
          return close[1].tr, close[1].idx
        end
        if #close > 1 then
          local names = {}
          for _, p in ipairs(close) do
            names[#names + 1] = tostring(p.idx) .. '=' .. p.name
          end
          U.fail(
            'track_ambiguous',
            'varias pistas se parecen a "' .. selector .. '": ' .. table.concat(names, ', ')
          )
        end
      end

      U.fail('track_not_found', 'no encontre la pista "' .. selector .. '". ' .. track_list_hint())
    end

    U.fail('invalid_arg', 'selector de pista invalido: ' .. type(selector))
  end

  function S.info(tr, idx)
    local vol = reaper.GetMediaTrackInfo_Value(tr, 'D_VOL')
    local pan = reaper.GetMediaTrackInfo_Value(tr, 'D_PAN')
    local color = reaper.GetTrackColor(tr)
    local fx, fx_count = S.fx_names(tr, 4)
    local monitor = reaper.GetMediaTrackInfo_Value(tr, 'I_RECMON')
    local info = {
      index = idx,
      name = S.name(tr),
      volume_db = U.round(U.vol_to_db(vol), 1),
      pan = U.round(pan * 100, 0),
      mute = reaper.GetMediaTrackInfo_Value(tr, 'B_MUTE') ~= 0,
      solo = reaper.GetMediaTrackInfo_Value(tr, 'I_SOLO') ~= 0,
      armed = reaper.GetMediaTrackInfo_Value(tr, 'I_RECARM') ~= 0,
      selected = reaper.GetMediaTrackInfo_Value(tr, 'I_SELECTED') > 0,
      fx_count = fx_count,
      fx = fx,
      input = S.rec_input_text(reaper.GetMediaTrackInfo_Value(tr, 'I_RECINPUT')),
      monitor = MONITOR_NAMES[monitor] or 'off',
      sends = reaper.GetTrackNumSends(tr, 0),
      outputs = reaper.GetTrackNumSends(tr, 1),
      folder_depth = reaper.GetMediaTrackInfo_Value(tr, 'I_FOLDERDEPTH'),
    }
    if color and color ~= 0 then
      local r, g, b = reaper.ColorFromNative(color)
      info.color = string.format('#%02x%02x%02x', r, g, b)
    end
    return info
  end

  function S.fx_name(tr, fx_index)
    local ok, name = reaper.TrackFX_GetFXName(tr, fx_index, '')
    if not ok then
      return nil
    end
    return name
  end

  -- Nombres de los primeros plugins de la pista (para que la IA sepa qué hay).
  function S.fx_names(tr, limit)
    limit = limit or 4
    local count = reaper.TrackFX_GetCount(tr)
    local names = {}
    for i = 0, math.min(count, limit) - 1 do
      local name = S.fx_name(tr, i)
      if name then
        names[#names + 1] = name
      end
    end
    return names, count
  end

  -- Traduce I_RECINPUT a texto legible (lo inverso de track.set_input).
  function S.rec_input_text(value)
    if value == nil or value < 0 then
      return 'none'
    end
    if (value & 4096) ~= 0 then
      local channel = value & 31
      local device = (value >> 5) & 63
      local suffix = channel == 0 and '' or (':ch' .. channel)
      if device == 63 then
        return 'midi' .. suffix
      end
      return 'midi:' .. device .. suffix
    end
    local start = (value & 1023) + 1
    if (value & 2048) ~= 0 then
      return 'multichannel:' .. start
    end
    if (value & 1024) ~= 0 then
      return 'stereo:' .. start
    end
    return 'mono:' .. start
  end

  -- Busca un marcador o región por nombre (exacto y después por subcadena).
  function S.find_marker(name)
    local query = U.norm(name)
    local total = reaper.CountProjectMarkers(0)
    local partial = nil
    for i = 0, total - 1 do
      local ok, isrgn, pos, rgnend, mname = reaper.EnumProjectMarkers3(0, i)
      if ok and ok ~= 0 then
        local norm = U.norm(mname)
        if norm == query then
          return { pos = pos, finish = rgnend, name = mname, is_region = isrgn == true }
        end
        if not partial and norm:find(query, 1, true) then
          partial = { pos = pos, finish = rgnend, name = mname, is_region = isrgn == true }
        end
      end
    end
    return partial
  end

  -- Resuelve un FX por indice 1-based o por nombre (subcadena unica).
  function S.resolve_fx(tr, selector)
    local count = reaper.TrackFX_GetCount(tr)
    if count == 0 then
      U.fail('fx_not_found', 'la pista "' .. S.name(tr) .. '" no tiene plugins cargados')
    end

    if selector == nil or selector == '' then
      return 0, S.fx_name(tr, 0)
    end

    if type(selector) == 'number' then
      local i = math.floor(selector)
      if i < 0 then
        i = count + i + 1
      end
      if i < 1 or i > count then
        U.fail('fx_not_found', 'no existe el plugin ' .. tostring(selector) .. ' (la pista tiene ' .. count .. ')')
      end
      return i - 1, S.fx_name(tr, i - 1)
    end

    if type(selector) == 'string' then
      local query = selector:lower()
      local exact, exact_idx
      local partial = {}
      for i = 0, count - 1 do
        local name = (S.fx_name(tr, i) or ''):lower()
        if name == query then
          exact, exact_idx = name, i
          break
        end
        if name:find(query, 1, true) then
          partial[#partial + 1] = { idx = i, name = S.fx_name(tr, i) }
        end
      end
      if exact then
        return exact_idx, S.fx_name(tr, exact_idx)
      end
      if #partial == 1 then
        return partial[1].idx, partial[1].name
      end
      if #partial > 1 then
        local names = {}
        for _, p in ipairs(partial) do
          names[#names + 1] = tostring(p.idx + 1) .. '=' .. p.name
        end
        U.fail('fx_ambiguous', 'varios plugins coinciden con "' .. selector .. '": ' .. table.concat(names, ', '))
      end
      U.fail('fx_not_found', 'no encontre el plugin "' .. selector .. '" en la pista "' .. S.name(tr) .. '"')
    end

    U.fail('invalid_arg', 'selector de plugin invalido')
  end

  local function markers_snapshot(limit)
    local total, num_markers, num_regions = reaper.CountProjectMarkers(0)
    local markers, regions = {}, {}
    for i = 0, total - 1 do
      local ok, isrgn, pos, rgnend, name, idx = reaper.EnumProjectMarkers3(0, i)
      if ok and ok ~= 0 then
        if isrgn then
          if #regions < limit then
            regions[#regions + 1] = {
              index = idx,
              name = name,
              start = U.round(pos, 3),
              finish = U.round(rgnend, 3),
            }
          end
        else
          if #markers < limit then
            markers[#markers + 1] = { index = idx, name = name, position = U.round(pos, 3) }
          end
        end
      end
    end
    return markers, regions, num_markers, num_regions
  end

  function S.snapshot(opts)
    opts = opts or {}
    local max_tracks = opts.max_tracks or 64
    local n = S.count()

    local tracks = {}
    for i = 1, math.min(n, max_tracks) do
      tracks[i] = S.info(reaper.GetTrack(0, i - 1), i)
    end

    local play_state = reaper.GetPlayState()
    local cursor = reaper.GetCursorPosition()
    local beats, measures = reaper.TimeMap2_timeToBeats(0, cursor)
    local ts_num, ts_den, tempo = reaper.TimeMap_GetTimeSigAtTime(0, cursor)

    local sel_start, sel_end = reaper.GetSet_LoopTimeRange(false, true, 0, 0, false)

    local project_name = reaper.GetProjectName(0)
    local _, project_file = reaper.EnumProjects(-1)
    if not project_file then
      project_file = ''
    end
    -- GetProjectPath() devuelve la carpeta de grabacion, no la del .rpp.
    local record_path = reaper.GetProjectPath()

    local render_dir, render_pattern, render_settings, bounds
    local ok_render, val_render = reaper.GetSetProjectInfo_String(0, 'RENDER_FILE', '', false)
    if ok_render then
      render_dir = val_render
    end
    local ok_pattern, val_pattern = reaper.GetSetProjectInfo_String(0, 'RENDER_PATTERN', '', false)
    if ok_pattern then
      render_pattern = val_pattern
    end
    render_settings = reaper.GetSetProjectInfo(0, 'RENDER_SETTINGS', 0, false)
    bounds = reaper.GetSetProjectInfo(0, 'RENDER_BOUNDSFLAG', 0, false)

    local markers, regions, num_markers, num_regions = markers_snapshot(opts.max_markers or 25)

    local snap = {
      project = {
        name = project_name,
        file = project_file,
        dir = U.dirname(project_file),
        record_path = record_path,
        tempo = U.round(tempo, 2),
        time_signature = tostring(ts_num) .. '/' .. tostring(ts_den),
        length = U.round(reaper.GetProjectLength(0), 2),
        track_count = n,
      },
      transport = {
        playing = (play_state & 1) ~= 0,
        paused = (play_state & 2) ~= 0,
        recording = (play_state & 4) ~= 0,
        position = U.round(reaper.GetPlayPosition(), 3),
        cursor = U.round(cursor, 3),
        cursor_bar = measures + 1,
        cursor_beat = U.round(beats, 2),
      },
      selected_tracks = S.selected_indices(),
      tracks = tracks,
      audio = {
        outputs = S.audio_outputs(),
      },
      markers = markers,
      regions = regions,
      marker_count = num_markers,
      region_count = num_regions,
      time_selection = (sel_end > sel_start) and { start = U.round(sel_start, 3), finish = U.round(sel_end, 3) }
        or nil,
      render = {
        directory = render_dir,
        pattern = render_pattern,
        settings = render_settings,
        bounds_flag = bounds,
      },
    }

    if reaper.APIExists('IsProjectDirty') then
      snap.project.dirty = reaper.IsProjectDirty(0) == 1
    end

    return snap
  end

  return S
end)()
