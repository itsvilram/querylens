"""Client IP for the rate limit: X-Forwarded-For is believed only from our own proxies."""

from ipaddress import ip_network

import pytest

from app.api.client_ip import client_ip, rate_limit_bucket

PROXIES = [ip_network("10.0.0.0/8")]  # e.g. nginx inside the Docker network


def test_without_a_header_the_peer_is_the_client() -> None:
    assert client_ip("203.0.113.7", None, PROXIES) == "203.0.113.7"


def test_header_from_an_unknown_peer_is_ignored() -> None:
    """A client calling us directly can't pretend to be someone else."""
    assert client_ip("203.0.113.7", "198.51.100.1", PROXIES) == "203.0.113.7"
    assert client_ip("203.0.113.7", "198.51.100.1", []) == "203.0.113.7"


def test_header_from_our_proxy_names_the_client() -> None:
    assert client_ip("10.0.0.2", "203.0.113.7", PROXIES) == "203.0.113.7"


def test_client_written_part_of_the_header_is_skipped() -> None:
    """The client sent "X-Forwarded-For: 1.1.1.1"; our proxy appended the real address."""
    assert client_ip("10.0.0.2", "1.1.1.1, 203.0.113.7", PROXIES) == "203.0.113.7"


def test_chains_of_our_own_proxies_are_walked_through() -> None:
    assert client_ip("10.0.0.2", "1.1.1.1, 203.0.113.7, 10.0.0.9", PROXIES) == "203.0.113.7"


def test_only_our_proxies_in_the_header_gives_the_oldest() -> None:
    assert client_ip("10.0.0.2", "10.0.0.8, 10.0.0.9", PROXIES) == "10.0.0.8"


@pytest.mark.parametrize("header", ["", " , ,"])
def test_empty_header_falls_back_to_the_peer(header: str) -> None:
    assert client_ip("10.0.0.2", header, PROXIES) == "10.0.0.2"


def test_no_peer_address_shares_one_bucket() -> None:
    assert client_ip(None, "203.0.113.7", PROXIES) == "unknown"


def test_ipv4_is_limited_per_address() -> None:
    assert rate_limit_bucket("203.0.113.7") == "203.0.113.7"


def test_ipv6_is_limited_per_64_block() -> None:
    """One user can switch addresses inside their /64 at will."""
    first = rate_limit_bucket("2001:db8:1:2::1")
    assert first == "2001:db8:1:2::/64"
    assert rate_limit_bucket("2001:db8:1:2:ffff::9") == first
    assert rate_limit_bucket("2001:db8:1:3::1") != first


def test_non_addresses_are_kept_short() -> None:
    assert rate_limit_bucket("testclient") == "testclient"
    assert len(rate_limit_bucket("x" * 500)) == 64
