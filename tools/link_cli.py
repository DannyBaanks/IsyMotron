#!/usr/bin/env python3
"""isymotron link -- oficinas enlazadas (port de Munder Link, M3).

Passthrough delgado: toda la verdad vive en core/isymotron/link/.
`--help` nunca ejecuta nada (leccion de `demo --help`).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from isymotron.link import identity, pairing, receipts  # noqa: E402
from isymotron.link.remote import LinkCallError, post_json, resolve_peer, sealed_call  # noqa: E402
from isymotron.link.server import LinkServer  # noqa: E402


def cmd_estado(args: argparse.Namespace, directory: Path) -> int:
    ident = identity.load_identity(directory)
    peers = identity.load_peers(directory)
    try:
        inbox = sum(
            1
            for line in (directory / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
            if '"status": "queued"' in line or '"status":"queued"' in line
        )
    except OSError:
        inbox = 0
    print("ESTA OFICINA")
    print(f"  {ident['name']}  {identity.pretty_fingerprint(ident['office_id'])}")
    print("")
    print("ENLAZADAS")
    if not peers:
        print("  (ninguna — isymotron link emparejar <direccion>)")
    for peer in peers.values():
        print(f"  - {peer.get('name')}  {peer.get('office_id', '')[:16]}")
    print(f"inbox: {inbox} en cola")
    _ = args
    return 0


def cmd_buscar(args: argparse.Namespace, directory: Path) -> int:
    from isymotron.link.server import discover

    _ = directory
    print("isymotron: buscando oficinas (red local)…")
    for card in discover(timeout_s=args.seconds):
        print(f"  {card.get('name')}  {identity.pretty_fingerprint(card.get('office_id', ''))}  {card.get('seen_at')}")
    return 0


def cmd_emparejar(args: argparse.Namespace, directory: Path) -> int:
    ident = identity.load_identity(directory)
    own_nonce = pairing.fresh_nonce()
    status, body = post_json(
        f"http://{args.direccion}/link/v1/pair",
        {**identity.public_card(ident), "nonce": own_nonce, "port": 0},
    )
    if status != 200 or not body.get("ok"):
        print(f"emparejamiento fallido: {body}")
        return 1
    peer = body["peer"]
    code = pairing.short_code(
        ident["sign"]["x"], str(peer["sign_pub"]), own_nonce, str(body["nonce"])
    )
    print(f"Emparejando {ident['name']} -> {peer.get('name')} ({args.direccion})")
    print(f"Huella: {identity.pretty_fingerprint(peer.get('office_id', ''))}")
    print("")
    print(f"Código:  {code[:3]} {code[3:]}")
    print("")
    print("En la otra máquina corre:  isymotron link aceptar  y revisa que muestre este mismo código.")
    if not args.si:
        answer = input("¿Coincide el código en la otra pantalla? [s/N] ").strip().lower()
        if answer not in ("s", "si", "sí", "y", "yes"):
            print("cancelado: no se confió en nadie.")
            return 2
    pairing.trust_peer({**peer, "addresses": [args.direccion]}, directory)
    print(f"listo de este lado. Prueba: isymotron link enviar {peer.get('name')} \"hola\"")
    return 0


def cmd_aceptar(args: argparse.Namespace, directory: Path) -> int:
    pending = identity.load_pending(directory)
    if args.codigo is None:
        if not pending:
            print("sin solicitudes pendientes.")
            return 0
        for entry in pending.values():
            print(f"  {entry.get('name')}  código {entry.get('code')}")
        print("Escribe el código que ves en la OTRA pantalla: isymotron link aceptar <codigo>")
        return 0
    pinned = pairing.accept(args.codigo, directory)
    if pinned is None:
        print("código no coincide con ninguna solicitud pendiente.")
        return 1
    print(f"enlazada con {pinned['name']}. Ya puede delegarte trabajo.")
    return 0


def _call_or_exit(directory: Path, oficina: str, payload: dict) -> dict:
    try:
        return sealed_call(directory, oficina, payload)
    except LinkCallError as exc:
        raise SystemExit(str(exc))


def cmd_enviar(args: argparse.Namespace, directory: Path) -> int:
    body = _call_or_exit(
        directory, args.oficina,
        {"op": "delegate", "title": args.titulo or args.texto[:60], "body": args.texto},
    )
    peer = resolve_peer(directory, args.oficina)
    receipts.append_receipt(
        directory, "link_delegated",
        {"task_id": body["task_id"], "to": peer["office_id"], "title": args.titulo or ""},
    )
    print(f"delegada a {peer.get('name')} → {body['task_id']}")
    print(f"sigue: isymotron link tarea {args.oficina} {body['task_id']}")
    return 0


def cmd_tarea(args: argparse.Namespace, directory: Path) -> int:
    body = _call_or_exit(directory, args.oficina, {"op": "task", "task_id": args.task_id})
    task = body.get("task", {})
    print(f"  {task.get('title', '')}  {task.get('status', '')}")
    return 0


def cmd_mensaje(args: argparse.Namespace, directory: Path) -> int:
    _call_or_exit(directory, args.oficina, {"op": "message", "task_id": args.task_id, "text": args.texto})
    print("contexto agregado.")
    return 0


def cmd_cancelar(args: argparse.Namespace, directory: Path) -> int:
    _call_or_exit(
        directory, args.oficina,
        {"op": "cancel", "task_id": args.task_id, "reason": args.motivo or ""},
    )
    print("cancelada.")
    return 0


def cmd_olvidar(args: argparse.Namespace, directory: Path) -> int:
    dropped = pairing.forget(args.oficina, directory)
    if dropped is None:
        print(f"no conozco esa oficina: {args.oficina!r}")
        return 1
    print(f"olvide a {dropped.get('name')} (unilateral: ella te recuerda hasta que te olvide).")
    return 0


def cmd_servir(args: argparse.Namespace, directory: Path) -> int:
    try:
        server = LinkServer(directory, tcp_port=args.port, udp_port=args.udp_port)
    except OSError as exc:
        # A bind failure must not look like a successful start (trap caught
        # 2026-09-25: second `servir` bound nowhere and pairings went to the
        # zombie on the same port).
        print(f"no pude abrir :{args.port} — ¿ya hay un 'link servir' corriendo? ({exc})")
        return 1
    print(f"sirviendo enlace en {server.tcp_address} (Ctrl+C para detener)")
    server.start()
    try:
        while True:
            import time as _time

            _time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    from isymotron.link.server import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT

    parser = argparse.ArgumentParser(prog="isymotron link", description="Oficinas enlazadas.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("estado", aliases=["status"], help="esta oficina + enlazadas").set_defaults(func=cmd_estado)
    buscar = sub.add_parser("buscar", aliases=["discover"], help="buscar oficinas (red local)")
    buscar.add_argument("--seconds", type=float, default=1.0)
    buscar.set_defaults(func=cmd_buscar)
    emparejar = sub.add_parser("emparejar", aliases=["pair"], help="pedir emparejamiento")
    emparejar.add_argument("direccion", help="IP:port, IP Tailscale o nombre visto en buscar")
    emparejar.add_argument("--si", action="store_true", help="confiar sin preguntar (solo pruebas)")
    emparejar.set_defaults(func=cmd_emparejar)
    aceptar = sub.add_parser("aceptar", aliases=["accept"], help="aceptar con el código")
    aceptar.add_argument("codigo", nargs="?", default=None)
    aceptar.set_defaults(func=cmd_aceptar)
    enviar = sub.add_parser("enviar", aliases=["send"], help="delegar trabajo")
    enviar.add_argument("oficina")
    enviar.add_argument("texto")
    enviar.add_argument("--titulo", default="")
    enviar.set_defaults(func=cmd_enviar)
    tarea = sub.add_parser("tarea", aliases=["task"], help="estado de tarea delegada")
    tarea.add_argument("oficina")
    tarea.add_argument("task_id")
    tarea.set_defaults(func=cmd_tarea)
    mensaje = sub.add_parser("mensaje", aliases=["message"], help="agregar contexto")
    mensaje.add_argument("oficina")
    mensaje.add_argument("task_id")
    mensaje.add_argument("texto")
    mensaje.set_defaults(func=cmd_mensaje)
    cancelar = sub.add_parser("cancelar", aliases=["cancel"], help="cancelar delegada")
    cancelar.add_argument("oficina")
    cancelar.add_argument("task_id")
    cancelar.add_argument("motivo", nargs="?", default="")
    cancelar.set_defaults(func=cmd_cancelar)
    olvidar = sub.add_parser("olvidar", aliases=["forget"], help="quitar confianza (unilateral)")
    olvidar.add_argument("oficina")
    olvidar.set_defaults(func=cmd_olvidar)
    servir = sub.add_parser("servir", aliases=["serve"], help="servidor en primer plano")
    servir.add_argument("--port", type=int, default=DEFAULT_TCP_PORT)
    servir.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    servir.set_defaults(func=cmd_servir)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args, identity.state_dir())


if __name__ == "__main__":
    raise SystemExit(main())
