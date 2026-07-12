"""IPAM simulator helpers for network data generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

__all__ = ["IPAMLookupError", "IPAMSimulator", "get_demo_ipam"]

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping

SITE_ARG_INDEX = 0
HOSTNAME_ARG_INDEX = 1
INTERFACE_ARG_INDEX = 2


class IPAMLookupError(RuntimeError):
    """Raised when the simulated IPAM cannot provide an allocation."""


@dataclass(slots=True)
class IPAMSimulator:
    """Minimal in-memory IP address management simulator."""

    allocations: Mapping[str, Mapping[str, Mapping[str, str]]]

    def lookup(
        self,
        *,
        site: str,
        hostname: str,
        interface: str,
        arguments: list[str] | None = None,
    ) -> str:
        """Return the IPv4 allocation for the provided context.

        Arguments optionally allow callers to override lookup keys:

        - arguments[0]: alternate site identifier
        - arguments[1]: alternate hostname (defaults to provided hostname)
        - arguments[2]: alternate interface name (defaults to provided interface)
        """
        args = arguments or []
        site_key = (
            args[SITE_ARG_INDEX]
            if len(args) > SITE_ARG_INDEX and args[SITE_ARG_INDEX]
            else site
        )
        hostname_key = (
            args[HOSTNAME_ARG_INDEX]
            if len(args) > HOSTNAME_ARG_INDEX and args[HOSTNAME_ARG_INDEX]
            else hostname
        )
        interface_key = (
            args[INTERFACE_ARG_INDEX]
            if len(args) > INTERFACE_ARG_INDEX and args[INTERFACE_ARG_INDEX]
            else interface
        )

        try:
            return self.allocations[site_key][hostname_key][interface_key]
        except KeyError as exc:  # pragma: no cover - trivial guard
            msg = (
                f"No IPAM allocation for site={site_key!r}, "
                f"hostname={hostname_key!r}, interface={interface_key!r}"
            )
            raise IPAMLookupError(msg) from exc


def get_demo_ipam() -> IPAMSimulator:
    """Return an IPAM simulator pre-populated with demonstration data."""
    return IPAMSimulator(_DEMO_ALLOCATIONS)


_DEMO_ALLOCATIONS: MutableMapping[str, dict[str, dict[str, str]]] = {
    "bos01": {
        "wgw01.bos01": {
            "GigabitEthernet1/1": "10.0.0.1/24",
            "GigabitEthernet1/2": "10.0.0.1/24",
            "Vlan12": "10.1.1.20/20",
        },
        "wgw02.bos01": {
            "GigabitEthernet1/1": "10.0.0.2/24",
            "GigabitEthernet1/2": "10.0.0.1/24",
            "Vlan12": "10.1.1.21/20",
        },
    },
    "nyc01": {
        "wgw01.nyc01": {
            "GigabitEthernet1/1": "10.2.0.1/24",
            "GigabitEthernet1/2": "10.2.0.1/24",
            "Vlan12": "10.2.1.20/20",
        },
        "wgw02.nyc01": {
            "GigabitEthernet1/1": "10.2.0.2/24",
            "GigabitEthernet1/2": "10.2.0.1/24",
            "Vlan12": "10.2.1.21/20",
        },
    },
    "sfo01": {
        "wgw01.sfo01": {
            "ge-0/0/0": "10.3.0.1/24",
            "ge-0/0/1": "10.3.0.1/24",
            "vlan.12": "10.3.1.20/20",
        },
        "wgw02.sfo01": {
            "ge-0/0/0": "10.3.0.2/24",
            "ge-0/0/1": "10.3.0.1/24",
            "vlan.12": "10.3.1.21/20",
        },
    },
    "sfo02": {
        "wgw01.sfo02": {
            "ge-0/0/0": "10.4.0.1/24",
            "ge-0/0/1": "10.4.0.1/24",
            "vlan.12": "10.4.1.20/20",
        },
        "wgw02.sfo02": {
            "ge-0/0/0": "10.4.0.2/24",
            "ge-0/0/1": "10.4.0.1/24",
            "vlan.12": "10.4.1.21/20",
        },
    },
}
