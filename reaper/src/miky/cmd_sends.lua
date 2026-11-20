-- Miky · envíos entre pistas (send.*)

MIKY = MIKY or {}

MIKY.cmd_sends = (function()
  local U = MIKY.util
  local ST = MIKY.state

  local handlers = {}

  local function find_send(from, dest)
    local count = reaper.GetTrackNumSends(from, 0)
    for index = 0, count - 1 do
      local track = reaper.GetTrackSendInfo_Value(from, 0, index, 'P_DESTTRACK')
      if track == dest then
        return index
      end
    end
    return nil
  end

  local function resolve_pair(args)
    local from, from_idx = ST.resolve(U.raw(args, 'from'))
    local to_name = U.str(args, 'to', { required = true })
    local to, to_idx = ST.resolve(to_name)
    if from == to then
      U.fail('invalid_arg', 'no se puede enviar una pista a si misma')
    end
    return from, from_idx, to, to_idx
  end

  local MODE_VALUES = { post_fader = 0, pre_fx = 1, post_fx = 3 }

  handlers['send.add'] = {
    undo = true,
    desc = 'Crear envío',
    fn = function(args)
      local from, from_idx, to, to_idx = resolve_pair(args)
      local mode = U.enum(args, 'mode', { 'post_fader', 'pre_fx', 'post_fx' }, { default = 'post_fader' })
      local level = U.num(args, 'level_db', { min = -150, max = 12 })

      if find_send(from, to) then
        U.fail(
          'send_exists',
          'la pista "' .. ST.name(from) .. '" ya tiene un envio a "' .. ST.name(to) .. '"'
        )
      end

      local index = reaper.CreateTrackSend(from, to)
      if index < 0 then
        U.fail('reaper_error', 'REAPER no pudo crear el envio')
      end

      reaper.SetTrackSendInfo_Value(from, 0, index, 'I_SENDMODE', MODE_VALUES[mode])
      if level then
        reaper.SetTrackSendInfo_Value(from, 0, index, 'D_VOL', U.db_to_vol(level))
      end

      return {
        index = index + 1,
        from = ST.name(from),
        from_index = from_idx,
        to = ST.name(to),
        to_index = to_idx,
        mode = mode,
        level_db = level and U.round(level, 1) or 0,
      }
    end,
  }

  handlers['send.remove'] = {
    undo = true,
    desc = 'Quitar envío',
    fn = function(args)
      local from, from_idx, to, to_idx = resolve_pair(args)
      local index = find_send(from, to)
      if index == nil then
        U.fail(
          'send_not_found',
          'la pista "' .. ST.name(from) .. '" no tiene un envio a "' .. ST.name(to) .. '"'
        )
      end
      local removed = reaper.RemoveTrackSend(from, 0, index)
      if not removed then
        U.fail('reaper_error', 'REAPER no pudo quitar el envio')
      end
      return {
        from = ST.name(from),
        from_index = from_idx,
        to = ST.name(to),
        to_index = to_idx,
        sends_left = reaper.GetTrackNumSends(from, 0),
      }
    end,
  }

  handlers['send.set_level'] = {
    undo = true,
    desc = 'Ajustar nivel de envío',
    fn = function(args)
      local from, from_idx, to, to_idx = resolve_pair(args)
      local db = U.num(args, 'db', { required = true, min = -150, max = 24 })
      local index = find_send(from, to)
      if index == nil then
        U.fail(
          'send_not_found',
          'la pista "' .. ST.name(from) .. '" no tiene un envio a "' .. ST.name(to) .. '"'
        )
      end
      reaper.SetTrackSendInfo_Value(from, 0, index, 'D_VOL', U.db_to_vol(db))
      return {
        from = ST.name(from),
        to = ST.name(to),
        level_db = U.round(db, 1),
      }
    end,
  }

  handlers['track.output'] = {
    undo = true,
    desc = 'Rutear una pista a un par de salidas fisicas',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      -- 1 = salidas 1/2, 2 = salidas 3/4, 3 = 5/6...
      local pair = U.num(args, 'pair', { default = 1, min = 1, max = 64 })
      local level = U.num(args, 'level_db', { default = 0, min = -150, max = 24 })
      local mono = U.bool(args, 'mono', { default = false })

      local count = reaper.GetTrackNumSends(tr, 1)
      for index = 0, count - 1 do
        local dest = reaper.GetTrackSendInfo_Value(tr, 1, index, 'I_DSTCHAN') & 1023
        if dest == (pair - 1) * 2 then
          U.fail(
            'output_exists',
            'la pista "' .. ST.name(tr) .. '" ya va a las salidas ' .. ((pair - 1) * 2 + 1) ..
              '/' .. ((pair - 1) * 2 + 2)
          )
        end
      end

      local send_index = reaper.CreateTrackSend(tr, nil)
      if send_index == nil or send_index < 0 then
        U.fail('reaper_error', 'REAPER no pudo crear la salida fisica')
      end

      local destchan = (pair - 1) * 2
      if mono then
        destchan = destchan + 1024 -- &1024 = mezclar a mono
      end
      reaper.SetTrackSendInfo_Value(tr, 1, send_index, 'I_DSTCHAN', destchan)
      reaper.SetTrackSendInfo_Value(tr, 1, send_index, 'D_VOL', U.db_to_vol(level))

      return {
        track = ST.name(tr),
        index = idx,
        pair = pair,
        channels = ((pair - 1) * 2 + 1) .. '/' .. ((pair - 1) * 2 + 2),
        level_db = U.round(level, 1),
        mono = mono,
        outputs_total = reaper.GetTrackNumSends(tr, 1),
      }
    end,
  }

  handlers['track.output_clear'] = {
    undo = true,
    desc = 'Quitar todas las salidas fisicas de una pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local removed = 0
      while reaper.GetTrackNumSends(tr, 1) > 0 do
        if not reaper.RemoveTrackSend(tr, 1, 0) then
          break
        end
        removed = removed + 1
      end
      return { track = ST.name(tr), index = idx, removed = removed }
    end,
  }

  return handlers
end)()
