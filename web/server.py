"""Single-user HTTP console for a trusted local network."""

from __future__ import annotations

import argparse
import fcntl
import hmac
import ipaddress
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit, parse_qs

from .catalog import Catalog, ValidationError
from .jobs import Manager

STATIC = Path(__file__).parent / "static"


def local_ipv4_addresses():
    """Discover interface addresses, without depending on external network access."""
    addresses = set()
    try:
        result = subprocess.run(["ip", "-j", "-4", "address", "show", "up"],
                                capture_output=True, text=True, check=True, timeout=2)
        for interface in json.loads(result.stdout):
            addresses.update(info["local"] for info in interface.get("addr_info", [])
                             if info.get("family") == "inet")
    except (OSError, ValueError, subprocess.SubprocessError):
        try:
            addresses.update(info[4][0] for info in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM))
        except OSError:
            pass
    return sorted(address for address in addresses if not ipaddress.ip_address(address).is_loopback)


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, catalog, data_dir):
        data_dir = Path(data_dir).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        self.lockfile = (data_dir / "server.lock").open("a")
        try:
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lockfile.close()
            raise RuntimeError("该数据目录已有控制台实例运行") from None
        self.catalog = catalog
        self.token = secrets.token_urlsafe(32)
        self.access_addresses = local_ipv4_addresses() if address[0] == "0.0.0.0" else [address[0]]
        self.allowed_hosts = {"127.0.0.1", "localhost", *self.access_addresses}
        try:
            super().__init__(address, Handler)
            self.manager = Manager(catalog, data_dir)
        except BaseException:
            self.lockfile.close()
            raise

    def server_close(self):
        try:
            if hasattr(self, "manager"):
                self.manager.close()
            super().server_close()
        finally:
            self.lockfile.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "RoboLabConsole/1"

    def log_message(self, *_):
        pass

    def headers_for(self, status, mime, length, **extra):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        for name, value in extra.items():
            self.send_header(name.replace("_", "-"), value)
        self.end_headers()

    def json(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.headers_for(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def allowed_host(self):
        port = self.server.server_port
        return self.headers.get("Host", "") in {f"{host}:{port}" for host in self.server.allowed_hosts}

    def authenticated(self, mutation=False):
        token = self.headers.get("X-XPL-Token", "")
        if not mutation and not token:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                if "xpl_session" in cookie:
                    token = cookie["xpl_session"].value
            except Exception:
                pass
        return self.allowed_host() and hmac.compare_digest(token, self.server.token)

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, KeyError, OSError) as exc:
            self.json({"error": str(exc)}, 400)

    def get(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        if not self.allowed_host():
            self.json({"error": "访问地址不在控制台监听地址中"}, 403)
            return
        if path == "/":
            data = (STATIC / "index.html").read_text().replace("__XPL_TOKEN__", self.server.token).encode()
            self.headers_for(200, "text/html; charset=utf-8", len(data), Set_Cookie=f"xpl_session={self.server.token}; HttpOnly; SameSite=Strict; Path=/")
            self.wfile.write(data)
            return
        if path in {"/app.js", "/style.css"}:
            target = STATIC / path[1:]
            data = target.read_bytes()
            self.headers_for(200, "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8", len(data))
            self.wfile.write(data)
            return
        if not self.authenticated():
            self.json({"error": "请从控制台首页建立会话"}, 403)
            return
        if path == "/api/catalog":
            self.json(self.server.catalog.snapshot())
            return
        if path == "/api/runs":
            query = parse_qs(url.query)
            limit = int(query.get("limit", [500])[0])
            offset = int(query.get("offset", [0])[0])
            if not 1 <= limit <= 500 or offset < 0:
                raise ValueError("limit 必须为 1–500，offset 必须非负")
            self.json({"runs": self.server.manager.store.list(limit, offset)})
            return
        match = re.fullmatch(r"/api/runs/([0-9a-f]{16})(?:/(logs|artifacts|files)(?:/(.*))?)?", path)
        if match is None:
            self.json({"error": "接口不存在"}, 404)
            return
        run_id, view, relative = match.groups()
        store = self.server.manager.store
        run = store.get(run_id)
        if run is None:
            self.json({"error": "运行不存在"}, 404)
            return
        directory = store.directory(run_id)
        if view is None:
            self.json(run)
        elif view == "logs":
            log = directory / "console.log"
            size = log.stat().st_size if log.exists() else 0
            offset = max(0, min(size, int(parse_qs(url.query).get("offset", [0])[0])))
            content = b""
            if log.exists():
                with log.open("rb") as stream:
                    stream.seek(offset)
                    content = stream.read(65536)
                    offset = stream.tell()
            self.json({"text": content.decode(errors="replace"), "offset": offset})
        elif view == "artifacts":
            files = []
            for f in sorted(directory.rglob("*")):
                if len(files) >= 200:
                    break
                if f.is_file() and f.suffix in {".json", ".jsonl", ".log", ".mp4", ".png"}:
                    try:
                        f.resolve().relative_to(directory.resolve())
                    except ValueError:
                        continue
                    files.append({"path": f.relative_to(directory).as_posix(), "size": f.stat().st_size})
            self.json({"files": files})
        elif view == "files":
            target = (directory / (relative or "")).resolve()
            try:
                target.relative_to(directory.resolve())
            except ValueError:
                self.json({"error": "不允许读取运行目录之外的文件"}, 403)
                return
            if not target.is_file() or target.suffix not in {".json", ".jsonl", ".log", ".mp4", ".png"}:
                self.json({"error": "文件不存在或类型不支持"}, 404)
                return
            size = target.stat().st_size
            start, end, status = 0, max(0, size - 1), 200
            extra = {"Accept_Ranges": "bytes"}
            if self.headers.get("Range"):
                bounds = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers["Range"])
                if bounds is None or int(bounds[1]) >= size:
                    self.json({"error": "无效的文件范围"}, 416)
                    return
                start = int(bounds[1])
                end = min(end, int(bounds[2])) if bounds[2] else end
                if end < start:
                    self.json({"error": "无效的文件范围"}, 416)
                    return
                status = 206
                extra["Content_Range"] = f"bytes {start}-{end}/{size}"
            length = 0 if size == 0 else end - start + 1
            mime = mimetypes.guess_type(target.name)[0] or "text/plain"
            self.headers_for(status, mime, length, **extra)
            with target.open("rb") as stream:
                stream.seek(start)
                while length:
                    data = stream.read(min(length, 262144))
                    if not data:
                        break
                    self.wfile.write(data)
                    length -= len(data)

    def do_POST(self):
        try:
            if not self.authenticated(mutation=True):
                self.json({"error": "无效的会话令牌"}, 403)
                return
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 65536:
                self.json({"error": "请求体大小不合法"}, 400)
                return
            payload = json.loads(self.rfile.read(size))
            if self.path == "/api/runs":
                self.json(self.server.manager.create(payload), 201)
            else:
                match = re.fullmatch(r"/api/runs/([0-9a-f]{16})/cancel", self.path)
                if match is None:
                    self.json({"error": "接口不存在"}, 404)
                    return
                self.json(self.server.manager.cancel(match[1]))
        except KeyError:
            self.json({"error": "运行不存在"}, 404)
        except (ValueError, TypeError) as exc:
            self.json({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(prog="start.sh", description="启动 RoboLab 控制台")
    parser.add_argument("--host", default="0.0.0.0", help="监听 IPv4 地址，默认 0.0.0.0；仅本机访问可设为 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/web"))
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        if ipaddress.ip_address(args.host).version != 4:
            raise ValueError("--host 请使用 IPv4 地址")
        config = json.loads(args.config.read_text()) if args.config else {}
        with ConsoleServer((args.host, args.port), Catalog(config), args.data_dir) as server:
            local_address = "127.0.0.1" if args.host == "0.0.0.0" else args.host
            print(f"RoboLab 控制台：http://{local_address}:{server.server_port}", flush=True)
            print(f"  Python   : {sys.executable} ({sys.version.split()[0]})")
            print(f"  工作目录 : {server.catalog.root}")
            print(f"  配置文件 : {args.config.resolve() if args.config else '内置默认配置'}")
            print(f"  历史目录 : {args.data_dir.resolve()}")
            print(f"  监听地址 : {args.host}:{server.server_port}")
            snapshot = server.catalog.snapshot()
            print(f"  策略目录 : {len(snapshot['policies'])} 个活动策略")
            for benchmark in snapshot["benchmarks"]:
                status = "入口已配置" if benchmark["ready"] else "待配置"
                print(f"  {benchmark['name']:<10}: {status}")
            for address in server.access_addresses:
                if not ipaddress.ip_address(address).is_loopback:
                    print(f"\n  远程访问 : http://{address}:{server.server_port}/")
            print("\n服务已就绪。模型和仿真将在提交评测任务后加载。")
            print("直接打开上方地址；Ctrl+C 停止服务及其评测任务。", flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                print("\n正在停止控制台并清理评测任务…", flush=True)
        print("控制台已停止。", flush=True)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"控制台启动失败：{exc}\n")


if __name__ == "__main__":
    main()
