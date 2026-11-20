-- REAPER simulado para tests del puente (no se instala en REAPER).
-- Implementa el subconjunto de la API que usa Miky, con un modelo de proyecto
-- en memoria. La idea es detectar errores de lÃ³gica sin abrir el DAW.

MOCK = {
  tempo = 120,
  playing = false,
  recording = false,
  cursor = 0.0,
  loop_start = 0.0,
  loop_end = 4.0,
  metronome = false,
  loop_repeat = false,
  dirty = 0,
  undo_stack = {},
  undo_descriptions = {},
  commands = {},
  markers = {},
  render = {},
  project_file = "",
  project_name = "",
  resource_path = "C:\\mock\\REAPER",
  tracks = {},
  items = {},
}

local function new_track(name)
  return {
    name = name or "",
    vol = 1.0,
    pan = 0.0,
    mute = 0,
    solo = 0,
    arm = 0,
    selected = false,
    recmon = 0,
    recinput = -1,
    folderdepth = 0,
    color = 0,
    fx = {},
    sends = {},
  }
end

local fx_param_db = {
  ["ReaComp"] = {
    { name = "Threshold", min = -150, max = 12 },
    { name = "Ratio", min = 1, max = 20 },
    { name = "Attack", min = 0, max = 250 },
    { name = "Release", min = 0, max = 5000 },
  },
  ["ReaEQ"] = {
    { name = "Freq-Low Shelf", min = 20, max = 20000 },
    { name = "Gain-Low Shelf", min = -24, max = 24 },
  },
  ["JS: utility/volume"] = {
    { name = "Volume", min = -150, max = 12 },
  },
}

local installed_fx = {
  "VST: SSL Native Bus Compressor (SSL)",
  "VST: FabFilter Pro-Q 4 (FabFilter)",
  "VST: API 550B (Waves)",
  "VST: Pultec EQP-1A (Universal Audio)",
  "VST: ReaComp (Cockos)",
  "VST: ReaEQ (Cockos)",
  "VST3: Eamut Drums Compressor (Eamut Audio)",
  "JS: utility/volume",
}

local reaper = {}

-- ---------------------------------------------------------------- bÃ¡sicos

function reaper.GetAppVersion()
  return "7.84/mock"
end

function reaper.GetResourcePath()
  return MOCK.resource_path
end

function reaper.time_precise()
  return os.clock()
end

function reaper.defer(fn)
  MOCK.deferred = fn
end

function reaper.APIExists(name)
  return reaper[name] ~= nil
end

function reaper.kbd_getTextFromCmd(cmd, _section)
  return "Accion " .. tostring(cmd)
end

function reaper.IsProjectDirty(_proj)
  return MOCK.dirty
end

-- ---------------------------------------------------------------- proyecto

function reaper.EnumProjects(idx)
  if idx == -1 then
    return 0, MOCK.project_file
  end
  return 0, MOCK.project_file
end

function reaper.GetProjectName(_proj)
  return MOCK.project_name
end

function reaper.GetProjectPath()
  return "C:\\mock\\render"
end

function reaper.GetProjectLength(_proj)
  local length = 60.0
  for _, marker in ipairs(MOCK.markers) do
    local endpos = marker.rgnend or marker.pos
    if endpos and endpos > length then
      length = endpos
    end
  end
  return length
end

function reaper.Main_SaveProject(_proj, _force)
  MOCK.dirty = 0
  MOCK.saved = true
end

function reaper.Main_SaveProjectEx(_proj, filename, options)
  MOCK.project_file = filename
  MOCK.project_name = filename:match("[^\\/]+$") or filename
  MOCK.dirty = 0
  MOCK.saved = true
end

function reaper.PreventUIRefresh(_count) end
function reaper.UpdateArrange() end
function reaper.TrackList_AdjustWindows(_minor) end

function reaper.Undo_BeginBlock() end

function reaper.Undo_EndBlock(desc, _flags)
  MOCK.undo_descriptions[#MOCK.undo_descriptions + 1] = desc
end

function reaper.Undo_CanUndo2(_proj)
  local count = #MOCK.undo_descriptions
  if count == 0 then
    return nil
  end
  return MOCK.undo_descriptions[count]
end

function reaper.GetSetProjectInfo(_proj, desc, value, is_set)
  if is_set then
    MOCK.render[desc] = value
    return value
  end
  return MOCK.render[desc] or 0
end

function reaper.GetSetProjectInfo_String(_proj, desc, value, is_set)
  if is_set then
    MOCK.render[desc] = value
    return true, value
  end
  if desc == "RENDER_TARGETS" then
    local dir = MOCK.render["RENDER_FILE"] or ""
    local pattern = MOCK.render["RENDER_PATTERN"] or "$project"
    return true, dir .. "\\" .. pattern .. ".wav"
  end
  local stored = MOCK.render[desc]
  if stored == nil then
    return false, ""
  end
  return true, tostring(stored)
end

-- ---------------------------------------------------------------- pistas

function reaper.CountTracks(_proj)
  return #MOCK.tracks
end

function reaper.GetTrack(_proj, index)
  return MOCK.tracks[index + 1]
end

function reaper.GetMasterTrack(_proj)
  return MOCK.master or { name = "MASTER", vol = 1.0, pan = 0.0, fx = {} }
end

-- Medidor simulado: cada pista puede fijar su peak; si no, uno por defecto.
function reaper.Track_GetPeakInfo(track, channel)
  if not track then
    return 0
  end
  if track.peak ~= nil then
    return track.peak
  end
  if channel and channel > 0 then
    return 0.0
  end
  return MOCK.default_peak or 0.25
end

-- Abrir proyectos: se registra el pedido y se cambia el proyecto actual.
function reaper.Main_openProject(path)
  MOCK.opened_project = path
  MOCK.project_file = (path or ""):gsub("^noprompt:", "")
  return true
end

-- Listado de archivos de una carpeta (para buscar .rpp cerca del proyecto).
function reaper.EnumerateFiles(dir, index)
  local list = MOCK.dir_files and MOCK.dir_files[dir]
  if not list then
    return nil
  end
  return list[index + 1]
end

function reaper.InsertTrackInProject(_proj, index, _flags)
  local track = new_track("")
  table.insert(MOCK.tracks, index + 1, track)
  for _, other in ipairs(MOCK.tracks) do
    other.selected = false
  end
  track.selected = true
end

function reaper.InsertTrackAtIndex(index, _defaults)
  reaper.InsertTrackInProject(0, index, 1)
end

function reaper.DeleteTrack(track)
  for index, candidate in ipairs(MOCK.tracks) do
    if candidate == track then
      table.remove(MOCK.tracks, index)
      return
    end
  end
end

function reaper.GetSetMediaTrackInfo_String(track, param, value, set)
  if param == "P_NAME" then
    if set then
      track.name = value
      return true, track.name
    end
    return true, track.name
  end
  return false, ""
end

local numeric_fields = {
  D_VOL = "vol",
  D_PAN = "pan",
  B_MUTE = "mute",
  I_SOLO = "solo",
  I_RECARM = "arm",
  I_SELECTED = "selected",
  I_RECMON = "recmon",
  I_RECINPUT = "recinput",
  I_FOLDERDEPTH = "folderdepth",
}

function reaper.GetMediaTrackInfo_Value(track, param)
  if param == "IP_TRACKNUMBER" then
    for index, candidate in ipairs(MOCK.tracks) do
      if candidate == track then
        return index
      end
    end
    return 0
  end
  local field = numeric_fields[param]
  if field == nil then
    return 0
  end
  local value = track[field]
  if type(value) == "boolean" then
    return value and 1 or 0
  end
  return value or 0
end

function reaper.SetMediaTrackInfo_Value(track, param, value)
  local field = numeric_fields[param]
  if field == nil then
    return false
  end
  if field == "selected" then
    track.selected = value ~= 0
  else
    track[field] = value
  end
  return true
end

function reaper.SetOnlyTrackSelected(track)
  for _, candidate in ipairs(MOCK.tracks) do
    candidate.selected = candidate == track
  end
end

function reaper.SetTrackSelected(track, selected)
  track.selected = selected and true or false
end

function reaper.ReorderSelectedTracks(before_index, _folder)
  local selected = {}
  for _, track in ipairs(MOCK.tracks) do
    if track.selected then
      selected[#selected + 1] = track
    end
  end
  if #selected == 0 then
    return false
  end
  for _, track in ipairs(selected) do
    for index, candidate in ipairs(MOCK.tracks) do
      if candidate == track then
        table.remove(MOCK.tracks, index)
        break
      end
    end
  end
  local insert_at = before_index + 1
  for offset, track in ipairs(selected) do
    table.insert(MOCK.tracks, insert_at + offset - 1, track)
  end
  return true
end

function reaper.ColorToNative(r, g, b)
  return (r or 0) | ((g or 0) << 8) | ((b or 0) << 16)
end

function reaper.ColorFromNative(color)
  local value = color or 0
  return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
end

function reaper.SetTrackColor(track, color)
  track.color = color | 0x1000000
end

function reaper.GetTrackColor(track)
  return track.color or 0
end

function reaper.GetTrackStateChunk(track, _value, _isundo)
  local chunk = "<TRACK {11111111-2222-3333-4444-555555555555}\n"
    .. "  NAME " .. (track.name or "") .. "\n"
    .. "  VOLPAN " .. tostring(track.vol) .. " " .. tostring(track.pan) .. " 1 -1\n"
    .. "  MUTESOLO " .. tostring(track.mute) .. " " .. tostring(track.solo) .. " 0\n"
    .. ">\n"
  return true, chunk
end

function reaper.SetTrackStateChunk(track, chunk, _isundo)
  local name = chunk:match("NAME ([^\n]*)")
  if name then
    track.name = name
  end
  return true
end

-- ---------------------------------------------------------------- FX

local function param_table(fx)
  if fx_param_db[fx.name] then
    return fx_param_db[fx.name]
  end
  -- Los nombres reales vienen con prefijo y fabricante ("VST: ReaComp (Cockos)").
  local lowered = fx.name:lower()
  for key, value in pairs(fx_param_db) do
    if lowered:find(key:lower(), 1, true) then
      return value
    end
  end
  return {}
end

local function mock_installed_match(name)
  if name == nil or name == '' or name == 'NONEXISTENT' then
    return nil
  end
  local needle = name:lower()
  for _, installed in ipairs(installed_fx) do
    if installed:lower():find(needle, 1, true) then
      return installed
    end
  end
  return nil
end

function reaper.TrackFX_AddByName(track, name, _recfx, instantiate)
  if instantiate == 0 then
    for index, fx in ipairs(track.fx) do
      if fx.name:lower():find(name:lower(), 1, true) then
        return index - 1
      end
    end
    return -1
  end
  local resolved = mock_installed_match(name)
  if not resolved then
    return -1
  end
  local fx = { name = resolved, enabled = true, params = {} }
  if instantiate <= -1000 then
    local position = -1000 - instantiate + 1
    table.insert(track.fx, position, fx)
    return position - 1
  end
  table.insert(track.fx, fx)
  return #track.fx - 1
end

function reaper.TrackFX_GetCount(track)
  return #track.fx
end

function reaper.TrackFX_GetFXName(track, index)
  local fx = track.fx[index + 1]
  if not fx then
    return false, ""
  end
  return true, fx.name
end

function reaper.TrackFX_GetNumParams(track, index)
  local fx = track.fx[index + 1]
  if not fx then
    return 0
  end
  return #param_table(fx)
end

function reaper.TrackFX_GetParamName(track, index, param)
  local fx = track.fx[index + 1]
  if not fx then
    return false, ""
  end
  local spec = param_table(fx)[param + 1]
  return true, spec and spec.name or ""
end

function reaper.TrackFX_GetParam(track, index, param)
  local fx = track.fx[index + 1]
  if not fx then
    return 0, 0, 0
  end
  local spec = param_table(fx)[param + 1]
  if not spec then
    return 0, 0, 0
  end
  local stored = fx.params[param]
  local value = stored or ((spec.min + spec.max) / 2)
  return value, spec.min, spec.max
end

function reaper.TrackFX_SetParam(track, index, param, value)
  local fx = track.fx[index + 1]
  if not fx then
    return false
  end
  fx.params[param] = value
  return true
end

function reaper.TrackFX_SetParamNormalized(track, index, param, value)
  local fx = track.fx[index + 1]
  if not fx then
    return false
  end
  local spec = param_table(fx)[param + 1]
  if not spec then
    return false
  end
  fx.params[param] = spec.min + (spec.max - spec.min) * value
  return true
end

function reaper.TrackFX_GetParamNormalized(track, index, param)
  local fx = track.fx[index + 1]
  if not fx then
    return 0
  end
  local spec = param_table(fx)[param + 1]
  if not spec then
    return 0
  end
  local value = fx.params[param] or ((spec.min + spec.max) / 2)
  return (value - spec.min) / (spec.max - spec.min)
end

function reaper.TrackFX_GetFormattedParamValue(track, index, param, _value)
  local fx = track.fx[index + 1]
  if not fx then
    return false, ""
  end
  local spec = param_table(fx)[param + 1]
  local value = fx.params[param] or 0
  return true, string.format("%.2f", value) .. (spec and "" or "")
end

function reaper.TrackFX_GetEnabled(track, index)
  local fx = track.fx[index + 1]
  return fx ~= nil and fx.enabled or false
end

function reaper.TrackFX_SetEnabled(track, index, enabled)
  local fx = track.fx[index + 1]
  if not fx then
    return false
  end
  fx.enabled = enabled and true or false
  return true
end

function reaper.TrackFX_Delete(track, index)
  local fx = track.fx[index + 1]
  if not fx then
    return false
  end
  table.remove(track.fx, index + 1)
  return true
end

function reaper.TrackFX_SetOpen(track, index, open)
  local fx = track.fx[index + 1]
  if fx then
    fx.open = open
  end
end

function reaper.TrackFX_GetOpen(track, index)
  local fx = track.fx[index + 1]
  return fx ~= nil and fx.open == true or false
end

-- ---------------------------------------------------------------- transporte

function reaper.GetPlayState()
  local state = 0
  if MOCK.playing then
    state = state | 1
  end
  if MOCK.recording then
    state = state | 4
  end
  return state
end

function reaper.GetPlayPosition()
  return MOCK.cursor
end

function reaper.GetCursorPosition()
  return MOCK.cursor
end

function reaper.SetEditCurPos(position, _moveview, _seekplay)
  MOCK.cursor = position
end

function reaper.Master_GetTempo()
  return MOCK.tempo
end

function reaper.SetCurrentBPM(_proj, bpm, _undo)
  MOCK.tempo = bpm
end

function reaper.TimeMap_GetTimeSigAtTime(_proj, _time)
  return 4, 4, MOCK.tempo
end

function reaper.TimeMap2_timeToBeats(_proj, tpos)
  local beats_total = tpos * MOCK.tempo / 60.0
  local measures = math.floor(beats_total / 4.0)
  local beats_in_measure = beats_total - measures * 4.0
  return beats_in_measure, measures, 4, beats_total, 4
end

function reaper.TimeMap2_beatsToTime(_proj, tpos, measures)
  local beats_total = (measures or 0) * 4.0 + (tpos or 0)
  return beats_total * 60.0 / MOCK.tempo
end

function reaper.GetSet_LoopTimeRange(is_set, _is_loop, start, finish, _allow)
  if is_set then
    MOCK.loop_start = start
    MOCK.loop_end = finish
  end
  return MOCK.loop_start, MOCK.loop_end
end

function reaper.AddProjectMarker2(_proj, isrgn, pos, rgnend, name, wantidx, color)
  local marker = {
    isrgn = isrgn and true or false,
    pos = pos,
    rgnend = rgnend or 0,
    name = name or "",
    index = wantidx,
    color = color or 0,
  }
  MOCK.markers[#MOCK.markers + 1] = marker
  return #MOCK.markers
end

function reaper.CountProjectMarkers(_proj)
  local markers, regions = 0, 0
  for _, marker in ipairs(MOCK.markers) do
    if marker.isrgn then
      regions = regions + 1
    else
      markers = markers + 1
    end
  end
  return #MOCK.markers, markers, regions
end

function reaper.EnumProjectMarkers3(_proj, index)
  local marker = MOCK.markers[index + 1]
  if not marker then
    return 0
  end
  return 1, marker.isrgn, marker.pos, marker.rgnend, marker.name, index + 1, marker.color
end

function reaper.GetToggleCommandState(command)
  if command == 40364 then
    return MOCK.metronome and 1 or 0
  end
  if command == 1068 then
    return MOCK.loop_repeat and 1 or 0
  end
  if command == 40078 then
    return MOCK.mixer and 1 or 0
  end
  if command == 40251 then
    return MOCK.routing and 1 or 0
  end
  return 0
end

function reaper.Main_OnCommand(command, _flag)
  MOCK.commands[#MOCK.commands + 1] = command
  if command == 1007 then
    MOCK.playing = true
  elseif command == 1016 then
    MOCK.playing = false
    MOCK.recording = false
  elseif command == 1013 then
    MOCK.playing = true
    MOCK.recording = true
  elseif command == 40029 then
    MOCK.undo = (MOCK.undo or 0) + 1
  elseif command == 40030 then
    MOCK.redo = (MOCK.redo or 0) + 1
  elseif command == 40062 then
    local source
    for _, track in ipairs(MOCK.tracks) do
      if track.selected then
        source = track
        break
      end
    end
    if source then
      local copy = {}
      for key, value in pairs(source) do
        copy[key] = value
      end
      copy.fx = {}
      for _, fx in ipairs(source.fx) do
        copy.fx[#copy.fx + 1] = { name = fx.name, enabled = fx.enabled, params = {} }
      end
      table.insert(MOCK.tracks, copy)
    end
  elseif command == 40297 then
    for _, track in ipairs(MOCK.tracks) do
      track.selected = false
    end
  elseif command == 40364 then
    MOCK.metronome = not MOCK.metronome
  elseif command == 40078 then
    MOCK.mixer = not MOCK.mixer
  elseif command == 40251 then
    MOCK.routing = not MOCK.routing
  elseif command == 1068 then
    MOCK.loop_repeat = not MOCK.loop_repeat
  elseif command == 42230 or command == 41824 then
    MOCK.last_render = MOCK.render
  elseif command == 40004 then
    MOCK.quit_requested = true
  end
end

-- ---------------------------------------------------------------- items

function MOCK.add_item(track_index, position, length, selected)
  local track = MOCK.tracks[track_index]
  if not track then
    return nil
  end
  local item = {
    track = track,
    pos = position or 0,
    len = length or 1,
    selected = selected ~= false,
  }
  MOCK.items[#MOCK.items + 1] = item
  return item
end

function reaper.EnumInstalledFX(index)
  local name = installed_fx[index + 1]
  if name then
    return true, name, "fxident" .. index
  end
  return false, "", ""
end

function reaper.CountMediaItems(_proj)
  return #MOCK.items
end

function reaper.GetMediaItem(_proj, index)
  return MOCK.items[index + 1]
end

local function mock_selected_items()
  local out = {}
  for _, item in ipairs(MOCK.items) do
    if item.selected then
      out[#out + 1] = item
    end
  end
  return out
end

function reaper.CountSelectedMediaItems(_proj)
  return #mock_selected_items()
end

function reaper.GetSelectedMediaItem(_proj, index)
  return mock_selected_items()[index + 1]
end

function reaper.IsMediaItemSelected(item)
  return item ~= nil and item.selected == true
end

function reaper.SetMediaItemSelected(item, selected)
  if item then
    item.selected = selected and true or false
  end
end

function reaper.GetMediaItem_Track(item)
  return item and item.track
end

function reaper.GetMediaItemInfo_Value(item, parm)
  if parm == 'D_POSITION' then
    return item.pos
  end
  if parm == 'D_LENGTH' then
    return item.len
  end
  return 0
end

function reaper.SetMediaItemInfo_Value(item, parm, value)
  if parm == 'D_POSITION' then
    item.pos = value
  elseif parm == 'D_LENGTH' then
    item.len = value
  end
  return true
end

function reaper.CountTrackMediaItems(track)
  local count = 0
  for _, item in ipairs(MOCK.items) do
    if item.track == track then
      count = count + 1
    end
  end
  return count
end

function reaper.GetTrackMediaItem(track, index)
  local found = 0
  for _, item in ipairs(MOCK.items) do
    if item.track == track then
      if found == index then
        return item
      end
      found = found + 1
    end
  end
  return nil
end

function reaper.SplitMediaItem(item, position)  if not item then
    return nil
  end
  if position <= item.pos or position >= item.pos + item.len then
    return nil
  end
  local right = {
    track = item.track,
    pos = position,
    len = item.pos + item.len - position,
    selected = item.selected,
  }
  item.len = position - item.pos
  MOCK.items[#MOCK.items + 1] = right
  return right
end

function reaper.DeleteTrackMediaItem(_track, item)
  for index, candidate in ipairs(MOCK.items) do
    if candidate == item then
      table.remove(MOCK.items, index)
      return true
    end
  end
  return false
end

-- ---------------------------------------------------------------- envíos

function reaper.GetNumAudioOutputs()
  return MOCK.audio_outputs or 4
end

function reaper.GetOutputChannelName(index)
  return 'Salida ' .. (index + 1)
end

function reaper.GetTrackNumSends(track, category)
  if category == 0 then
    return #(track.sends or {})
  end
  if category == 1 then
    return #(track.outputs or {})
  end
  return 0
end

function reaper.CreateTrackSend(track, dest)
  if dest == nil then
    -- Salida física (hardware output).
    track.outputs = track.outputs or {}
    track.outputs[#track.outputs + 1] = { destchan = 0, vol = 1.0 }
    return #track.outputs - 1
  end
  track.sends = track.sends or {}
  track.sends[#track.sends + 1] = { dest = dest, vol = 1.0, mode = 0 }
  return #track.sends - 1
end

function reaper.RemoveTrackSend(track, category, index)
  if category == 1 then
    if not track.outputs or not track.outputs[index + 1] then
      return false
    end
    table.remove(track.outputs, index + 1)
    return true
  end
  if category ~= 0 then
    return false
  end
  if not track.sends or not track.sends[index + 1] then
    return false
  end
  table.remove(track.sends, index + 1)
  return true
end

function reaper.GetTrackSendInfo_Value(track, category, index, parm)
  local send
  if category == 1 then
    send = track.outputs and track.outputs[index + 1]
  else
    send = track.sends and track.sends[index + 1]
  end
  if not send then
    return 0
  end
  if parm == 'P_DESTTRACK' then
    return send.dest
  end
  if parm == 'D_VOL' then
    return send.vol
  end
  if parm == 'I_SENDMODE' then
    return send.mode
  end
  if parm == 'I_DSTCHAN' then
    return send.destchan or 0
  end
  return 0
end

function reaper.SetTrackSendInfo_Value(track, category, index, parm, value)
  local send
  if category == 1 then
    send = track.outputs and track.outputs[index + 1]
  else
    send = track.sends and track.sends[index + 1]
  end
  if not send then
    return false
  end
  if parm == 'D_VOL' then
    send.vol = value
  elseif parm == 'I_SENDMODE' then
    send.mode = value
  elseif parm == 'I_DSTCHAN' then
    send.destchan = value
  end
  return true
end

function reaper.TrackFX_CopyToTrack(src_track, src_fx, dest_track, dest_fx, is_move)
  local fx = src_track.fx[src_fx + 1]
  if not fx then
    return false
  end
  local copy = { name = fx.name, enabled = fx.enabled, params = {} }
  for key, value in pairs(fx.params or {}) do
    copy.params[key] = value
  end
  if dest_fx == nil or dest_fx < 0 then
    dest_track.fx[#dest_track.fx + 1] = copy
  else
    table.insert(dest_track.fx, dest_fx + 1, copy)
  end
  if is_move then
    table.remove(src_track.fx, src_fx + 1)
  end
  return true
end

-- ---------------------------------------------------------------- reset

function MOCK.reset(count)
  MOCK.tracks = {}
  MOCK.items = {}
  MOCK.markers = {}
  MOCK.commands = {}
  MOCK.render = {}
  MOCK.undo_descriptions = {}
  MOCK.tempo = 120
  MOCK.playing = false
  MOCK.recording = false
  MOCK.cursor = 0
  MOCK.metronome = false
  MOCK.loop_repeat = false
  MOCK.mixer = false
  MOCK.routing = false
  MOCK.project_file = ""
  MOCK.project_name = ""
  MOCK.saved = false
  for index = 1, (count or 0) do
    MOCK.tracks[index] = new_track("Pista " .. index)
  end
end

MOCK.reset(0)
reaper.MOCK = MOCK

return reaper
