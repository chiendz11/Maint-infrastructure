"""Bounded local adapters for the application's explicit loopback test profiles.

TCP preserves PostgreSQL/Kafka wire bytes. HTTP forwards scoped requests; only
the Worker registry/ML routes inject their own client-credentials bearer. All
other routes preserve caller Authorization and application authorization.
"""

import http.client
import http.server
import select
import socket
import socketserver
import ssl
import threading
import time

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailer", "transfer-encoding", "upgrade"}
ALLOWED = {"postgres", "kafka", "keycloak", "business-api", "processing-read-api",
           "ingestion-api", "ml-service", "frontend", "sensor", "simulator-ui"}


def forwarded_headers(incoming, *, tls, client_host):
    # The edge owns proxy metadata; never trust caller-supplied forwarding headers.
    blocked = HOP | {"forwarded", "x-forwarded-proto", "x-forwarded-host", "x-forwarded-port", "x-forwarded-for"}
    result = {key: value for key, value in incoming.items() if key.lower() not in blocked}
    result["X-Forwarded-Proto"] = "https" if tls else "http"
    result["X-Forwarded-For"] = client_host
    return result


def target(spec):
    host, port = spec["target_host"], spec["target_port"]
    short = host.removesuffix(".maintai-local.svc.cluster.local")
    if short not in ALLOWED and host != "127.0.0.1":
        raise ValueError("Adapter target is not a local service")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Adapter target port is invalid")
    return host, port


class LimitedMixIn(socketserver.ThreadingMixIn):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(128)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class TCPServer(LimitedMixIn, socketserver.TCPServer):
    allow_reuse_address = True


class HTTPServer(LimitedMixIn, http.server.HTTPServer):
    allow_reuse_address = True


def tcp_server(spec):
    upstream = target(spec)

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                with socket.create_connection(upstream, timeout=5) as remote:
                    remote.settimeout(None)
                    peers = {self.request: remote, remote: self.request}
                    activity = time.monotonic()
                    while True:
                        readable, _, _ = select.select(list(peers), [], [], 60)
                        if not readable:
                            if time.monotonic() - activity >= 3600:
                                break
                            continue
                        activity = time.monotonic()
                        for current in readable:
                            raw = current.recv(65536)
                            if not raw:
                                return
                            peers[current].sendall(raw)
            except OSError:
                return

    return TCPServer((spec.get("bind", "127.0.0.1"), spec["port"]), Handler)


def http_server(spec, tokens):
    routes = sorted(spec.get("routes", [spec]), key=lambda x: len(x.get("prefix", "/")), reverse=True)
    for route in routes:
        target(route)
    if any(route.get("oauth") for route in routes) and spec.get("bind", "127.0.0.1") != "127.0.0.1":
        raise ValueError("Credential-injecting route must bind loopback")

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass

        def forward(self):
            if not self.path.startswith("/") or self.path.startswith("//"):
                self.send_error(400)
                return
            route = next((r for r in routes if self.path.startswith(r.get("prefix", "/"))), None)
            if route is None or self.headers.get("Transfer-Encoding"):
                self.send_error(400)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 262144:
                    raise ValueError("Request body exceeds bound")
                self.connection.settimeout(15)
                body = self.rfile.read(size) if size else None
                if body is not None and len(body) != size:
                    raise ValueError("Incomplete body")
                headers = forwarded_headers(self.headers, tls=spec.get("tls", False), client_host=self.client_address[0])
                if route.get("oauth"):
                    headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
                    headers["Authorization"] = "Bearer " + tokens.get(route["oauth"])
                upstream = http.client.HTTPConnection(*target(route), timeout=120)
                try:
                    upstream.request(self.command, self.path, body=body, headers=headers)
                    response = upstream.getresponse()
                    self.send_response(response.status)
                    for key, value in response.getheaders():
                        if key.lower() not in HOP:
                            self.send_header(key, value)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        while data := response.read1(65536):
                            self.wfile.write(data)
                            self.wfile.flush()
                finally:
                    upstream.close()
            except (OSError, ValueError, http.client.HTTPException):
                # Never retry a forwarded POST: the upstream may have committed it.
                self.close_connection = True

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = forward

    server = HTTPServer((spec.get("bind", "127.0.0.1"), spec["port"]), Handler)
    if spec.get("tls"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain("/tls/tls.crt", "/tls/tls.key")
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def serve(configuration, tokens, stopped):
    servers = [tcp_server(item) for item in configuration.get("tcp", [])]
    servers += [http_server(item, tokens) for item in configuration.get("http", [])]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while not stopped.wait(1):
            pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
