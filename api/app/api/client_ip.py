"""Who is calling? The client IP address, for the rate limit.

X-Forwarded-For is just a header: anyone can send "X-Forwarded-For: 1.2.3.4"
to look like someone else and dodge the limit. So we believe it only when the
request comes from one of our own proxies (TRUSTED_PROXIES, e.g. nginx).
Each proxy appends the address it received the request from, so we read the
list from the right and skip our own proxies: the first address that is not
ours is the client. Everything to its left was written by the client itself.

The first proxy a browser reaches must REPLACE the header, not append to it
(web/nginx.conf). In Docker the browser arrives from the network's gateway,
whose address is inside TRUSTED_PROXIES, so an appended fake would be believed.
"""

from collections.abc import Sequence
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

type Network = IPv4Network | IPv6Network


def _is_trusted(address: str, trusted: Sequence[Network]) -> bool:
    try:
        ip = ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def client_ip(peer: str | None, forwarded_for: str | None, trusted: Sequence[Network]) -> str:
    """peer: the address that connected to us. forwarded_for: the X-Forwarded-For header."""
    if peer is None:
        return "unknown"
    if not forwarded_for or not _is_trusted(peer, trusted):
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, trusted):
            return hop
    return hops[0] if hops else peer  # every hop is one of ours: take the oldest


def rate_limit_bucket(ip: str) -> str:
    """The rate-limit key for an address.

    One IPv6 user usually owns a whole /64 block and can switch addresses
    inside it at will, so IPv6 is limited per /64. Anything that is not an
    address (a test client, a broken header) is kept short and used as is.
    """
    try:
        address = ip_address(ip)
    except ValueError:
        return ip[:64]
    if address.version == 6:
        return str(ip_network(f"{address}/64", strict=False))
    return str(address)
