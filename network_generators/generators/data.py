from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable

import typer
from loguru import logger

from network_generators.services.asset import (
    AssetInventory,
    AssetLookupError,
    get_demo_asset_inventory,
)
from network_generators.services.ipam import IPAMLookupError, IPAMSimulator, get_demo_ipam

TOKEN_PATTERN = re.compile(
    r"^<(?P<resolver>[a-zA-Z0-9_]+)(?:\|(?P<args>[^>]*))?>$",
    re.IGNORECASE,
)
DEFAULT_SCHEMA_REFERENCE = "../../data/schema.json"


def main(
    source_dir: Path = typer.Option(
        Path("data"),
        "--source",
        help="Directory containing authoring data files.",
        show_default=True,
    ),
    output_dir: Path = typer.Option(
        Path("generated/data"),
        "--output",
        help="Directory for processed data files.",
        show_default=True,
    ),
    schema_reference: str = typer.Option(
        DEFAULT_SCHEMA_REFERENCE,
        "--schema-reference",
        help="Value to assign to the $schema property in generated files.",
        show_default=True,
    ),
) -> None:
    processor = DataProcessor(
        source_dir=source_dir,
        output_dir=output_dir,
        schema_reference=schema_reference,
        ipam=get_demo_ipam(),
        assets=get_demo_asset_inventory(),
    )
    processor.run()


class DataProcessor:
    def __init__(
        self,
        *,
        source_dir: Path,
        output_dir: Path,
        schema_reference: str,
        ipam: IPAMSimulator,
        assets: AssetInventory,
    ) -> None:
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.schema_reference = schema_reference
        self.ipam = ipam
        self.assets = assets

    def run(self) -> None:
        files = list(self._iter_source_files())
        if not files:
            logger.warning("No JSON files discovered under {}", self.source_dir)
            return

        for src_path in files:
            rel_site = src_path.parent.name
            processed = self._process_file(src_path, site=rel_site)
            self._write_output(processed, rel_site, src_path.name)

        logger.info("Processed {} data file(s) into {}", len(files), self.output_dir)

    def _iter_source_files(self) -> Iterable[Path]:
        if not self.source_dir.exists():
            logger.error("Source directory {} does not exist", self.source_dir)
            return []

        for site_dir in sorted(p for p in self.source_dir.iterdir() if p.is_dir()):
            if site_dir.name == "schema":
                continue
            for json_path in sorted(site_dir.glob("*.json")):
                yield json_path

    def _process_file(self, path: Path, *, site: str) -> Dict[str, Any]:
        raw = json.loads(path.read_text())
        processed = deepcopy(raw)
        hostname = processed.get("hostname", "<unknown>")

        interfaces = processed.get("interfaces", {})
        for iface, details in interfaces.items():
            if not isinstance(details, dict):
                continue
            value = details.get("ipv4")
            if isinstance(value, str):
                details["ipv4"] = self._resolve_token(
                    value, site=site, hostname=hostname, interface=iface
                )

        serial = processed.get("serial_number")
        if isinstance(serial, str):
            processed["serial_number"] = self._resolve_token(
                serial, site=site, hostname=hostname, interface=None
            )

        processed["$schema"] = self.schema_reference
        return processed

    def _resolve_token(
        self,
        candidate: str,
        *,
        site: str,
        hostname: str,
        interface: str | None,
    ) -> str:
        match = TOKEN_PATTERN.match(candidate.strip())
        if not match:
            return candidate

        resolver = match.group("resolver").lower()
        args = match.group("args")
        arguments = [part for part in args.split("|") if part] if args else []

        if resolver == "ipam":
            if interface is None:
                raise ValueError(
                    f"Resolver 'ipam' requires an interface context (value {candidate!r})"
                )
            try:
                return self.ipam.lookup(
                    site=site, hostname=hostname, interface=interface, arguments=arguments
                )
            except IPAMLookupError as exc:
                raise ValueError(
                    f"{hostname} {interface}: {exc}"
                ) from exc

        if resolver == "asset":
            try:
                return self.assets.lookup(
                    site=site, hostname=hostname, arguments=arguments
                )
            except AssetLookupError as exc:
                raise ValueError(f"{hostname}: {exc}") from exc

        raise ValueError(f"Resolver '{resolver}' is not supported in {candidate!r}")

    def _write_output(self, data: Dict[str, Any], site: str, filename: str) -> None:
        target_dir = self.output_dir / site
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        logger.debug("Wrote {}", target)


if __name__ == "__main__":
    typer.run(main)
