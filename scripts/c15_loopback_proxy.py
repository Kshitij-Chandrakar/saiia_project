"""Rehearsal-only fixed TCP routes; no caller-selected upstream or credentials."""

import select
import socket
import socketserver
import threading

ROUTES = {
    15432: ("db", 5432),
    19999: ("auth", 9999),
    15000: ("storage", 5000),
    13000: ("rest", 3000),
    18025: ("mail", 8025),
    11025: ("mail", 1025),
}


def serve(port, target):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.create_connection(target, timeout=10) as upstream:
                peers = (self.request, upstream)
                while True:
                    readable, _, _ = select.select(peers, [], [], 30)
                    if not readable:
                        return
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.request else self.request).sendall(
                            data
                        )

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    Server(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    for port, target in ROUTES.items():
        threading.Thread(target=serve, args=(port, target), daemon=True).start()
    threading.Event().wait()
