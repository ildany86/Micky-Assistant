-- Miky · comandos de plugins / FX (fx.*)

MIKY = MIKY or {}

MIKY.cmd_fx = (function()
  local U = MIKY.util
  local ST = MIKY.state

  local handlers = {}

  -- ---------- búsqueda por descripción ("un compresor estilo SSL") ----------

  local STOPWORDS = {
    ['un'] = true, ['una'] = true, ['el'] = true, ['la'] = true, ['los'] = true,
    ['las'] = true, ['de'] = true, ['del'] = true, ['al'] = true, ['con'] = true,
    ['para'] = true, ['que'] = true, ['sea'] = true, ['tipo'] = true, ['estilo'] = true,
    ['como'] = true, ['parametrico'] = true, ['parametric'] = true, ['analogico'] = true,
    ['vintage'] = true, ['moderno'] = true, ['nuevo'] = true, ['favorito'] = true,
    ['inserta'] = true, ['carga'] = true, ['pone'] = true, ['pon'] = true,
    ['agrega'] = true, ['plugin'] = true, ['efecto'] = true,
  }

  -- Cada palabra clave se expande a prefijos de palabra que buscamos en el nombre
  -- real del plugin (así "compresor" encuentra "Compressor" y "comp").
  local ALIASES = {
    compresor = { 'comp' }, compresion = { 'comp' }, comp = { 'comp' },
    compresores = { 'comp' },
    ecualizador = { 'eq', 'equaliz', 'equilib', 'pro-q', 'proq' },
    equalizador = { 'eq', 'equaliz', 'equilib', 'pro-q', 'proq' },
    ecualizacion = { 'eq', 'equaliz' }, eq = { 'eq', 'equaliz', 'pro-q', 'proq' },
    reverb = { 'reverb', 'verb', 'convol', 'ir' }, reverberacion = { 'reverb', 'verb', 'convol' },
    delay = { 'delay', 'echo', 'eco' }, eco = { 'delay', 'echo', 'eco' },
    limitador = { 'limit' }, limiter = { 'limit' },
    puerta = { 'gate' }, gate = { 'gate' }, expansor = { 'expand', 'gate' },
    deeser = { 'de-ess', 'deess', 'desser' }, deesser = { 'de-ess', 'deess', 'desser' },
    saturador = { 'satur', 'tube', 'tape', 'drive', 'distor' },
    saturacion = { 'satur', 'tube', 'tape', 'drive' },
    distorsion = { 'distor', 'drive', 'satur' },
    preamplificador = { 'pre', 'preamp', 'amp' }, preamp = { 'pre', 'preamp' },
    amplificador = { 'amp', 'sim' }, simulador = { 'sim' },
    instrumento = { 'inst' }, sintetizador = { 'synth' }, piano = { 'piano' },
    bateria = { 'drum', 'kit' }, drums = { 'drum', 'kit' },
    coro = { 'chorus' }, chorus = { 'chorus' },
    flanger = { 'flanger' }, phaser = { 'phaser' },
    pitch = { 'pitch', 'tune' }, afinador = { 'tune', 'pitch' },
    filtro = { 'filter' }, filtros = { 'filter' },
    estereo = { 'stereo' }, midi = { 'midi' }, sintesis = { 'synth' },
  }

  local function tokenize(query)
    -- Devuelve "conceptos": cada uno es una lista de patrones alternativos.
    -- Así "equalizer" y "eq" cuentan una sola vez por plugin (si no, los plugins
    -- cuyo nombre contiene las dos variantes puntúan doble y desplazan al resto).
    local concepts = {}
    local seen = {}
    for word in U.norm(query):gmatch('[%w%-]+') do
      if not STOPWORDS[word] and #word >= 2 then
        local patterns = ALIASES[word] or { word }
        local key = patterns[1]
        if not seen[key] then
          seen[key] = true
          concepts[#concepts + 1] = patterns
        end
      end
    end
    return concepts
  end

  local function score_name(name, concepts)
    local normalized = U.norm(name)
    local score = 0
    for _, patterns in ipairs(concepts) do
      for _, pattern in ipairs(patterns) do
        -- Búsqueda por subcadena: "comp" encuentra "ReaComp" y "Compressor",
        -- "eq" encuentra "ReaEQ" y "EQP". El ruido se resuelve ofreciendo opciones.
        if normalized:find(pattern, 1, true) then
          score = score + 1
          break
        end
      end
    end
    return score
  end

  local function installed_fx()
    local list = {}
    local index = 0
    while index < 4000 do
      local ok, name = reaper.EnumInstalledFX(index)
      if not ok then
        break
      end
      if name and name ~= '' then
        list[#list + 1] = name
      end
      index = index + 1
    end
    return list
  end

  local function search_list(list, query, limit)
    local concepts = tokenize(query)
    if #concepts == 0 then
      return {}
    end
    local scored = {}
    for _, name in ipairs(list) do
      local score = score_name(name, concepts)
      if score > 0 then
        scored[#scored + 1] = { name = name, score = score }
      end
    end
    -- Con 1500 plugins, muchos empatan en puntaje. Desempate: primero los
    -- plugins "de verdad" (VST3/VST) antes que los JS de utilería, y después el
    -- nombre más corto, que suele ser el de fábrica (ReaEQ antes que "4x4 EQ").
    local function kind_rank(name)
      local lower = name:lower()
      if lower:find('^vst3') then
        return 0
      end
      if lower:find('^vst') or lower:find('^au:') or lower:find('^clap') or lower:find('^lv2') then
        return 1
      end
      if lower:find('^js') then
        return 3
      end
      return 2
    end

    table.sort(scored, function(a, b)
      if a.score ~= b.score then
        return a.score > b.score
      end
      local rank_a, rank_b = kind_rank(a.name), kind_rank(b.name)
      if rank_a ~= rank_b then
        return rank_a < rank_b
      end
      if #a.name ~= #b.name then
        return #a.name < #b.name
      end
      return a.name < b.name
    end)

    -- Solo se ofrecen opciones cuando hay empate: si uno puntúa más que el
    -- resto, se elige ese directamente.
    local out = {}
    local top = scored[1] and scored[1].score or 0
    for index = 1, #scored do
      if scored[index].score < top or #out >= (limit or 5) then
        break
      end
      out[#out + 1] = scored[index].name
    end
    return out
  end

  local function search_installed_fx(query, limit)
    return search_list(installed_fx(), query, limit)
  end

  -- ---------- favoritos de REAPER (reaper-fxfolders.ini) ----------

  -- REAPER guarda las carpetas del explorador de plugins en un .ini del recurso.
  -- La carpeta "Favoritos"/"Favorites" es la lista que el usuario curó a mano:
  -- es la mejor pista de qué plugin quiere cuando pide algo por descripción.
  local function read_fx_folders()
    local path = reaper.GetResourcePath() .. '/reaper-fxfolders.ini'
    local file = io.open(path, 'r')
    if not file then
      return {}
    end
    local names = {}
    local items = {}
    local current = nil
    for raw_line in file:lines() do
      local line = raw_line:gsub('\r', '')
      local folder_id = line:match('^%[Folder(%d+)%]$')
      if folder_id then
        current = tonumber(folder_id)
        items[current] = items[current] or {}
      elseif line:match('^%[Folders%]$') then
        current = nil
      elseif current then
        local item = line:match('^Item%d+=(.+)$')
        if item then
          items[current][#items[current] + 1] = item
        end
      else
        local id, name = line:match('^Name(%d+)=(.+)$')
        if id and name then
          names[tonumber(id)] = name
        end
      end
    end
    file:close()

    local out = {}
    for id, list in pairs(items) do
      out[#out + 1] = { id = id, name = names[id] or ('Carpeta ' .. id), items = list }
    end
    table.sort(out, function(a, b)
      return a.id < b.id
    end)
    return out
  end

  local function is_favorites_name(name)
    local key = U.norm(name)
    return key:find('favorit', 1, true) ~= nil or key:find('estrell', 1, true) ~= nil
  end

  -- Convierte las rutas del .ini ("...\Eamut Drums Compressor.vst3") al nombre
  -- con el que REAPER lista el plugin ("VST3: Eamut Drums Compressor (Eamut)").
  -- Devuelve (encontrados, faltantes): los favoritos marcados que ya no están
  -- instalados se informan aparte en vez de perderse.
  local function favorites_list()
    local folders = read_fx_folders()
    local chosen = {}
    for _, folder in ipairs(folders) do
      if is_favorites_name(folder.name) then
        chosen[#chosen + 1] = folder
      end
    end
    if #chosen == 0 then
      return {}, {}
    end
    local installed = {}
    for _, name in ipairs(installed_fx()) do
      installed[#installed + 1] = { name = name, key = U.norm(name) }
    end
    local out = {}
    local missing = {}
    local seen = {}
    local seen_missing = {}
    for _, folder in ipairs(chosen) do
      for _, item in ipairs(folder.items) do
        local base = item:match('([^/\\]+)$') or item
        base = base:gsub('%.[%w]+$', '')
        local key = U.norm(base)
        if #key >= 4 then
          local found = nil
          for _, entry in ipairs(installed) do
            if entry.key:find(key, 1, true) then
              found = entry.name
              break
            end
          end
          if found and not seen[found] then
            seen[found] = true
            out[#out + 1] = found
          elseif not found and not seen_missing[key] then
            seen_missing[key] = true
            missing[#missing + 1] = base
          end
        end
      end
    end
    return out, missing
  end

  -- ---------- comandos ----------

  handlers['fx.installed'] = {
    undo = false,
    desc = 'Listar los plugins instalados',
    fn = function(args)
      local limit = U.num(args, 'limit', { default = 0, min = 0, max = 4000 }) or 0
      local all = installed_fx()
      local names = {}
      local vendors = {}
      local seen = {}
      for _, name in ipairs(all) do
        if limit == 0 or #names < limit then
          names[#names + 1] = name
        end
        local vendor = name:match('%((.-)%)%s*$')
        if vendor and not seen[vendor] then
          seen[vendor] = true
          vendors[#vendors + 1] = vendor
        end
      end
      table.sort(vendors)
      local favorites, missing = favorites_list()
      local folders = {}
      for _, folder in ipairs(read_fx_folders()) do
        folders[#folders + 1] = folder.name
      end
      return {
        count = #all,
        vendors = vendors,
        names = names,
        truncated = limit > 0 and #all > limit or false,
        favorites = favorites,
        favorite_count = #favorites,
        missing_favorites = missing,
        folders = folders,
      }
    end,
  }

  handlers['fx.favorites'] = {
    undo = false,
    desc = 'Listar los plugins favoritos de REAPER',
    fn = function()
      local favorites, missing = favorites_list()
      local summary
      if #favorites > 0 then
        summary = table.concat(favorites, ' / ')
      elseif #missing > 0 then
        summary = 'los marcados no están instalados: ' .. table.concat(missing, ' / ')
      else
        summary = 'no hay favoritos marcados'
      end
      return {
        count = #favorites,
        favorites = favorites,
        missing = missing,
        summary = summary,
      }
    end,
  }

  handlers['fx.search'] = {
    undo = false,
    desc = 'Buscar plugins instalados por descripcion',
    fn = function(args)
      local query = U.str(args, 'query', { required = true })
      local limit = U.num(args, 'limit', { default = 8, min = 1, max = 50 }) or 8
      local all = installed_fx()
      local found = search_installed_fx(query, limit)
      if #found == 0 then
        U.fail(
          'fx_not_found',
          'no hay ningun plugin instalado que coincida con "' .. query .. '" (hay ' .. #all .. ' en total)'
        )
      end
      return {
        query = query,
        count = #found,
        candidates = found,
        total_installed = #all,
        summary = table.concat(found, ' / '),
      }
    end,
  }

  local function param_names_hint(tr, fx, limit)
    limit = limit or 10
    local names = {}
    local count = reaper.TrackFX_GetNumParams(tr, fx)
    for i = 0, math.min(count, limit) - 1 do
      local _, name = reaper.TrackFX_GetParamName(tr, fx, i, '')
      if name and name ~= '' then
        names[#names + 1] = name
      end
    end
    if count > limit then
      names[#names + 1] = '...'
    end
    return table.concat(names, ', ')
  end

  handlers['fx.add'] = {
    undo = true,
    desc = 'Cargar plugin',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local name = U.str(args, 'name', { required = true })
      local position = U.num(args, 'position')

      local instantiate = 1
      if position then
        -- <= -1000 codifica la posicion de insercion (-1000 = primero de la cadena)
        instantiate = -1000 - (math.floor(position) - 1)
      end

      local fx = reaper.TrackFX_AddByName(tr, name, false, instantiate)
      local resolved = name
      local from_favorites = false
      if fx < 0 then
        -- 1) Favoritos del usuario primero: si hay uno solo que coincida, se
        -- carga sin preguntar; si hay varios, esas son las opciones.
        local favorites = favorites_list()
        local favorite = search_list(favorites, name, 5)
        if #favorite == 1 then
          resolved = favorite[1]
          from_favorites = true
          fx = reaper.TrackFX_AddByName(tr, resolved, false, instantiate)
        elseif #favorite > 1 then
          error({
            code = 'fx_candidates',
            message = 'tus favoritos para "' .. name .. '": ' .. table.concat(favorite, ' / '),
            candidates = favorite,
            from_favorites = true,
          }, 0)
        end
      end

      if fx < 0 then
        -- 2) Catálogo completo: se busca por descripción ("compresor estilo
        -- SSL", "eq tipo pultec").
        local candidates = search_installed_fx(name, 5)
        if #candidates == 1 then
          resolved = candidates[1]
          fx = reaper.TrackFX_AddByName(tr, resolved, false, instantiate)
        elseif #candidates > 1 then
          error({
            code = 'fx_candidates',
            message = 'encontre varios plugins para "' .. name .. '": ' .. table.concat(candidates, ' / '),
            candidates = candidates,
          }, 0)
        end
      end

      if fx < 0 then
        U.fail(
          'fx_not_found',
          'no encontre el plugin "' .. name .. '" en la pista "' .. ST.name(tr) .. '". ' ..
            'Proba con el nombre tal como aparece en el explorador de plugins de REAPER.'
        )
      end

      return {
        index = fx + 1,
        name = ST.fx_name(tr, fx),
        track_name = ST.name(tr),
        requested = name,
        resolved = resolved,
        from_favorites = from_favorites,
        track = idx,
        fx_count = reaper.TrackFX_GetCount(tr),
      }
    end,
  }

  handlers['fx.remove'] = {
    undo = true,
    desc = 'Quitar plugin',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local fx, fx_name = ST.resolve_fx(tr, U.raw(args, 'fx'))
      local removed = reaper.TrackFX_Delete(tr, fx)
      if not removed then
        U.fail('reaper_error', 'REAPER no pudo quitar el plugin "' .. tostring(fx_name) .. '"')
      end
      return { track = idx, removed = fx_name, fx_count = reaper.TrackFX_GetCount(tr) }
    end,
  }

  handlers['fx.bypass'] = {
    undo = true,
    desc = 'Activar o desactivar plugin',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local fx, fx_name = ST.resolve_fx(tr, U.raw(args, 'fx'))
      local enabled = U.bool(args, 'enabled')
      if enabled == nil then
        enabled = not reaper.TrackFX_GetEnabled(tr, fx)
      end
      reaper.TrackFX_SetEnabled(tr, fx, enabled)
      return { track = idx, fx = fx_name, enabled = enabled }
    end,
  }

  handlers['fx.set_param'] = {
    undo = true,
    desc = 'Cambiar parametro de plugin',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local fx, fx_name = ST.resolve_fx(tr, U.raw(args, 'fx'))
      local selector = U.raw(args, 'param')
      if selector == nil then
        U.fail('missing_arg', 'falta el argumento "param"')
      end

      local count = reaper.TrackFX_GetNumParams(tr, fx)
      local param_index

      if type(selector) == 'number' then
        local i = math.floor(selector)
        if i >= 1 and i <= count then
          param_index = i - 1
        elseif i >= 0 and i < count and selector == i then
          -- compatibilidad: 0-based explicito
          param_index = i
        end
      elseif type(selector) == 'string' then
        local query = U.norm(selector)
        local partial = {}
        for i = 0, count - 1 do
          local _, pname = reaper.TrackFX_GetParamName(tr, fx, i, '')
          local norm = U.norm(pname)
          if norm == query then
            param_index = i
            break
          end
          if norm ~= '' and norm:find(query, 1, true) then
            partial[#partial + 1] = i
          end
        end
        if param_index == nil and #partial == 1 then
          param_index = partial[1]
        end
        if param_index == nil and #partial > 1 then
          local names = {}
          for _, pi in ipairs(partial) do
            local _, pname = reaper.TrackFX_GetParamName(tr, fx, pi, '')
            names[#names + 1] = tostring(pi + 1) .. '=' .. pname
          end
          U.fail('param_ambiguous', 'varios parametros coinciden: ' .. table.concat(names, ', '))
        end
      end

      if param_index == nil then
        U.fail(
          'param_not_found',
          'no encontre el parametro "' .. tostring(selector) .. '" en ' .. tostring(fx_name) ..
            '. Parametros disponibles: ' .. param_names_hint(tr, fx)
        )
      end

      local normalized = U.bool(args, 'normalized', { default = false })
      local value = U.num(args, 'value', { required = true })

      if normalized then
        reaper.TrackFX_SetParamNormalized(tr, fx, param_index, U.clamp(value, 0, 1))
      else
        reaper.TrackFX_SetParam(tr, fx, param_index, value)
      end

      local _, pname = reaper.TrackFX_GetParamName(tr, fx, param_index, '')
      local formatted = ''
      if reaper.APIExists('TrackFX_GetFormattedParamValue') then
        local ok, text = reaper.TrackFX_GetFormattedParamValue(tr, fx, param_index, '')
        if ok then
          formatted = text or ''
        end
      end

      return {
        track = idx,
        fx = fx_name,
        param = pname,
        param_index = param_index + 1,
        value = value,
        normalized = normalized,
        formatted = formatted,
      }
    end,
  }

  handlers['fx.list'] = {
    undo = false,
    desc = 'Listar plugins de una pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local count = reaper.TrackFX_GetCount(tr)
      local out = {}
      for i = 0, count - 1 do
        local entry = {
          index = i + 1,
          name = ST.fx_name(tr, i),
          enabled = reaper.TrackFX_GetEnabled(tr, i),
          param_count = reaper.TrackFX_GetNumParams(tr, i),
        }
        out[#out + 1] = entry
      end
      return { track = idx, name = ST.name(tr), fx = out }
    end,
  }

  handlers['fx.params'] = {
    undo = false,
    desc = 'Leer los parametros reales de los plugins de una pista',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local limit = U.num(args, 'limit', { default = 12, min = 1, max = 48 }) or 12
      local wanted = U.raw(args, 'fx')
      local count = reaper.TrackFX_GetCount(tr)
      local out = {}
      local parts = {}
      for i = 0, count - 1 do
        local name = ST.fx_name(tr, i)
        local include = true
        if wanted and wanted ~= '' then
          include = U.norm(name):find(U.norm(tostring(wanted)), 1, true) ~= nil
        end
        if include then
          local preset = ''
          if reaper.TrackFX_GetPreset then
            local ok_preset, preset_name = reaper.TrackFX_GetPreset(tr, i, '')
            if ok_preset then
              preset = preset_name or ''
            end
          end
          local params = {}
          local param_count = reaper.TrackFX_GetNumParams(tr, i)
          for p = 0, param_count - 1 do
            if #params >= limit then
              break
            end
            local _, param_name = reaper.TrackFX_GetParamName(tr, i, p, '')
            if param_name and param_name ~= '' then
              -- REAPER devuelve un string; algunos mocks, (ok, string).
              local first, second = reaper.TrackFX_GetFormattedParamValue(tr, i, p, '')
              local formatted
              if type(first) == 'string' then
                formatted = first
              elseif type(second) == 'string' then
                formatted = second
              end
              if not formatted or formatted == '' then
                formatted = tostring(reaper.TrackFX_GetParamNormalized(tr, i, p))
              end
              params[#params + 1] = { name = param_name, value = formatted }
            end
          end
          out[#out + 1] = {
            index = i + 1,
            name = name,
            preset = preset,
            param_count = param_count,
            params = params,
          }
          local readable = {}
          for _, param in ipairs(params) do
            readable[#readable + 1] = param.name .. ' ' .. param.value
          end
          parts[#parts + 1] = name .. ': ' .. table.concat(readable, ', ')
        end
      end
      if #out == 0 then
        U.fail('fx_not_found', 'la pista "' .. ST.name(tr) .. '" no tiene plugins' ..
          (wanted and wanted ~= '' and (' que coincidan con "' .. tostring(wanted) .. '"') or ''))
      end
      return {
        track = idx,
        track_name = ST.name(tr),
        plugins = out,
        count = #out,
        summary = table.concat(parts, ' | '),
      }
    end,
  }

  handlers['fx.open'] = {
    undo = false,
    desc = 'Abrir interfaz de plugin',
    fn = function(args)
      local tr, idx = ST.resolve(U.raw(args, 'track'))
      local fx, fx_name = ST.resolve_fx(tr, U.raw(args, 'fx'))
      reaper.TrackFX_SetOpen(tr, fx, true)
      return { track = idx, fx = fx_name, open = true }
    end,
  }

  return handlers
end)()
