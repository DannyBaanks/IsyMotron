# 11 — Mensaje recomendado para Claude / Codex / OpenISy

Pégales esto junto con el ZIP:

---

Quiero que implementes la siguiente frontera de TamagotchIA usando este paquete como especificación, pero **el repo actual manda sobre el documento**.

Primero inspecciona `DannyBaanks/TamagotchIA` completo y verifica branch/HEAD, paths reales, tests, build, save format, persona contract, iOS/Android Capacitor y estado actual. Después inspecciona `DannyBaanks/iSyCodeMovil` y localiza el runtime GUS vigente en iOS y Android. No copies nada hasta entender dependencias, licencias y qué piezas son realmente reutilizables.

Objetivo: que cada criatura pueda tener un GUS local persistente. El motor determinista sigue siendo verdad. GUS recibe un Context Box versionado con historia, stats actuales/tendencias, eventos, memorias, relación, preferencias, resumen conversacional y open threads; responde como la criatura; jamás muta el juego directamente.

Trabaja en fases pequeñas. Mantén PWA funcional. No metas PvP todavía. No hagas refactors ajenos. Antes de cada edición importante, di qué path real verificaste. Después de cada fase, corre las pruebas mínimas. Separa DEMONSTRATED / INFERRED / NOT_DEMONSTRATED. No declares device support sin prueba en hardware físico.

Si encuentras divergencias respecto al ZIP, corrige el plan y documenta por qué. Si una integración local exige permisos o autoridad más amplios de los previstos, detente antes de ampliarlos.

Entrega al final: cambios, tests, evidence matrix, device status, migration notes, rollback y siguiente frontera mínima.

---
