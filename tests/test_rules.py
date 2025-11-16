"""Tests covering the custom rule execution engine used during data generation."""

from __future__ import annotations

import importlib
import json
import sys
from typing import TYPE_CHECKING

import pytest

from network_generators.generators.data import (
    DataProcessor,
    ProcessorDependencies,
)
from network_generators.services.asset import get_demo_asset_inventory
from network_generators.services.ipam import get_demo_ipam
from network_generators.services.rules import (
    RuleContext,
    RuleEngine,
    RuleViolationError,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_rule_engine_applies_rules(tmp_path: Path) -> None:
    """Ensure manually supplied rules mutate device data."""
    def sample_rule(ctx: RuleContext) -> None:
        if ctx.hostname == "wgw01.sfo01" and ctx.site == "sfo01":
            ctx.device["domain"] = f"{ctx.site}.example.com"
            ctx.device["matches"] = []

    engine = RuleEngine(rules=[sample_rule])
    device = {
        "hostname": "wgw01.sfo01",
        "domain": "example.com",
        "matches": ["foo"],
        "vendor": "juniper",
    }

    engine.apply(device, site="sfo01", source_path=tmp_path / "device.json")

    assert device["domain"] == "sfo01.example.com"
    assert device["matches"] == []


def test_default_rules_module_examples(tmp_path: Path) -> None:
    """Validate the built-in example rules."""
    engine = RuleEngine()
    juniper_device = {
        "hostname": "wgw99.sfo01",
        "domain": "example.com",
        "vendor": "juniper",
    }
    engine.apply(juniper_device, site="sfo01", source_path=tmp_path / "device.json")
    assert juniper_device["domain"] == "sfo01.example.com"

    nyc_gateway = {
        "hostname": "wgw01.nyc01",
        "matches": ["system|>>|"],
    }
    engine.apply(nyc_gateway, site="nyc01", source_path=tmp_path / "nyc.json")
    assert nyc_gateway["matches"] == []


def test_data_processor_applies_rules(tmp_path: Path) -> None:
    """Apply rules through the standard processor entrypoint."""
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    site_dir = source_dir / "sfo01"
    site_dir.mkdir(parents=True)

    device_payload = {
        "hostname": "wgw01.sfo01",
        "domain": "example.com",
        "role": "wan-gateway",
        "vendor": "juniper",
        "os": "junos",
        "serial_number": "FTX0000",
        "tags": [],
        "timezone": "UTC",
        "interfaces": {
            "ge-0/0/0": {"ipv4": "10.0.0.1/24"},
        },
        "matches": ["system|>>|"],
    }
    (site_dir / "device.json").write_text(json.dumps(device_payload))

    def sample_rule(ctx: RuleContext) -> None:
        if ctx.site == "sfo01" and ctx.device.get("vendor") == "juniper":
            ctx.device["domain"] = f"{ctx.site}.example.com"
        if ctx.hostname == "wgw01.sfo01":
            ctx.device["matches"] = []

    dependencies = ProcessorDependencies(
        ipam=get_demo_ipam(),
        assets=get_demo_asset_inventory(),
        rules_engine=RuleEngine(rules=[sample_rule]),
    )

    processor = DataProcessor(
        source_dir=source_dir,
        output_dir=output_dir,
        schema_reference="schema.json",
        dependencies=dependencies,
    )

    processor.run()

    rendered = json.loads((output_dir / "sfo01" / "device.json").read_text())
    assert rendered["domain"] == "sfo01.example.com"
    assert rendered["matches"] == []
    assert rendered["$schema"] == "schema.json"


def test_rule_engine_discovers_decorated_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirm rule discovery works with decorated module functions."""
    package_root = tmp_path / "custom_rules"
    package_root.mkdir()
    rules_file = package_root / "__init__.py"
    rules_file.write_text(
        "from network_generators.services.rules import rule\n\n"
        "@rule\n"
        "def adjust(ctx):\n"
        "    if ctx.site == 'nyc01':\n"
        "        ctx.device['domain'] = 'nyc01.example.com'\n"
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        importlib.invalidate_caches()
        engine = RuleEngine(module_name="custom_rules")
        device = {
            "hostname": "wgw01.nyc01",
            "domain": "example.com",
        }
        engine.apply(device, site="nyc01", source_path=tmp_path / "device.json")
        assert device["domain"] == "nyc01.example.com"
    finally:
        sys.modules.pop("custom_rules", None)


def test_fleet_rule_detects_duplicate_ipv4(tmp_path: Path) -> None:
    """Ensure the built-in fleet rule flags duplicate IPv4 assignments."""
    engine = RuleEngine()
    session = engine.create_session()

    device_one = {
        "hostname": "wgw01.nyc01",
        "interfaces": {
            "ge-0/0/0": {"ipv4": "10.2.0.1/24"},
        },
    }
    device_two = {
        "hostname": "wgw02.nyc01",
        "interfaces": {
            "ge-0/0/0": {"ipv4": "10.2.0.1/24"},
        },
    }

    src_one = tmp_path / "data" / "nyc01" / "wgw01.json"
    src_two = tmp_path / "data" / "nyc01" / "wgw02.json"
    src_one.parent.mkdir(parents=True, exist_ok=True)
    src_two.parent.mkdir(parents=True, exist_ok=True)
    src_one.write_text(json.dumps(device_one))
    src_two.write_text(json.dumps(device_two))

    session.apply(
        device_one,
        site="nyc01",
        source_path=src_one,
        display_path="data/nyc01/wgw01.json",
    )
    session.apply(
        device_two,
        site="nyc01",
        source_path=src_two,
        display_path="data/nyc01/wgw02.json",
    )

    with pytest.raises(RuleViolationError) as excinfo:
        session.finalize()

    message = str(excinfo.value)
    assert "Duplicate IPv4 addresses detected" in message
    assert "data/nyc01/wgw01.json::ge-0/0/0" in message
