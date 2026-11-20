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
