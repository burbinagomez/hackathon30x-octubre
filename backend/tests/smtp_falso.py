"""SMTP falso en 127.0.0.1: guarda lo que recibe, nunca reenvía. Sin TLS: SMTP_SEGURIDAD=ninguna."""
import base64
import socketserver
import threading
from dataclasses import dataclass, field

USUARIO = "resend"
CLAVE_FALSA = "re_test_XXXXXXXXXXXXXXXX"


@dataclass
class Recibido:
    remitente: str
    destinos: list[str]
    datos: bytes


@dataclass
class SmtpFalso:
    rechazar: frozenset[str] = frozenset()
    cortar_en_data: bool = False
    mensajes: list[Recibido] = field(default_factory=list)
    credenciales: list[tuple[str, str]] = field(default_factory=list)

    def __enter__(self) -> "SmtpFalso":
        falso = self

        class _Sesion(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                falso._atender(self.rfile, self.wfile)

        self._servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Sesion)
        self._servidor.daemon_threads = True
        self.host, self.port = self._servidor.server_address
        threading.Thread(target=self._servidor.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_: object) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()

    def _atender(self, entrada, salida) -> None:
        def decir(linea: str) -> None:
            salida.write(linea.encode() + b"\r\n")

        decir("220 smtp-falso")
        remitente, destinos = "", []
        while linea := entrada.readline():
            orden = linea.decode().rstrip("\r\n")
            verbo = orden.split(" ", 1)[0].upper()
            if verbo in ("EHLO", "HELO"):
                decir("250-smtp-falso")
                decir("250 AUTH PLAIN")
            elif verbo == "AUTH":
                _, usuario, clave = base64.b64decode(orden.split()[2]).decode().split("\0")
                self.credenciales.append((usuario, clave))
                decir("235 ok")
            elif verbo == "MAIL":
                remitente, destinos = _direccion(orden), []
                decir("250 ok")
            elif verbo == "RCPT":
                destino = _direccion(orden)
                if destino in self.rechazar:
                    decir("550 no existe")
                else:
                    destinos.append(destino)
                    decir("250 ok")
            elif verbo == "DATA":
                if self.cortar_en_data:
                    return
                decir("354 dale")
                filas = []
                while (fila := entrada.readline()) not in (b".\r\n", b""):
                    filas.append(fila[1:] if fila.startswith(b"..") else fila)
                self.mensajes.append(Recibido(remitente, destinos, b"".join(filas)))
                decir("250 ok")
            elif verbo == "QUIT":
                decir("221 chau")
                return
            else:
                decir("250 ok")


def _direccion(orden: str) -> str:
    """`MAIL FROM:<a@b> SIZE=1` → `a@b`."""
    return orden[orden.index("<") + 1 : orden.index(">")]
