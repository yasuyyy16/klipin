"""CLI `klipin`: start | api | worker | doctor | update-ytdlp."""

import argparse
import socket
import subprocess
import sys
import time


def _prepare_db() -> None:
    from klipin.config import get_config
    from klipin.db.backup import prepare_database
    from klipin.db.session import get_engine

    prepare_database(get_engine(), get_config().klipin_home)


def bind_sockets(hosts: list[str], port: int) -> list[socket.socket]:
    """Buka socket untuk tiap alamat loopback (BR-012); minimal satu harus berhasil."""
    import structlog

    socks = []
    for host in hosts:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            sock.close()
            structlog.get_logger(__name__).warning("gagal bind", host=host, port=port,
                                                   error=str(exc))
            continue
        socks.append(sock)
    if not socks:
        raise SystemExit(f"Port {port} tidak bisa dipakai. Klipin mungkin sudah berjalan.")
    return socks


def cmd_api(args: argparse.Namespace) -> int:
    import uvicorn

    from klipin.config import get_config
    from klipin.logging import setup_logging

    cfg = get_config()
    setup_logging(cfg, "api")
    _prepare_db()
    if args.reload:
        # shortcut: mode dev --reload hanya bind alamat pertama (uvicorn reload tidak
        # menerima banyak socket); jalankan tanpa --reload untuk bind 127.0.0.1 + ::1.
        uvicorn.run("klipin.api.app:app", host=cfg.klipin_host[0], port=cfg.klipin_port,
                    reload=True, log_config=None)
        return 0
    socks = bind_sockets(cfg.klipin_host, cfg.klipin_port)
    config = uvicorn.Config("klipin.api.app:app", log_config=None)  # logging Klipin
    uvicorn.Server(config).run(sockets=socks)
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from klipin.config import get_config
    from klipin.logging import setup_logging
    from klipin.worker.loop import run

    setup_logging(get_config(), "worker")
    return run()


def cmd_start(args: argparse.Namespace) -> int:
    from klipin.config import get_config
    from klipin.logging import setup_logging

    setup_logging(get_config(), "start")
    _prepare_db()  # sekali sebelum API & Worker jalan, agar tidak berebut migrasi
    procs = [
        subprocess.Popen([sys.executable, "-m", "klipin", name]) for name in ("api", "worker")
    ]
    try:
        # Bila salah satu proses mati, yang lain ikut dimatikan.
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from klipin.config import get_config
    from klipin.doctor import print_report, run_checks

    checks = run_checks(get_config())
    print_report(checks)
    return 0 if all(c.ok for c in checks) else 1


def cmd_update_ytdlp(args: argparse.Namespace) -> int:
    from klipin import system

    print("Memperbarui yt-dlp…", flush=True)
    try:
        result = system.update_ytdlp()
    except system.UpdateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(result["message"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="klipin", description="Klipin: livestream ke klip 9:16")
    sub = parser.add_subparsers(dest="command", required=True, metavar="PERINTAH")
    sub.add_parser("start", help="jalankan API + Worker").set_defaults(func=cmd_start)
    api = sub.add_parser("api", help="jalankan API Server saja")
    api.add_argument("--reload", action="store_true", help="muat ulang otomatis (mode dev)")
    api.set_defaults(func=cmd_api)
    sub.add_parser("worker", help="jalankan Worker saja").set_defaults(func=cmd_worker)
    sub.add_parser("doctor", help="cek prasyarat").set_defaults(func=cmd_doctor)
    sub.add_parser("update-ytdlp", help="perbarui yt-dlp").set_defaults(func=cmd_update_ytdlp)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from pydantic import ValidationError

    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 0
    except ValidationError as exc:
        for err in exc.errors():
            print(f"Konfigurasi tidak valid ({err['loc'][0]}): {err['msg']}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
