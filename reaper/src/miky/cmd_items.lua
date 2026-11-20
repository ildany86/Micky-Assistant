-- Miky · edición de items (item.*)

MIKY = MIKY or {}

MIKY.cmd_items = (function()
  local U = MIKY.util
  local ST = MIKY.state

  local handlers = {}

  local function selected_items()
    local items = {}
    local count = reaper.CountSelectedMediaItems(0)
    for index = 0, count - 1 do
      local item = reaper.GetSelectedMediaItem(0, index)
      if item then
        items[#items + 1] = item
      end
    end
    return items
  end

  local function items_for(args)
    -- 1) los items seleccionados; 2) si se indicó pista, todos los de esa pista.
    local items = selected_items()
    if #items > 0 then
      return items, 'seleccion'
    end
    local selector = U.raw(args, 'track')
    if selector == nil then
      return items, 'seleccion'
    end
    local track = ST.resolve(selector)
    local count = reaper.CountTrackMediaItems(track)
    for index = 0, count - 1 do
      local item = reaper.GetTrackMediaItem(track, index)
      if item then
        items[#items + 1] = item
      end
    end
    return items, ST.name(track)
  end

  local function item_bounds(item)
    local position = reaper.GetMediaItemInfo_Value(item, 'D_POSITION')
    local length = reaper.GetMediaItemInfo_Value(item, 'D_LENGTH')
    return position, position + length
  end

  local function resolve_time(args, marker_key, time_key)
    local marker_name = U.str(args, marker_key)
    if marker_name then
      local marker = ST.find_marker(marker_name)
      if not marker then
        U.fail('marker_not_found', 'no encontre un marcador o region llamado "' .. marker_name .. '"')
      end
      return marker.pos, marker.name
    end
    return U.num(args, time_key)
  end

  handlers['item.keep_between'] = {
    undo = true,
    desc = 'Recortar item entre marcadores',
    fn = function(args)
      local start_pos, start_name = resolve_time(args, 'start_marker', 'start')
      local end_pos, end_name = resolve_time(args, 'end_marker', 'end')
      if not start_pos then
        U.fail('missing_arg', 'indica "start_marker" o "start" (en segundos)')
      end
      if not end_pos then
        U.fail('missing_arg', 'indica "end_marker" o "end" (en segundos)')
      end
      if end_pos <= start_pos then
        U.fail('invalid_arg', 'el final tiene que ser mayor que el comienzo')
      end

      local items, origin = items_for(args)
      if #items == 0 then
        U.fail(
          'item_required',
          'no hay ningun item seleccionado. Selecciona el item en REAPER (o indica la pista) y volve a pedirlo'
        )
      end

      local kept, trimmed = 0, 0
      for _, item in ipairs(items) do
        local track = reaper.GetMediaItem_Track(item)
        local position, finish = item_bounds(item)
        if finish > start_pos and position < end_pos then
          -- Primero la cola, después la cabeza: así los cortes no se pisan.
          if finish > end_pos then
            local tail = reaper.SplitMediaItem(item, end_pos)
            if tail then
              reaper.DeleteTrackMediaItem(track, tail)
              trimmed = trimmed + 1
            end
          end
          local pos_now = reaper.GetMediaItemInfo_Value(item, 'D_POSITION')
          if pos_now < start_pos then
            local right = reaper.SplitMediaItem(item, start_pos)
            if right then
              reaper.DeleteTrackMediaItem(track, item)
              item = right
              trimmed = trimmed + 1
            end
          end
          reaper.SetMediaItemSelected(item, true)
          kept = kept + 1
        end
      end

      if kept == 0 then
        U.fail(
          'item_out_of_range',
          'el item seleccionado no se superpone con ese rango (' ..
            tostring(U.round(start_pos, 2)) .. ' s a ' .. tostring(U.round(end_pos, 2)) .. ' s)'
        )
      end

      return {
        kept = kept,
        trimmed = trimmed,
        origin = origin,
        start = U.round(start_pos, 3),
        finish = U.round(end_pos, 3),
        from_marker = start_name or '',
        to_marker = end_name or '',
      }
    end,
  }

  handlers['item.split_at_cursor'] = {
    undo = true,
    desc = 'Cortar item en el cursor',
    fn = function(args)
      local position = U.num(args, 'position') or reaper.GetCursorPosition()
      local items = items_for(args)
      if #items == 0 then
        U.fail('item_required', 'no hay ningun item seleccionado para cortar')
      end

      local splits = 0
      for _, item in ipairs(items) do
        local start, finish = item_bounds(item)
        if position > start and position < finish then
          local right = reaper.SplitMediaItem(item, position)
          if right then
            splits = splits + 1
          end
        end
      end

      if splits == 0 then
        U.fail('item_out_of_range', 'el cursor no cae dentro de ningun item seleccionado')
      end
      return { splits = splits, position = U.round(position, 3) }
    end,
  }

  handlers['item.delete_selected'] = {
    undo = true,
    desc = 'Eliminar items seleccionados',
    fn = function()
      local items = selected_items()
      if #items == 0 then
        U.fail('item_required', 'no hay ningun item seleccionado')
      end
      local deleted = 0
      for _, item in ipairs(items) do
        local track = reaper.GetMediaItem_Track(item)
        if track and reaper.DeleteTrackMediaItem(track, item) then
          deleted = deleted + 1
        end
      end
      return { deleted = deleted }
    end,
  }

  return handlers
end)()
