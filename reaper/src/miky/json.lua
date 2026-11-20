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
