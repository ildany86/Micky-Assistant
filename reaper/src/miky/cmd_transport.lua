-- Miky · transporte y proyecto (transport.*, project.*)

MIKY = MIKY or {}

MIKY.cmd_transport = (function()
  local U = MIKY.util
  local ST = MIKY.state

  local handlers = {}

  local function play_state()
    return reaper.GetPlayState()
  end

  handlers['transport.play'] = {
    undo = false,
    desc = 'Reproducir',
    fn = function()
      if (play_state() & 1) == 0 then
        reaper.Main_OnCommand(1007, 0) -- Transport: Play
      end
      return { playing = (play_state() & 1) ~= 0 }
    end,
  }

  handlers['transport.stop'] = {
    undo = false,
    desc = 'Detener',
    fn = function()
      if (play_state() & 4) ~= 0 then
        -- 40667 = "Parar y guardar todos los archivos grabados". Se usa al parar
        -- una grabación porque la acción normal (1016) puede abrir el diálogo
        -- modal "Acciones para los archivos grabados", y un diálogo modal
        -- congela el puente hasta que alguien lo cierre a mano.
        reaper.Main_OnCommand(40667, 0)
        if (play_state() & 4) ~= 0 then
          reaper.Main_OnCommand(1016, 0)
        end
      else
        reaper.Main_OnCommand(1016, 0) -- Transport: Stop
      end
      return { playing = false, recording = false }
    end,
  }

  handlers['transport.pause'] = {
    undo = false,
    desc = 'Pausar',
    fn = function()
      reaper.Main_OnCommand(1008, 0) -- Transport: Pause
      return { paused = (play_state() & 2) ~= 0 }
    end,
  }

  handlers['transport.record'] = {
    undo = false,
    desc = 'Grabar',
    fn = function()
      if (play_state() & 4) ~= 0 then
        return { recording = true, already = true }
      end

      local armed = {}
      for i = 1, ST.count() do
        local tr = reaper.GetTrack(0, i - 1)
        if reaper.GetMediaTrackInfo_Value(tr, 'I_RECARM') > 0 then
          armed[#armed + 1] = ST.name(tr)
        end
      end
      if #armed == 0 then
        U.fail(
          'no_armed_track',
          'no hay ninguna pista armada para grabar. Arma una pista primero.'
        )
      end

      reaper.Main_OnCommand(1013, 0) -- Transport: Record
      return { recording = (play_state() & 4) ~= 0, armed = armed }
    end,
  }

  handlers['transport.set_position'] = {
    undo = false,
    desc = 'Mover el cursor',
    fn = function(args)
      local seconds = U.num(args, 'seconds')
      local bar = U.num(args, 'bar')
      local beat = U.num(args, 'beat', { default = 0 })
      local pos

      if bar then
        pos = reaper.TimeMap2_beatsToTime(0, beat, math.floor(bar) - 1)
      elseif seconds then
        pos = seconds
      else
        U.fail('missing_arg', 'indica "bar" o "seconds"')
      end

      pos = math.max(0, pos)
      reaper.SetEditCurPos(pos, true, true)
      return { position = U.round(pos, 3), bar = bar, beat = beat }
    end,
  }

  handlers['transport.goto_start'] = {
    undo = false,
    desc = 'Ir al comienzo',
    fn = function()
      reaper.SetEditCurPos(0, true, true)
      return { position = 0 }
    end,
  }

  handlers['transport.goto_end'] = {
    undo = false,
    desc = 'Ir al final',
    fn = function()
      local pos = reaper.GetProjectLength(0)
      reaper.SetEditCurPos(pos, true, true)
      return { position = U.round(pos, 3) }
    end,
  }

  handlers['transport.set_loop'] = {
    undo = false,
    desc = 'Configurar loop',
    fn = function(args)
      local start, finish = U.num(args, 'start'), U.num(args, 'finish')
      local enabled = U.bool(args, 'enabled')

      if start and finish then
        reaper.GetSet_LoopTimeRange(true, true, start, finish, false)
      end

      if enabled ~= nil then
        local current = reaper.GetToggleCommandState(1068) == 1
        if current ~= enabled then
          reaper.Main_OnCommand(1068, 0) -- Transport: Toggle repeat
        end
      end

      local s, e = reaper.GetSet_LoopTimeRange(false, true, 0, 0, false)
      return {
        start = U.round(s, 3),
        finish = U.round(e, 3),
        enabled = reaper.GetToggleCommandState(1068) == 1,
      }
    end,
  }

  handlers['transport.goto_marker'] = {
    undo = false,
    desc = 'Ir a un marcador o region',
    fn = function(args)
      local name = U.str(args, 'name', { required = true })
      local hit = ST.find_marker(name)
      if not hit then
        U.fail('marker_not_found', 'no encontre un marcador o region llamada "' .. name .. '"')
      end
      reaper.SetEditCurPos(hit.pos, true, true)
      return { name = hit.name, position = U.round(hit.pos, 3), is_region = hit.is_region }
    end,
  }

  -- ---------------- Proyecto ----------------

  handlers['project.save'] = {
    undo = false,
    desc = 'Guardar proyecto',
    fn = function()
      local _, file = reaper.EnumProjects(-1)
      if not file or file == '' then
        U.fail('project_unsaved', 'el proyecto nunca se guardo: usa project.save_as con una ruta')
      end
      reaper.Main_SaveProject(0, false)
      return { saved = true, path = file }
    end,
  }

  handlers['project.save_as'] = {
    undo = false,
    desc = 'Guardar proyecto como',
    fn = function(args)
      local target = U.str(args, 'path', { required = true })
      if not target:lower():match('%.rpp$') then
        target = target .. '.rpp'
      end
      reaper.Main_SaveProjectEx(0, target, 8)
      local _, check = reaper.EnumProjects(-1)
      if not check or check == '' then
        U.fail('reaper_error', 'REAPER no pudo guardar el proyecto en ' .. target)
      end
      return { saved = true, path = check }
    end,
  }

  handlers['project.undo'] = {
    undo = false,
    desc = 'Deshacer',
    fn = function()
      local can = reaper.Undo_CanUndo2(0)
      if can == nil then
        return { undone = false, reason = 'no hay nada para deshacer' }
      end
      reaper.Main_OnCommand(40029, 0) -- Edit: Undo
      return { undone = true, action = can }
    end,
  }

  handlers['project.redo'] = {
    undo = false,
    desc = 'Rehacer',
    fn = function()
      reaper.Main_OnCommand(40030, 0) -- Edit: Redo
      return { redone = true }
    end,
  }

  handlers['project.set_tempo'] = {
    undo = true,
    desc = 'Cambiar tempo',
    fn = function(args)
      local bpm = U.num(args, 'bpm', { required = true, min = 5, max = 960 })
      reaper.SetCurrentBPM(0, bpm, true)
      return { bpm = U.round(reaper.Master_GetTempo(), 2) }
    end,
  }

  handlers['project.set_metronome'] = {
    undo = false,
    desc = 'Activar o desactivar metronomo',
    fn = function(args)
      local enabled = U.bool(args, 'enabled')
      local current = reaper.GetToggleCommandState(40364) == 1
      if enabled == nil then
        enabled = not current
      end
      if current ~= enabled then
        reaper.Main_OnCommand(40364, 0) -- Options: Toggle metronome
      end
      return { metronome = reaper.GetToggleCommandState(40364) == 1 }
    end,
  }

  handlers['view.mixer'] = {
    undo = false,
    desc = 'Mostrar u ocultar el mezclador',
    fn = function(args)
      local visible = U.bool(args, 'visible')
      local current = reaper.GetToggleCommandState(40078) == 1
      if visible == nil then
        visible = not current
      end
      if current ~= visible then
        reaper.Main_OnCommand(40078, 0) -- Ver: Mezclador > Mostrar/Ocultar
      end
      local now_visible = reaper.GetToggleCommandState(40078) == 1
      return {
        mixer_visible = now_visible,
        state_text = now_visible and 'mostrado' or 'oculto',
      }
    end,
  }

  handlers['view.routing'] = {
    undo = false,
    desc = 'Alternar la ventana de ruteo',
    fn = function()
      -- La ventana de ruteo no expone un estado confiable de abierta/cerrada,
      -- así que la acción siempre alterna: sirve tanto para abrir como cerrar.
      reaper.Main_OnCommand(40251, 0) -- Ver: Ventana de ruteo
      return {}
    end,
  }

  return handlers
end)()
