"""CLI helpers for generating normalized network data files."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from loguru import logger

from network_generators.services.asset import (
    AssetInventory,
    AssetLookupError,
    get_demo_asset_inventory,
)
from network_generators.services.ipam import (
    IPAMLookupError,
    IPAMSimulator,
    get_demo_ipam,
)
from network_generators.services.rules import RuleEngine

if TYPE_CHECKING:
    from collections.abc import Iterable
    from network_generators.services.rules import RuleEngineSession

TOKEN_PATTERN = re.compile(
    r"^<(?P<resolver>[a-zA-Z0-9_]+)(?:\|(?P<args>[^>]*))?>$",
    re.IGNORECASE,
)
DEFAULT_SCHEMA_REFERENCE = "../../data/schema.json"
SOURCE_DIR_OPTION = typer.Option(
    Path("data"),
    "--source",
    help="Directory containing authoring data files.",
    show_default=True,
)
OUTPUT_DIR_OPTION = typer.Option(
    Path("generated/data"),
    "--output",
    help="Directory for processed data files.",
    show_default=True,
)
SCHEMA_REFERENCE_OPTION = typer.Option(
    DEFAULT_SCHEMA_REFERENCE,
    "--schema-reference",
    help="Value to assign to the $schema property in generated files.",
    show_default=True,
)
IPAM_INTERFACE_REQUIRED_MESSAGE = (
    "Resolver 'ipam' requires an interface context (value {candidate!r})"
)
IPAM_LOOKUP_FAILED_MESSAGE = "{hostname} {interface}: {error}"
ASSET_LOOKUP_FAILED_MESSAGE = "{hostname}: {error}"
UNSUPPORTED_RESOLVER_MESSAGE = (
    "Resolver '{resolver}' is not supported in {candidate!r}"
)


def main(
    source_dir: Path = SOURCE_DIR_OPTION,
    output_dir: Path = OUTPUT_DIR_OPTION,
    schema_reference: str = SCHEMA_REFERENCE_OPTION,
) -> None:
    """Process source data and write normalized JSON outputs."""
    dependencies = ProcessorDependencies(
        ipam=get_demo_ipam(),
        assets=get_demo_asset_inventory(),
    )
    processor = DataProcessor(
        source_dir=source_dir,
        output_dir=output_dir,
        schema_reference=schema_reference,
        dependencies=dependencies,
    )
    processor.run()


@dataclass(slots=True)
class ProcessorDependencies:
    """Container for dependencies required by the data processor."""

    ipam: IPAMSimulator
    assets: AssetInventory
    rules_engine: RuleEngine | None = None


class DataProcessor:
    """Coordinate data ingestion, token resolution, and output generation."""

    def __init__(
        self,
        *,
        source_dir: Path,
        output_dir: Path,
        schema_reference: str,
        dependencies: ProcessorDependencies,
    ) -> None:
        """Store the configuration and dependency instances for processing."""
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.schema_reference = schema_reference
        self.ipam = dependencies.ipam
        self.assets = dependencies.assets
        self.rules_engine = dependencies.rules_engine or RuleEngine()

    def run(self) -> None:
        """Normalize every discovered JSON source file."""
        files = list(self._iter_source_files())
        if not files:
            logger.warning("No JSON files discovered under {}", self.source_dir)
            return

        session = self.rules_engine.create_session()
        pending_outputs: list[tuple[dict[str, Any], str, str]] = []

        for src_path in files:
            rel_site = src_path.parent.name
            processed = self._process_file(src_path, site=rel_site, session=session)
            pending_outputs.append((processed, rel_site, src_path.name))

        session.finalize()

        for processed, rel_site, filename in pending_outputs:
            self._write_output(processed, rel_site, filename)

        logger.info("Processed {} data file(s) into {}", len(files), self.output_dir)

    def _iter_source_files(self) -> Iterable[Path]:
        if not self.source_dir.exists():
            logger.error("Source directory {} does not exist", self.source_dir)
            return []

        for site_dir in sorted(p for p in self.source_dir.iterdir() if p.is_dir()):
            if site_dir.name == "schema":
                continue
            yield from sorted(site_dir.glob("*.json"))

    def _process_file(
        self,
        path: Path,
        *,
        site: str,
        session: "RuleEngineSession",
    ) -> dict[str, Any]:
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

        try:
            relative_source = path.relative_to(self.source_dir)
            display_path = str(self.source_dir / relative_source)
        except ValueError:
            display_path = str(path)

        session.apply(
            processed,
            site=site,
            source_path=path,
            display_path=display_path,
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
                message = IPAM_INTERFACE_REQUIRED_MESSAGE.format(candidate=candidate)
                raise ValueError(message)
            try:
                return self.ipam.lookup(
                    site=site, hostname=hostname, interface=interface, arguments=arguments
                )
            except IPAMLookupError as exc:
                message = IPAM_LOOKUP_FAILED_MESSAGE.format(
                    hostname=hostname, interface=interface, error=exc
                )
                raise ValueError(message) from exc

        if resolver == "asset":
            try:
                return self.assets.lookup(
                    site=site, hostname=hostname, arguments=arguments
                )
            except AssetLookupError as exc:
                message = ASSET_LOOKUP_FAILED_MESSAGE.format(
                    hostname=hostname, error=exc
                )
                raise ValueError(message) from exc

        message = UNSUPPORTED_RESOLVER_MESSAGE.format(
            resolver=resolver, candidate=candidate
        )
        raise ValueError(message)

    def _write_output(self, data: dict[str, Any], site: str, filename: str) -> None:
        target_dir = self.output_dir / site
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        logger.debug("Wrote {}", target)


if __name__ == "__main__":
    typer.run(main)
