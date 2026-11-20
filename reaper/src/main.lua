-- Miky · punto de entrada del puente ReaScript
-- Este archivo se ejecuta dentro de REAPER (accion, __startup.lua o CLI).
-- No abre ninguna ventana: solo atiende pedidos y escribe el latido de estado.

if MIKY == nil or MIKY.ipc == nil then
  return
end

MIKY.ipc.main()
