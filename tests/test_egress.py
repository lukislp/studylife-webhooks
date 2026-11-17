"""Vetted egress (egress.py, audit M4): address classification, resolve-then-vet, and real round
trips through VettedTransport against local receivers - plain http and https with SNI."""

import asyncio
import datetime
import ipaddress
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from studylife_webhooks.db import Webhook
from studylife_webhooks.delivery import deliver_one
from studylife_webhooks.egress import (
    AddressRejectedError,
    VettedTransport,
    is_address_rejection,
    is_public_address,
    resolve_vetted,
)
from studylife_webhooks.metrics import UPSTREAM_REQUESTS_TOTAL

NON_PUBLIC = [
    # IPv4
    "0.0.0.0",
    "0.1.2.3",
    "10.0.0.1",
    "10.42.0.17",  # k3s pod CIDR
    "10.43.0.10",  # k3s service CIDR (kube-dns)
    "127.0.0.1",
    "127.255.255.254",
    "100.64.0.1",
    "100.127.255.255",
    "169.254.169.254",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.10",
    "192.0.0.8",
    "192.0.2.1",
    "198.18.0.1",
    "198.51.100.7",
    "203.0.113.9",
    "224.0.0.251",
    "239.255.255.250",
    "240.0.0.1",
    "255.255.255.255",
    # IPv6
    "::",
    "::1",
    "fc00::1",
    "fd12:3456::1",
    "fe80::1",
    "fec0::1",
    "ff02::1",
    "100::1",
    "2001:db8::1",
    "2001:0:4136:e378::1",  # Teredo
    # IPv6 spellings of private IPv4
    "::ffff:10.0.0.1",
    "::ffff:127.0.0.1",
    "::ffff:169.254.169.254",
    "::ffff:100.64.0.1",
    "::10.0.0.1",  # IPv4-compatible
    "64:ff9b::a00:1",  # NAT64 of 10.0.0.1
    "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
    "2002:a00:1::1",  # 6to4 of 10.0.0.1
    "2002:c0a8:101::1",  # 6to4 of 192.168.1.1
]

PUBLIC = [
    "1.1.1.1",
    "8.8.8.8",
    "100.63.255.255",
    "100.128.0.1",
    "172.15.255.255",
    "172.32.0.1",
    "192.169.0.1",
    "223.255.255.254",
    "2606:4700::1111",
    "2a00:1450:4001::200e",
    "::ffff:8.8.8.8",
    "64:ff9b::808:808",
    "2002:808:808::1",
]


@pytest.mark.parametrize("ip", NON_PUBLIC)
def test_non_public_addresses_are_refused(ip: str):
    assert not is_public_address(ipaddress.ip_address(ip))


@pytest.mark.parametrize("ip", PUBLIC)
def test_public_addresses_are_allowed(ip: str):
    assert is_public_address(ipaddress.ip_address(ip))


class FakeResolver:
    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table
        self.lookups: list[str] = []

    async def __call__(self, host: str, port: int) -> list[str]:
        self.lookups.append(host)
        return self.table.get(host, [])


def _loopback_or_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_loopback or is_public_address(address)


async def test_resolve_vetted_returns_public_addresses():
    resolver = FakeResolver({"hook.example.com": ["8.8.8.8", "2606:4700::1111"]})
    assert await resolve_vetted("hook.example.com", 443, resolver) == ["8.8.8.8", "2606:4700::1111"]


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.5",
        "127.0.0.1",
        "169.254.169.254",
        "100.100.100.100",
        "fd00::1",
        "::ffff:192.168.0.1",
        "fe80::1%eth0",
    ],
)
async def test_name_resolving_to_private_is_refused(ip: str):
    with pytest.raises(AddressRejectedError) as info:
        await resolve_vetted("evil.example.com", 443, FakeResolver({"evil.example.com": [ip]}))
    assert info.value.host == "evil.example.com"


async def test_mixed_public_and_private_answer_is_refused_as_a_whole():
    for answer in (["8.8.8.8", "10.0.0.1"], ["2606:4700::1111", "fe80::1"]):
        with pytest.raises(AddressRejectedError):
            await resolve_vetted(
                "mixed.example.com", 443, FakeResolver({"mixed.example.com": answer})
            )


async def test_unresolvable_name_is_refused():
    with pytest.raises(AddressRejectedError):
        await resolve_vetted("nothing.example.com", 443, FakeResolver({}))


@pytest.mark.parametrize("host", ["127.0.0.1", "[::1]", "::ffff:10.1.2.3"])
async def test_ip_literal_is_vetted_without_dns(host: str):
    resolver = FakeResolver({})
    with pytest.raises(AddressRejectedError):
        await resolve_vetted(host, 443, resolver)
    assert resolver.lookups == []


# --- round trips through VettedTransport ---------------------------------------------------


class Receiver:
    """Minimal HTTP/1.1 receiver on 127.0.0.1 that records request heads (and, for TLS, the SNI
    name the client sent)."""

    def __init__(self, response: bytes) -> None:
        self.response = response
        self.heads: list[str] = []
        self.sni: list[str | None] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        self.heads.append(head.decode("latin-1"))
        writer.write(self.response)
        await writer.drain()
        writer.close()


@asynccontextmanager
async def _serve(
    response: bytes = b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n",
    ssl_context: ssl.SSLContext | None = None,
) -> AsyncIterator[tuple[Receiver, int]]:
    receiver = Receiver(response)
    if ssl_context is not None:
        ssl_context.sni_callback = lambda _sock, name, _ctx: receiver.sni.append(name)
    server = await asyncio.start_server(receiver.handle, "127.0.0.1", 0, ssl=ssl_context)
    port = server.sockets[0].getsockname()[1]
    try:
        yield receiver, port
    finally:
        server.close()
        await server.wait_closed()


async def test_connects_to_the_vetted_address_with_the_original_host_header():
    # A name system DNS cannot resolve: the request can only arrive if the transport connected
    # to the address the vetting resolver returned.
    resolver = FakeResolver({"hook.studylife.invalid": ["127.0.0.1"]})
    async with _serve() as (receiver, port):
        transport = VettedTransport(resolver, allowed=_loopback_or_public)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.post(f"http://hook.studylife.invalid:{port}/in", content=b"{}")
    assert response.status_code == 204
    assert receiver.heads[0].startswith("POST /in HTTP/1.1")
    assert f"Host: hook.studylife.invalid:{port}" in receiver.heads[0]
    assert resolver.lookups == ["hook.studylife.invalid"]


async def test_production_filter_never_opens_a_connection_to_loopback():
    resolver = FakeResolver({"rebind.studylife.invalid": ["127.0.0.1"]})
    async with (
        _serve() as (receiver, port),
        httpx.AsyncClient(transport=VettedTransport(resolver)) as client,
    ):
        with pytest.raises(httpx.ConnectError) as info:
            await client.post(f"http://rebind.studylife.invalid:{port}/", content=b"{}")
    assert is_address_rejection(info.value)
    assert receiver.heads == []


def _tls_server_context(tmp_path: Path, host: str) -> tuple[ssl.SSLContext, ssl.SSLContext]:
    """A throwaway CA and a leaf for host.
    Returns (server context, client context trusting the CA)."""
    now = datetime.datetime.now(datetime.UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "egress-test-ca")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        # Only the NAME, deliberately not 127.0.0.1: validation must be against the host name.
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "tls.crt", tmp_path / "tls.key"
    cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    server.load_cert_chain(cert_file, key_file)
    client = ssl.create_default_context(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())
    return server, client


async def test_https_keeps_sni_and_certificate_validation_on_the_host_name(tmp_path: Path):
    host = "hook.studylife.invalid"
    server_ctx, client_ctx = _tls_server_context(tmp_path, host)
    resolver = FakeResolver({host: ["127.0.0.1"]})
    async with _serve(ssl_context=server_ctx) as (receiver, port):
        transport = VettedTransport(resolver, allowed=_loopback_or_public, ssl_context=client_ctx)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.post(f"https://{host}:{port}/in", content=b"{}")
    assert response.status_code == 204
    assert receiver.sni == [host]
    assert f"Host: {host}:{port}" in receiver.heads[0]


async def test_redirects_are_not_followed():
    resolver = FakeResolver({"hook.studylife.invalid": ["127.0.0.1"]})
    redirect = (
        b"HTTP/1.1 307 Temporary Redirect\r\n"
        b"Location: http://169.254.169.254/latest/meta-data/\r\n"
        b"Content-Length: 0\r\nConnection: close\r\n\r\n"
    )
    async with _serve(redirect) as (receiver, port):
        webhook = Webhook(
            id="w1",
            user_id=1,
            target_url=f"http://hook.studylife.invalid:{port}/in",
            events=["*"],
            secret="shh",
            created_at="2026-11-16T00:00:00Z",
        )
        result = await deliver_one(
            webhook,
            "session.completed",
            "2026-11-16T00:00:00Z",
            {},
            transport=VettedTransport(resolver, allowed=_loopback_or_public),
        )
    assert result.status_code == 307
    assert not result.delivered
    assert len(receiver.heads) == 1


async def test_delivery_to_a_private_target_fails_as_blocked():
    resolver = FakeResolver({"intranet.example.com": ["10.43.0.10"]})
    webhook = Webhook(
        id="w2",
        user_id=1,
        target_url="https://intranet.example.com/hook",
        events=["*"],
        secret="shh",
        created_at="2026-11-16T00:00:00Z",
    )
    blocked = UPSTREAM_REQUESTS_TOTAL.labels(target="webhook-target", outcome="blocked")
    before = blocked._value.get()

    result = await deliver_one(
        webhook,
        "session.completed",
        "2026-11-16T00:00:00Z",
        {},
        transport=VettedTransport(resolver),
    )

    assert not result.delivered
    assert result.status_code is None
    assert "non-public address" in (result.error or "")
    assert blocked._value.get() == before + 1
