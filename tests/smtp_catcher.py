"""A minimal in-process SMTP server for end-to-end tests.

Phase 4d gates dynamic QR creation behind a verified email, and the
verification link is only ever delivered by email. A real E2E therefore
needs a real mailbox; this stands one up in-process so the test exercises
the actual SMTP path in app/services/mailer.py rather than reaching into
the database to flip a flag.

Deliberately hand-rolled instead of pulling in aiosmtpd: the E2E only needs
to accept one message, and a test-only dependency is a cost paid forever.
Implements just enough of RFC 5321 for smtplib.SMTP().send_message().
"""
import socket
import threading


class SMTPCatcher:
    def __init__(self):
        self.messages = []          # list of dicts: to, data
        self._sock = None
        self._thread = None
        self.port = None

    # -- lifecycle -----------------------------------------------------
    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop = True
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # -- server --------------------------------------------------------
    def _serve(self):
        self._sock.settimeout(0.5)
        while not getattr(self, "_stop", False):
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            conn.settimeout(10)
            fh = conn.makefile("rwb")

            def reply(line):
                fh.write((line + "\r\n").encode())
                fh.flush()

            reply("220 nare-e2e ESMTP")
            sender, rcpts = None, []
            while True:
                line = fh.readline()
                if not line:
                    return
                cmd = line.decode("utf-8", "replace").strip()
                upper = cmd.upper()
                if upper.startswith("EHLO"):
                    reply("250-nare-e2")
                    reply("250 SIZE 10485760")
                elif upper.startswith("HELO"):
                    reply("250 nare-e2")
                elif upper.startswith("MAIL FROM"):
                    sender = cmd[10:].strip().strip("<>")
                    reply("250 OK")
                elif upper.startswith("RCPT TO"):
                    rcpts.append(cmd[8:].strip().strip("<>"))
                    reply("250 OK")
                elif upper.startswith("DATA"):
                    reply("354 End data with <CR><LF>.<CR><LF>")
                    body = []
                    while True:
                        d = fh.readline()
                        if not d or d.strip() == b".":
                            break
                        body.append(d.decode("utf-8", "replace"))
                    self.messages.append({
                        "from": sender,
                        "to": list(rcpts),
                        "data": "".join(body),
                    })
                    reply("250 OK queued")
                elif upper.startswith("RSET"):
                    sender, rcpts = None, []
                    reply("250 OK")
                elif upper.startswith("NOOP"):
                    reply("250 OK")
                elif upper.startswith("QUIT"):
                    reply("221 Bye")
                    return
                else:
                    reply("250 OK")
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # -- helpers -------------------------------------------------------
    def wait_for(self, to_addr, timeout=20):
        """Return the first message addressed to to_addr, waiting for it."""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            for m in self.messages:
                if any(to_addr.lower() in (r or "").lower() for r in m["to"]):
                    return m
            time.sleep(0.1)
        return None
