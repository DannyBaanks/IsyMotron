# Resume Status — 2026-09-30

## Intención del usuario

Convertir TamagotchIA en una mascota donde cada criatura pueda tener su propio GUS local y mantener continuidad histórica real.

## Prioridad inmediata

1. sandbox local GUS;
2. Context Box persistente;
3. historia de stats + memoria + relación + conversación;
4. iOS y Android;
5. PWA sigue viva con fallback/remote;
6. PvP queda diseñado pero no implementado todavía.

## Concepto clave

> El GUS debe recordar la vida de la criatura, pero el motor sigue decidiendo la vida de la criatura.

## Fuente de runtime

Revisar `iSyCodeMovil` actual; no depender de snapshots viejos del paquete.

## Fuente de producto

TamagotchIA actual ya tiene engine/persona/store y capas nativas por Capacitor. Extender, no reemplazar.
