"""CLI `klipin`: start | api | worker | doctor | update-ytdlp."""

import argparse
import subprocess
import sys
import time

HOST = "127.0.0.1"
PORT = 8765


def cmd_api(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("klipin.api.app:app", host=HOST, port=PORT, reload=args.reload)
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from klipin.worker.loop import run

    return run()


def cmd_start(args: argparse.Namespace) -> int:
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
    print("klipin doctor belum diimplementasikan (T-005).", file=sys.stderr)
    return 1


def cmd_update_ytdlp(args: argparse.Namespace) -> int:
    print("klipin update-ytdlp belum diimplementasikan (T-020).", file=sys.stderr)
    return 1


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
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
