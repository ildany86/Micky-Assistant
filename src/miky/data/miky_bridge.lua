-- Miky bridge v0.1.0b1
-- Generado por tools/build_lua.py · no editar a mano.
-- Puente de control entre la app Miky (Python) y REAPER (ReaScript).
--
-- Qué hace: mira la carpeta de pedidos, ejecuta comandos de un catálogo
-- cerrado y escribe las respuestas. No abre ventanas, no toca el mouse y
-- no ejecuta código que venga de afuera.
--
-- Carpeta de trabajo: %APPDATA%\Miky\ipc
--   requests/   pedidos de la app
--   responses/  respuestas del puente
--   status.json latido (para saber si el puente está vivo)

-- ===== version.lua =================================================
-- Miky · version y constantes del protocolo
-- (build_lua.py reescribe VERSION desde src/miky/__init__.py: una sola fuente de verdad)

MIKY = MIKY or {}

MIKY.VERSION = '0.1.0b1'
MIKY.PROTOCOL = 1

-- ===== json.lua ====================================================
-- Miky · codec JSON mínimo (sin dependencias externas)
-- Codifica/decodifica el subconjunto de JSON que usa el protocolo del puente.
-- Se usa desde ReaScript (Lua 5.4) y desde los tests con el interprete embebido.

MIKY = MIKY or {}

MIKY.json = (function()
  local json = {}

  local escape_map = {
    ['"'] = '\\"',
    ['\\'] = '\\\\',
    ['\b'] = '\\b',
    ['\f'] = '\\f',
    ['\n'] = '\\n',
    ['\r'] = '\\r',
    ['\t'] = '\\t',
  }

  local function escape_char(c)
    return escape_map[c] or string.format('\\u%04x', string.byte(c))
  end

  local function is_array(t)
    local n = 0
    for k in pairs(t) do
      if type(k) ~= 'number' then
        return false
      end
      n = n + 1
    end
    return n == #t
  end

  local encode

  local function encode_table(t)
    if is_array(t) then
      local parts = {}
      for i = 1, #t do
        parts[i] = encode(t[i])
      end
      return '[' .. table.concat(parts, ',') .. ']'
    end
    local parts = {}
    for k, v in pairs(t) do
      parts[#parts + 1] = encode(tostring(k)) .. ':' .. encode(v)
    end
    return '{' .. table.concat(parts, ',') .. '}'
  end

  encode = function(v)
    local tv = type(v)
    if v == nil then
      return 'null'
    elseif tv == 'boolean' then
      return tostring(v)
    elseif tv == 'number' then
      if v ~= v or v == math.huge or v == -math.huge then
        return 'null'
      end
      if math.type(v) == 'integer' then
        return string.format('%d', v)
      end
      if v == math.floor(v) and math.abs(v) < 1e15 then
        return string.format('%.0f', v)
      end
      return string.format('%.14g', v)
    elseif tv == 'string' then
      local escaped = v:gsub('[%c\\"]', escape_char)
      return '"' .. escaped .. '"'
    elseif tv == 'table' then
      return encode_table(v)
    end
    return 'null'
  end

  function json.encode(v)
    return encode(v)
  end

  local function utf8_char(cp)
    if cp < 0x80 then
      return string.char(cp)
    elseif cp < 0x800 then
      return string.char(0xC0 + (cp >> 6), 0x80 + (cp & 0x3F))
    elseif cp < 0x10000 then
      return string.char(0xE0 + (cp >> 12), 0x80 + ((cp >> 6) & 0x3F), 0x80 + (cp & 0x3F))
    end
    return string.char(
      0xF0 + (cp >> 18),
      0x80 + ((cp >> 12) & 0x3F),
      0x80 + ((cp >> 6) & 0x3F),
      0x80 + (cp & 0x3F)
    )
  end

  function json.decode(str)
    if type(str) ~= 'string' then
      error('json.decode: se esperaba un string', 2)
    end

    local i = 1
    local len = #str

    local function fail(msg)
      error(string.format('JSON invalido: %s (posicion %d)', msg, i), 0)
    end

    local function skip_ws()
      local _, e = str:find('^[ \t\r\n]+', i)
      if e then
        i = e + 1
      end
    end

    local parse_value

    local function parse_string()
      i = i + 1
      local out = {}
      while true do
        local c = str:sub(i, i)
        if c == '' then
          fail('texto sin cerrar')
        end
        if c == '"' then
          i = i + 1
          return table.concat(out)
        end
        if c == '\\' then
          local n = str:sub(i + 1, i + 1)
          if n == 'u' then
            local hex = str:sub(i + 2, i + 5)
            if not hex:match('^%x%x%x%x$') then
              fail('escape \\u invalido')
            end
            local cp = tonumber(hex, 16)
            i = i + 6
            if cp >= 0xD800 and cp <= 0xDBFF then
              local low_hex = str:sub(i + 2, i + 5)
              if str:sub(i, i + 1) == '\\u' and low_hex:match('^%x%x%x%x$') then
                local lo = tonumber(low_hex, 16)
                if lo >= 0xDC00 and lo <= 0xDFFF then
                  cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                  i = i + 6
                end
              end
            end
            out[#out + 1] = utf8_char(cp)
          else
            local simple = {
              ['"'] = '"',
              ['\\'] = '\\',
              ['/'] = '/',
              b = '\b',
              f = '\f',
              n = '\n',
              r = '\r',
              t = '\t',
            }
            local rep = simple[n]
            if not rep then
              fail('escape invalido')
            end
            out[#out + 1] = rep
            i = i + 2
          end
        else
          out[#out + 1] = c
          i = i + 1
        end
      end
    end

    local function parse_number()
      local s, e = str:find('^-?%d+%.?%d*[eE][-+]?%d+', i)
      if not s then
        s, e = str:find('^-?%d+%.?%d*', i)
      end
      if not s then
        fail('numero invalido')
      end
      local num = tonumber(str:sub(s, e))
      if not num then
        fail('numero invalido')
      end
      i = e + 1
      return num
    end

    local function parse_array()
      local arr = {}
      i = i + 1
      skip_ws()
      if str:sub(i, i) == ']' then
        i = i + 1
        return arr
      end
      while true do
        arr[#arr + 1] = parse_value()
        skip_ws()
        local c = str:sub(i, i)
        if c == ',' then
          i = i + 1
        elseif c == ']' then
          i = i + 1
          return arr
        else
          fail("se esperaba ',' o ']'")
        end
      end
    end

    local function parse_object()
      local obj = {}
      i = i + 1
      skip_ws()
      if str:sub(i, i) == '}' then
        i = i + 1
        return obj
      end
      while true do
        skip_ws()
        if str:sub(i, i) ~= '"' then
          fail('se esperaba una clave')
        end
        local key = parse_string()
        skip_ws()
        if str:sub(i, i) ~= ':' then
          fail("se esperaba ':'")
        end
        i = i + 1
        obj[key] = parse_value()
        skip_ws()
        local c = str:sub(i, i)
        if c == ',' then
          i = i + 1
        elseif c == '}' then
          i = i + 1
          return obj
        else
          fail("se esperaba ',' o '}'")
        end
      end
    end

    parse_value = function()
      skip_ws()
      local c = str:sub(i, i)
      if c == '' then
        fail('fin inesperado')
      elseif c == '{' then
        return parse_object()
      elseif c == '[' then
        return parse_array()
      elseif c == '"' then
        return parse_string()
      elseif c == 't' then
        if str:sub(i, i + 3) == 'true' then
          i = i + 4
          return true
        end
        fail('literal invalido')
      elseif c == 'f' then
        if str:sub(i, i + 4) == 'false' then
          i = i + 5
          return false
        end
        fail('literal invalido')
      elseif c == 'n' then
        if str:sub(i, i + 3) == 'null' then
          i = i + 4
          return nil
        end
        fail('literal invalido')
      elseif c == '-' or c:match('%d') then
        return parse_number()
      end
      fail('caracter inesperado: ' .. c)
    end

    local value = parse_value()
    skip_ws()
    if i <= len then
      fail('contenido sobrante')
    end
    return value
  end

  return json
end)()

-- ===== util.lua ====================================================
-- Miky · utilidades compartidas (argumentos, colores, textos, conversiones)

MIKY = MIKY or {}

MIKY.util = (function()
  local U = {}

  -- Errores estructurados: el puente los serializa como {code, message}
  function U.fail(code, message)
    error({ code = code, message = message }, 0)
  end

  function U.trim(s)
    s = tostring(s or '')
    s = s:gsub('^%s+', '')
    s = s:gsub('%s+$', '')
    return s
  end

  function U.dirname(path)
    if not path or path == '' then
      return ''
    end
    local dir = path:match('^(.*)[/\\][^/\\]*$')
    return dir or ''
  end

  function U.clamp(v, lo, hi)    if v < lo then
      return lo
    end
    if v > hi then
      return hi
    end
    return v
  end

  function U.round(v, decimals)
    local mult = 10 ^ (decimals or 0)
    return math.floor(v * mult + 0.5) / mult
  end

  function U.is_number(v)
    return type(v) == 'number' and v == v and v ~= math.huge and v ~= -math.huge
  end

  -- Tabla de acentos UTF-8 -> ASCII (escrita con bytes para no depender de la
  -- codificacion con la que se guarde este archivo).
  local accent_map = {
    ['\195\160'] = 'a', ['\195\161'] = 'a', ['\195\162'] = 'a', ['\195\164'] = 'a',
    ['\195\128'] = 'a', ['\195\129'] = 'a', ['\195\130'] = 'a', ['\195\132'] = 'a',
    ['\195\168'] = 'e', ['\195\169'] = 'e', ['\195\170'] = 'e', ['\195\171'] = 'e',
    ['\195\136'] = 'e', ['\195\137'] = 'e', ['\195\138'] = 'e', ['\195\139'] = 'e',
    ['\195\172'] = 'i', ['\195\173'] = 'i', ['\195\174'] = 'i', ['\195\175'] = 'i',
    ['\195\140'] = 'i', ['\195\141'] = 'i', ['\195\142'] = 'i', ['\195\143'] = 'i',
    ['\195\178'] = 'o', ['\195\179'] = 'o', ['\195\180'] = 'o', ['\195\182'] = 'o',
    ['\195\146'] = 'o', ['\195\147'] = 'o', ['\195\148'] = 'o', ['\195\150'] = 'o',
    ['\195\185'] = 'u', ['\195\186'] = 'u', ['\195\187'] = 'u', ['\195\188'] = 'u',
    ['\195\153'] = 'u', ['\195\154'] = 'u', ['\195\155'] = 'u', ['\195\156'] = 'u',
    ['\195\177'] = 'n', ['\195\145'] = 'n',
    ['\195\167'] = 'c', ['\195\135'] = 'c',
  }

  -- Normaliza para comparar nombres: minusculas, sin acentos, espacios simples.
  function U.norm(s)
    s = tostring(s or '')
    for k, v in pairs(accent_map) do
      s = s:gsub(k, v)
    end
    s = s:lower()
    s = s:gsub('%s+', ' ')
    return U.trim(s)
  end

  function U.fuzzy_eq(a, b)
    return U.norm(a) == U.norm(b)
  end

  -- Distancia de edición entre dos cadenas cortas (para tolerar typos).
  function U.distance(a, b)
    a = tostring(a or '')
    b = tostring(b or '')
    local la, lb = #a, #b
    if la == 0 then
      return lb
    end
    if lb == 0 then
      return la
    end
    local prev = {}
    for j = 0, lb do
      prev[j] = j
    end
    for i = 1, la do
      local cur = { [0] = i }
      local char_a = a:sub(i, i)
      for j = 1, lb do
        local cost = (char_a == b:sub(j, j)) and 0 or 1
        local best = prev[j] + 1
        if cur[j - 1] + 1 < best then
          best = cur[j - 1] + 1
        end
        if prev[j - 1] + cost < best then
          best = prev[j - 1] + cost
        end
        cur[j] = best
      end
      prev = cur
    end
    return prev[lb]
  end

  function U.db_to_vol(db)
    if db == nil then
      return 1
    end
    if db <= -150 then
      return 0
    end
    return 10 ^ (db / 20)
  end

  function U.vol_to_db(vol)
    if vol == nil or vol <= 0 then
      return -150
    end
    return 20 * math.log(vol, 10)
  end

  function U.pan_to_norm(pct)
    return U.clamp(pct / 100, -1, 1)
  end

  local named_colors = {
    rojo = { 235, 60, 60 }, red = { 235, 60, 60 },
    naranja = { 240, 140, 40 }, orange = { 240, 140, 40 },
    amarillo = { 240, 205, 45 }, yellow = { 240, 205, 45 },
    verde = { 75, 190, 95 }, green = { 75, 190, 95 },
    celeste = { 70, 175, 225 }, cyan = { 70, 175, 225 },
    azul = { 70, 120, 235 }, blue = { 70, 120, 235 },
    violeta = { 160, 95, 220 }, purple = { 160, 95, 220 },
    rosa = { 230, 95, 160 }, pink = { 230, 95, 160 },
    blanco = { 235, 235, 235 }, white = { 235, 235, 235 },
    gris = { 140, 140, 140 }, gray = { 140, 140, 140 }, grey = { 140, 140, 140 },
    negro = { 30, 30, 30 }, black = { 30, 30, 30 },
  }

  -- Acepta "#RRGGBB", "r,g,b", {r=,g=,b=} o un nombre en espanol/ingles.
  function U.color(arg)
    local r, g, b
    if type(arg) == 'table' then
      r, g, b = arg[1] or arg.r, arg[2] or arg.g, arg[3] or arg.b
    elseif type(arg) == 'string' then
      local hex = arg:match('^#?(%x%x%x%x%x%x)$')
      if hex then
        r = tonumber(hex:sub(1, 2), 16)
        g = tonumber(hex:sub(3, 4), 16)
        b = tonumber(hex:sub(5, 6), 16)
      else
        local cr, cg, cb = arg:match('^(%d+)%s*,%s*(%d+)%s*,%s*(%d+)$')
        if cr then
          r, g, b = tonumber(cr), tonumber(cg), tonumber(cb)
        else
          local c = named_colors[U.norm(arg)]
          if not c then
            U.fail('invalid_arg', 'color desconocido: ' .. tostring(arg))
          end
          r, g, b = c[1], c[2], c[3]
        end
      end
    end
    if not (U.is_number(r) and U.is_number(g) and U.is_number(b)) then
      U.fail('invalid_arg', 'color invalido: se esperaba nombre, "#RRGGBB" o {r,g,b}')
    end
    r = math.floor(U.clamp(r, 0, 255))
    g = math.floor(U.clamp(g, 0, 255))
    b = math.floor(U.clamp(b, 0, 255))
    return reaper.ColorToNative(r, g, b), r, g, b
  end

  -- ---------- Lectura de argumentos ----------

  function U.args_table(args)
    if args == nil then
      return {}
    end
    if type(args) ~= 'table' then
      U.fail('invalid_args', 'los argumentos deben ser un objeto JSON')
    end
    return args
  end

  function U.raw(args, key)
    return U.args_table(args)[key]
  end

  function U.num(args, key, opts)
    opts = opts or {}
    local v = U.args_table(args)[key]
    if v == nil then
      if opts.required then
        U.fail('missing_arg', 'falta el argumento "' .. key .. '"')
      end
      return opts.default
    end
    if type(v) ~= 'number' then
      local n = tonumber(v)
      if not n then
        U.fail('invalid_arg', 'el argumento "' .. key .. '" debe ser numerico')
      end
      v = n
    end
    if opts.min ~= nil and v < opts.min then
      v = opts.min
    end
    if opts.max ~= nil and v > opts.max then
      v = opts.max
    end
    return v
  end

  function U.str(args, key, opts)
    opts = opts or {}
    local v = U.args_table(args)[key]
    if v == nil then
      if opts.required then
        U.fail('missing_arg', 'falta el argumento "' .. key .. '"')
      end
      return opts.default
    end
    if type(v) == 'number' then
      v = tostring(v)
    end
    if type(v) ~= 'string' then
      U.fail('invalid_arg', 'el argumento "' .. key .. '" debe ser texto')
    end
    if opts.maxlen and #v > opts.maxlen then
      v = v:sub(1, opts.maxlen)
    end
    if not opts.allow_empty and U.trim(v) == '' then
      if opts.required then
        U.fail('invalid_arg', 'el argumento "' .. key .. '" no puede estar vacio')
      end
      return opts.default
    end
    return v
  end

  function U.bool(args, key, opts)
    opts = opts or {}
    local v = U.args_table(args)[key]
    if v == nil then
      if opts.required then
        U.fail('missing_arg', 'falta el argumento "' .. key .. '"')
      end
      return opts.default
    end
    if type(v) == 'boolean' then
      return v
    end
    if type(v) == 'number' then
      return v ~= 0
    end
    if type(v) == 'string' then
      local n = U.norm(v)
      if n == 'true' or n == 'si' or n == 'sí' or n == '1' or n == 'on' then
        return true
      end
      if n == 'false' or n == 'no' or n == '0' or n == 'off' then
        return false
      end
    end
    U.fail('invalid_arg', 'el argumento "' .. key .. '" debe ser verdadero/falso')
  end

  function U.enum(args, key, values, opts)
    opts = opts or {}
    local v = U.str(args, key, { required = opts.required, default = opts.default })
    if v == nil then
      return nil
    end
    local n = U.norm(v)
    for _, candidate in ipairs(values) do
      if U.norm(candidate) == n then
        return candidate
      end
    end
    U.fail(
      'invalid_arg',
      'valor invalido para "' .. key .. '": ' .. tostring(v) .. ' (opciones: ' .. table.concat(values, ', ') .. ')'
    )
  end

  return U
end)()

-- ===== state.lua ===================================================
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

-- ===== cmd_tracks.lua ==============================================
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

-- ===== cmd_fx.lua ==================================================
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

-- ===== cmd_transport.lua ===========================================
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

  -- Proyectos recientes: REAPER los guarda en la seccion [Recent] de reaper.ini.
  local function recent_projects()
    local ini = reaper.GetResourcePath() .. '/reaper.ini'
    local file = io.open(ini, 'r')
    if not file then
      return {}
    end
    local inside = false
    local out = {}
    for raw in file:lines() do
      local line = raw:gsub('\r', '')
      if line:match('^%[Recent%]$') then
        inside = true
      elseif line:match('^%[') then
        inside = false
      elseif inside then
        local value = line:match('^recent%d+=(.+)$')
        if value and value:lower():match('%.rpp$') and value ~= '' then
          out[#out + 1] = value
        end
      end
    end
    file:close()
    return out
  end

  local function score_project(path, wanted)
    local base = path:match('([^/\\]+)$') or path
    base = base:gsub('%.[Rr][Pp][Pp]$', '')
    local folded_base = U.norm(base)
    local folded_wanted = U.norm(wanted)
    if folded_wanted == '' or folded_base == '' then
      return 0
    end
    if folded_base == folded_wanted then
      return 100
    end
    if folded_base:find(folded_wanted, 1, true) then
      return 50 + math.min(20, #folded_wanted)
    end
    if #folded_base >= 4 and folded_wanted:find(folded_base, 1, true) then
      return 20
    end
    return 0
  end

  -- Busca por nombre en los recientes y en la carpeta del proyecto actual.
  local function find_projects(wanted)
    local scored = {}
    local seen = {}
    local function add(path, score)
      if path and score > 0 and not seen[path] then
        seen[path] = true
        scored[#scored + 1] = { path = path, score = score }
      end
    end
    for _, path in ipairs(recent_projects()) do
      add(path, score_project(path, wanted))
    end

    local _, current = reaper.EnumProjects(-1)
    if current and current ~= '' then
      local dir = current:match('^(.*)[/\\][^/\\]+$')
      if dir and reaper.EnumerateFiles then
        for index = 0, 300 do
          local name = reaper.EnumerateFiles(dir, index)
          if not name then
            break
          end
          if name:lower():match('%.rpp$') then
            add(dir .. '/' .. name, score_project(name, wanted))
          end
        end
      end
    end

    table.sort(scored, function(a, b)
      if a.score ~= b.score then
        return a.score > b.score
      end
      return #a.path < #b.path
    end)

    local out = {}
    local top = scored[1] and scored[1].score or 0
    for _, entry in ipairs(scored) do
      if entry.score < top or #out >= 5 then
        break
      end
      out[#out + 1] = entry.path
    end
    return out
  end

  handlers['project.open'] = {
    undo = false,
    desc = 'Abrir un proyecto',
    fn = function(args)
      local wanted = U.str(args, 'name', { required = true })
      local found = find_projects(wanted)
      if #found == 0 then
        U.fail(
          'project_not_found',
          'no encontre ningun proyecto que se parezca a "' .. wanted ..
            '". Proba con el nombre del archivo .rpp.'
        )
      end
      if #found > 1 then
        error({
          code = 'project_candidates',
          message = 'encontre varios proyectos para "' .. wanted .. '": ' .. table.concat(found, ' / '),
          candidates = found,
        }, 0)
      end
      local path = found[1]
      if args.save_current == true then
        reaper.Main_SaveProject(0, false)
      end
      -- "noprompt:" evita el dialogo modal de guardar cambios: si no,
      -- REAPER se queda esperando y el puente se traba.
      local ok = reaper.Main_openProject('noprompt:' .. path)
      if not ok then
        U.fail('reaper_error', 'REAPER no pudo abrir ' .. path)
      end
      return {
        opened = true,
        path = path,
        name = (path:match('([^/\\]+)$') or path):gsub('%.[Rr][Pp][Pp]$', ''),
      }
    end,
  }

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
      local can = reaper.Undo_CanRedo2(0)
      if can == nil then
        return { redone = false, reason = 'no hay nada para rehacer' }
      end
      reaper.Main_OnCommand(40030, 0) -- Edit: Redo
      return { redone = true, action = can }
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

-- ===== cmd_content.lua =============================================
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

-- ===== cmd_sends.lua ===============================================
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

-- ===== cmd_items.lua ===============================================
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

-- ===== registry.lua ================================================
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

-- ===== ipc.lua =====================================================
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

-- ===== main.lua ====================================================
-- Miky · punto de entrada del puente ReaScript
-- Este archivo se ejecuta dentro de REAPER (accion, __startup.lua o CLI).
-- No abre ninguna ventana: solo atiende pedidos y escribe el latido de estado.

if MIKY == nil or MIKY.ipc == nil then
  return
end

MIKY.ipc.main()

