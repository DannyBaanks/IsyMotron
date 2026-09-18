# Guía de IsyMotron (español)

Guía de operación, comando por comando. **Toda la salida de este documento es
salida real ejecutada el 2026-09-17**, no reconstruida ni inventada. Si algo no
coincide cuando lo corras, es un cambio del código, no un error de la guía.

Entorno verificado: Windows 11, `Python 3.10.11`, sin dependencias externas
salvo `pytest`.

---

## 0. Qué es esto, en una frase

Una máquina que decide **ALLOW o DENY** antes de que nada se ejecute, y que
deja un recibo sellado de cada decisión — incluidas las negativas.

Ahora mismo **no hay ningún modelo conectado**, a propósito. Eso viene después;
primero existe la gramática de autoridad que el modelo no va a poder tocar.

---

## 1. Correr la suite de aceptación

```
cd "C:\Development\ISyCo Git\ISyMotron"
python -m pytest tests/ -q
```

Salida real:

```
.......................                                                  [100%]
23 passed in 0.37s
```

Esos 23 tests son el **portón M0** del roadmap: si alguno se cae, la frontera
de autoridad está rota y no se sigue construyendo encima.

## 2. Ver el recorrido completo

```
python tools/m0_demo.py
```

Salida real (fragmentos, el recorrido completo son 7 pasos):

```
=== 1. describe() - what each device says it is ===================
  win11-victus     11-24h2  engine=nt-modern/0.1   granted=5/6
  win98-retrobox   98-se    engine=dos-bridge/0.1  granted=4/4

=== 2. the human approves one narrow lease ========================
  lease lease_7b7d4470d0ca4314
  capability filesystem.read  scope {'roots': ['C:/Users/danny/Photos']}  ttl 300s

=== 3. an in-scope read ===========================================
  [ALLOW] filesystem.read on win11-victus
         result: {"path": "C:/Users/danny/Photos/shot-2026-09-17.png", "bytes": 7, ...}
         seal ok: True  (sha256:faa09b5b05e7279e...)

=== 4. the same capability, one directory over ====================
  [DENY  OUT_OF_SCOPE] filesystem.read on win11-victus
         C:/Users/danny/Secrets/keys.txt is outside ['C:/Users/danny/Photos']
         seal ok: True  (sha256:d25c1ef4c834fb42...)
```

y al final:

```
=== summary =======================================================
  receipts written : 7 -> evidence/M0/
  ALLOW / DENY     : 4 / 3
  seals verified   : 7/7
  relay hops       : 12
```

**Lo importante del paso 4:** es la *misma* capability, con el *mismo* lease
vivo, un directorio más allá. No hace falta quitarle permisos al agente para
que falle; el permiso que tiene simplemente no llega hasta ahí.

## 3. Mirar un recibo por dentro

Los recibos quedan en `evidence/M0/`:

```
python -c "import json;d=json.load(open('evidence/M0/02_read_out_of_scope.json',encoding='utf-8'));print(json.dumps(d['decision'],indent=2,ensure_ascii=False))"
```

Salida real:

```json
{
  "decision": "DENY",
  "reason": "OUT_OF_SCOPE",
  "detail": "C:/Users/danny/Secrets/keys.txt is outside ['C:/Users/danny/Photos']"
}
```

Y el mismo fichero trae `"result": {}` y
`"seal": "sha256:d25c1ef4c834fb42e7abc874bb856ea5..."`.

Dos cosas que hay que leer despacio ahí:

1. **`result` está vacío.** Un DENY deja constancia de la negativa, pero no del
   contenido que se pedía. Si el recibo llevara el fichero dentro, negar sería
   una forma elegante de filtrar.
2. **El DENY también va sellado.** Negarse es un resultado, no un silencio. Un
   recibo de negativa se puede auditar igual que uno de éxito.

## 4. Comprobar que el sello detecta manipulación

```
python -c "import json;d=json.load(open('evidence/M0/01_read_allow.json',encoding='utf-8'));print('sello guardado:',d['seal'][:30],'...')"
```

Salida real:

```
sello guardado: sha256:faa09b5b05e7279e179bba2 ...
```

La comprobación viva está en el test `test_receipt_seal_detects_tampering`: se
cambia un campo del recibo y `verify()` pasa de `True` a `False`.

## 5. Los cuatro DENY que más importan

Cada uno tiene su test. Si alguna vez uno de estos empieza a devolver ALLOW, el
producto dejó de ser lo que dice ser:

| Situación | Razón que devuelve | Test |
|---|---|---|
| Pides un fichero fuera de tus raíces | `OUT_OF_SCOPE` | `test_outside_scope_is_denied_and_still_receipted` |
| Pides algo sin lease | `LEASE_MISSING` | `test_no_lease_is_a_hard_deny` |
| Pides una capability que la máquina no implementa | `CAPABILITY_UNAVAILABLE` | `test_capability_the_host_does_not_implement` |
| Pides una familia de capability sin checker registrado | `CAPABILITY_UNAVAILABLE` | `test_unmapped_capability_family_falls_to_deny` |

El último es el que más se olvida: **la rama `else` de un veredicto nunca cae
en la clase permisiva.** Si alguien inventa `quantum.entangle` y no registra su
comprobador de alcance, la respuesta es DENY, no "bueno, adelante".

## 6. Trampas de rutas que sí están cubiertas

Probadas, no supuestas:

```
C:/Users/danny/Photos/../Secrets/keys.txt   -> DENY  (se resuelve el .. ANTES)
C:\Users\danny\Secrets\keys.txt             -> DENY  (backslash no esquiva)
c:\users\danny\photos\shot-....png          -> ALLOW (mayúsculas no importan)
C:/Users/danny/Photos2/leak.txt             -> DENY  (Photos2 NO está en Photos)
```

La última es la que rompe un `startswith` ingenuo, y por eso tiene test propio.

## 7. Intentar pedir más permiso del que tienes

```
python -c "
import sys;sys.path[:0]=['core','hosts','.']
from simulator.engines import ModernHost
h=ModernHost(fs={}, granted=['filesystem.read'],
             grant_scopes={'filesystem.read':{'roots':['C:/Users/danny/Photos']}})
lease,_=h.request_lease('mobile:danny','filesystem.read',300,{'roots':['C:/','C:/Users/danny/Photos']})
print('pedido :', ['C:/','C:/Users/danny/Photos'])
print('otorgado:', lease.scope['roots'])
"
```

Salida real:

```
pedido : ['C:/', 'C:/Users/danny/Photos']
otorgado: ['C:/Users/danny/Photos']
```

Pedir `C:/` entero no falla: **se ignora**. Esa es la diferencia entre
*estrechar* (siempre permitido) y *ampliar* (imposible). Por eso un cliente
puede intentar pedir de más sin riesgo: nunca lo va a conseguir y nunca se va a
quedar bloqueado por intentarlo.

---

## 8. Tu máquina como host de verdad (M1)

Esto ya no es simulación. Toca disco real.

### 8.1 Ver qué es esta máquina

```
python tools/host_cli.py status
```

Salida real la primera vez, **antes de conceder nada**:

```
host      win11-danny  (Danny (Windows build 10.0.26200))
engine    nt-real/0.1   contract NemoHostContract/v0
grants    <inert: no grant file at C:\Users\progr\AppData\Local\IsyMotron\grants.json>
admin     not granted
lease cap 900s

capability             state        scope
filesystem.read        -
filesystem.write       -
apps.launch            -
system.info            -
process.inspect        -

Nothing is granted. The host is inert: every request returns DENY.
```

**Arranca inerte.** Sin fichero de grants no hay cero restricciones: hay cero
autoridad. Y si el fichero existe pero está corrupto, igual — un JSON que no
parsea significa *ningún permiso*, nunca *todos*.

### 8.2 Conceder permisos (esto eres tú, el humano)

```
python tools/host_cli.py grant filesystem.read  --root "C:/Users/progr/IsyMotron/Demo"
python tools/host_cli.py grant filesystem.write --root "C:/Users/progr/IsyMotron/NemoInbox"
python tools/host_cli.py grant system.info
python tools/host_cli.py grant apps.launch --app notepad.exe
```

Salida real:

```
granted filesystem.read -> {"roots": ["C:/Users/progr/IsyMotron/Demo"]}
written to C:\Users\progr\AppData\Local\IsyMotron\grants.json
```

Ese fichero **es** la autoridad local. Nada remoto lo puede ampliar.

### 8.3 Ejecutar de verdad

```
python tools/host_cli.py do filesystem.read --path "C:/Users/progr/IsyMotron/Demo/nota.txt"
python tools/host_cli.py do filesystem.read --path "C:/Users/progr/IsyMotron/no-concedido.txt"
python tools/host_cli.py do system.info
```

Salida real:

```
[ALLOW] filesystem.read on win11-danny
       {"path": "C:/Users/progr/IsyMotron/Demo/nota.txt", "kind": "file", "bytes": 76,
        "sha256": "sha256:a9fe636ee278b0158f5fe0ad85d22cea...", "text": "Hola desde el host real..."}
       evidence=DEMONSTRATED  seal_ok=True

[DENY OUT_OF_SCOPE] filesystem.read on win11-danny
       C:/Users/progr/IsyMotron/no-concedido.txt is outside ['C:/Users/progr/IsyMotron/Demo']
       evidence=DEMONSTRATED  seal_ok=True

[ALLOW] system.info on win11-danny
       {"os": "Windows 10", "build": "10.0.26200", "machine": "AMD64", "cores": 12,
        "engine": "nt-real/0.1", "python": "3.10.11"}
       evidence=DEMONSTRATED  seal_ok=True
```

Los recibos quedan en `evidence/M1/`. Para quitar un permiso:

```
python tools/host_cli.py revoke filesystem.write
```

### 8.4 Lo que nos enseñó el disco real el primer día

Está entero en `docs/FINDINGS.md`, pero el resumen importa.

Creamos un **junction** (`mklink /J`, no hace falta admin) dentro de la carpeta
concedida, apuntando fuera:

```
C:/.../granted/escape  -->  C:/.../secret
```

La ruta `C:/.../granted/escape/loot.txt` es **léxicamente perfecta**: cada
carácter está dentro de la raíz concedida. El `Enforcer` dijo **ALLOW**.

Los 23 tests de M0 no podían encontrar esto, porque el sistema de ficheros
simulado era un diccionario de Python, y nada dentro de un diccionario puede
apuntar fuera de sí mismo. **Eso es exactamente lo que `docs/EVIDENCE.md` decía
que la simulación borra — escrito antes de encontrarlo.**

Y había un segundo fallo peor: el motor sí lo paró, pero como lanzaba una
excepción normal, el recibo quedaba como `ALLOW` con `evidence=UNKNOWN`. **Una
fuga bloqueada quedaba registrada como acción permitida.** La defensa funcionó
y el registro de la defensa estaba mal, que es la mitad más peligrosa: un
ataque frenado que se apunta como permitido no te enseña nada para la próxima.

Arreglado: ahora el motor puede *denegar*, no sólo fallar, y su DENY manda
sobre el ALLOW del enforcer. Salida real después del arreglo:

```
junction  DENY | OUT_OF_SCOPE | evidence= DEMONSTRATED
          result: {}
          seal ok: True
legitimo  ALLOW | -            | evidence= DEMONSTRATED
```

Regla nueva del contrato: **la comprobación es de dos etapas y las dos pueden
decir DENY.** La léxica no ve el sistema de ficheros; la que resuelve no puede
resolver lo que aún no existe. Corren las dos, siempre.

## 9. Qué NO hace todavía

Para que no haya sorpresas al enseñarlo:

- **No hay modelo.** Ni Nemotron, ni ningún otro. Cero llamadas a ninguna API.
- **No hay Doctor, ni sandbox, ni marketplace, ni login.**
- **No hay app de móvil.** `clients/fake_mobile.py` es un objeto de Python.
- **Sólo hay un Windows real.** Falta un host legacy de verdad.

Esto está en `docs/EVIDENCE.md` con la etiqueta que le corresponde a cada
afirmación. Las nueve *Target Claims* del roadmap **siguen las nueve en
`NOT_DEMONSTRATED`** después de M1. La B y la F se movieron —ahora citan
hardware real en vez de un simulador— pero ninguna cruzó la línea, y mover una
etiqueta porque el progreso *parece* que lo merece es justo lo que este fichero
existe para impedir.

## 10. Lo siguiente, por orden de riesgo

Está razonado en `docs/ROADMAP_DELTA.md`. El resumen:

1. **Hoy mismo:** una llamada de prueba a Nemotron por Nebius, cronometrada.
   Es el requisito de elegibilidad del hackathon y ahora mismo está programado
   para el día 17. Si falla el 1 de octubre, no hay entrega.
2. **Hoy mismo:** confirmar la fecha exacta de cierre en Devpost. El roadmap
   dice "finales de octubre" y pide reconfirmarlo.
3. ~~Host real de Windows 11.~~ **HECHO** — M1, 16 tests sobre disco real.
4. Consola web (no app nativa todavía).
5. Nemotron Intent + Planner, **después** de que la gramática exista.
6. El Doctor. Es la tesis entera; que no sea lo último.
