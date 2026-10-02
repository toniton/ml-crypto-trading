import socket

_orig_getaddrinfo = socket.getaddrinfo


def enforce_ipv4() -> None:
    def getaddrinfo_v4(host, port, family=0, type=0, proto=0, flags=0):
        return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = getaddrinfo_v4
