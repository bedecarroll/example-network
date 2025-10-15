from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

__all__ = ["AssetLookupError", "AssetInventory", "get_demo_asset_inventory"]


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
        site_key = args[0] if len(args) >= 1 and args[0] else site
        hostname_key = args[1] if len(args) >= 2 and args[1] else hostname

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
