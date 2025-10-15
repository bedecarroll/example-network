"""Asset inventory helpers for simulated data generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

__all__ = ["AssetInventory", "AssetLookupError", "get_demo_asset_inventory"]

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping

SITE_ARG_INDEX = 0
HOSTNAME_ARG_INDEX = 1


class AssetLookupError(RuntimeError):
    """Raised when the simulated asset inventory cannot be satisfied."""


@dataclass(slots=True)
class AssetInventory:
    """Minimal asset database simulator keyed by site and hostname."""

    assets: Mapping[str, Mapping[str, str]]

    def lookup(
        self,
        *,
        site: str,
        hostname: str,
        arguments: list[str] | None = None,
    ) -> str:
        """Return the serial number for the given device."""
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

        try:
            return self.assets[site_key][hostname_key]
        except KeyError as exc:  # pragma: no cover - trivial guard
            msg = (
                f"No asset record for site={site_key!r}, hostname={hostname_key!r}"
            )
            raise AssetLookupError(msg) from exc


def get_demo_asset_inventory() -> AssetInventory:
    """Return an asset inventory pre-populated with demonstration data."""
    return AssetInventory(_DEMO_ASSETS)


_DEMO_ASSETS: MutableMapping[str, dict[str, str]] = {
    "bos01": {
        "wgw01.bos01": "FTX1234A01",
        "wgw02.bos01": "FTX1234A02",
    },
    "nyc01": {
        "wgw01.nyc01": "FTX5678B01",
        "wgw02.nyc01": "FTX5678B02",
    },
    "sfo01": {
        "wgw01.sfo01": "FTX2468C01",
        "wgw02.sfo01": "FTX2468C02",
    },
    "sfo02": {
        "wgw01.sfo02": "FTX1357D01",
        "wgw02.sfo02": "FTX1357D02",
    },
}
