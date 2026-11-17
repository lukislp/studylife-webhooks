"""Vetted egress for deliveries to a user's own target_url (2026-11-16 audit M4).

target_url is user input. StudyLife checks its syntax at registration, but a public host NAME can
resolve to 10.x, a cluster service, the node, or the cloud metadata address - and this service runs
inside the cluster. So every connection is vetted at connect time: the host is resolved here, ALL
its addresses must be public (see is_public_address), and the socket is opened to one of exactly
those vetted addresses. Checking and connecting with the same resolution leaves no window for DNS
rebinding. A name that answers with a mix of public and private addresses is refused as a whole.

https stays correct: httpcore starts TLS on the returned stream with the request's host name as
SNI and for certificate validation, and the Host header is built from the URL, never from the IP.

No proxy (trust_env=False: an environment proxy would connect on our behalf and bypass the vetting)
and no redirects (a 3xx from a public host must not lead to a private one).
"""

import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable, Iterable

import anyio
import httpcore
import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Resolves (host, port) to IP address strings. Injectable so tests can map a name to 127.0.0.1.
Resolver = Callable[[str, int], Awaitable[list[str]]]

# Decides whether a resolved address may be connected to. Production: is_public_address. Tests
# widen it to loopback to reach a local fake receiver.
AddressFilter = Callable[[IPAddress], bool]

_NON_PUBLIC_V4 = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",  # "this network", unspecified
        "10.0.0.0/8",  # RFC1918 (incl. the k3s pod and service CIDRs)
        "100.64.0.0/10",  # carrier-grade NAT (Tailscale)
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local incl. cloud metadata
        "172.16.0.0/12",  # RFC1918
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1
        "192.168.0.0/16",  # RFC1918
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",  # TEST-NET-3
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved, incl. broadcast
    )
]

_NON_PUBLIC_V6 = [
    ipaddress.ip_network(n)
    for n in (
        "::/128",  # unspecified
        "::1/128",  # loopback
        "100::/64",  # discard
        "2001::/32",  # Teredo: the embedded address is the relay's, not the target's
        "2001:db8::/32",  # documentation
        "fc00::/7",  # unique local
        "fe80::/10",  # link-local
        "fec0::/10",  # site-local (deprecated)
        "ff00::/8",  # multicast
    )
]

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")
_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")


def is_public_address(address: IPAddress) -> bool:
    """True only for a public internet address. IPv6 spellings of an IPv4 address (mapped,
    IPv4-compatible, NAT64, 6to4) are judged by the embedded IPv4 address."""
    if isinstance(address, ipaddress.IPv4Address):
        return not any(address in net for net in _NON_PUBLIC_V4)

    if address.ipv4_mapped is not None:
        return is_public_address(address.ipv4_mapped)
    if any(address in net for net in _NON_PUBLIC_V6):
        return False
    if address in _IPV4_COMPATIBLE:
        return is_public_address(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    if address in _NAT64 or address in _NAT64_LOCAL:
        return is_public_address(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    if address.sixtofour is not None:
        return is_public_address(address.sixtofour)
    return True


class AddressRejectedError(httpcore.ConnectError):
    """The target's host resolved to a non-public address (or to nothing); no socket was opened.
    httpx re-raises it as httpx.ConnectError with this exception as __cause__."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"connection to {host!r} refused: {reason}")
        self.host = host


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    # Order-preserving de-duplication (getaddrinfo repeats addresses per protocol).
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


async def resolve_vetted(
    host: str, port: int, resolver: Resolver, allowed: AddressFilter = is_public_address
) -> list[str]:
    """The addresses a connection to host may use. Raises AddressRejectedError when any of them
    is not allowed (by default: not public). An IP literal is vetted as-is, without DNS."""
    literal = host.strip("[]")
    try:
        addresses = [str(ipaddress.ip_address(literal))]
    except ValueError:
        addresses = await resolver(host, port)

    if not addresses:
        raise AddressRejectedError(host, "the name did not resolve")
    for address in addresses:
        # Scoped IPv6 results ("fe80::1%eth0") carry a zone id ip_address() does not parse.
        if not allowed(ipaddress.ip_address(address.split("%", 1)[0])):
            raise AddressRejectedError(host, f"it resolves to the non-public address {address}")
    return addresses


class VettedNetworkBackend(httpcore.AsyncNetworkBackend):
    """httpcore network backend that resolves and vets before connecting, then connects to the
    vetted address through the default backend (which also handles TLS on the stream)."""

    def __init__(
        self,
        resolver: Resolver = system_resolver,
        allowed: AddressFilter = is_public_address,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._allowed = allowed
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                addresses = await resolve_vetted(host, port, self._resolver, self._allowed)
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout(f"resolving {host!r} timed out") from exc
        except OSError as exc:  # socket.gaierror and friends
            raise httpcore.ConnectError(f"resolving {host!r} failed: {exc}") from exc

        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore.ConnectError as exc:
                last_error = exc
        assert last_error is not None  # addresses is never empty here
        raise last_error

    async def connect_unix_socket(self, *args, **kwargs) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not a valid webhook target")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class VettedTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose every connection goes through VettedNetworkBackend.

    httpx does not take a network backend as a constructor argument, so the connection pool
    httpx.AsyncHTTPTransport builds is replaced by one with the vetted backend and otherwise the
    same TLS settings. tests/test_egress.py does a real round trip through this class, so an
    httpx upgrade that changes the attribute fails there, not silently."""

    def __init__(
        self,
        resolver: Resolver = system_resolver,
        allowed: AddressFilter = is_public_address,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context or httpx.create_ssl_context(trust_env=False),
            network_backend=VettedNetworkBackend(resolver, allowed),
        )


def is_address_rejection(exc: BaseException) -> bool:
    """True when an httpx error was caused by the vetting (not by the network)."""
    return isinstance(exc.__cause__, AddressRejectedError)
