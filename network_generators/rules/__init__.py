"""Author custom data rules for network generators in this module.

Populate ``DATA_RULES``/``FLEET_RULES`` or decorate callables with ``@rule``
and ``@fleet_rule`` to have them applied automatically during data
normalization. See ``RuleContext`` and ``FleetContext`` for values exposed to
each rule.
"""

from __future__ import annotations

from collections import defaultdict
from ipaddress import ip_interface

from network_generators.services.rules import (
    FleetContext,
    FleetRule,
    Rule,
    RuleContext,
    fleet_rule,
    rule,
)

__all__ = [
    "DATA_RULES",
    "FLEET_RULES",
    "FleetContext",
    "FleetRule",
    "Rule",
    "RuleContext",
    "register",
    "register_fleet",
    "rule",
    "fleet_rule",
]

DATA_RULES: list[Rule] = []
FLEET_RULES: list[FleetRule] = []


def register(rule_callable: Rule) -> Rule:
    """Register a rule callable for execution."""
    DATA_RULES.append(rule_callable)
    return rule_callable


def register_fleet(rule_callable: FleetRule) -> FleetRule:
    """Register a fleet-wide rule callable for execution."""
    FLEET_RULES.append(rule_callable)
    return rule_callable


@register
@rule
def assign_site_domains(context: RuleContext) -> None:
    """Set Juniper device domains to include the site slug."""
    device = context.device
    if device.get("vendor") != "juniper":
        return
    current = device.get("domain")
    desired = f"{context.site}.example.com"
    if isinstance(current, str) and current != desired:
        device["domain"] = desired


@register
@rule
def suppress_matches_for_wgw01(context: RuleContext) -> None:
    """Clear matches for the NYC01 primary WAN gateway."""
    if context.hostname == "wgw01.nyc01":
        context.device["matches"] = []


@register_fleet
@fleet_rule
def ensure_unique_ipv4_allocations(context: FleetContext) -> None:
    """Detect duplicate IPv4 assignments or malformed addresses."""
    assignments: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []

    for record in context.devices:
        interfaces = record.device.get("interfaces")
        if not isinstance(interfaces, dict):
            continue

        for iface_name, iface_data in interfaces.items():
            if not isinstance(iface_data, dict):
                continue

            raw = iface_data.get("ipv4")
            if not raw:
                continue

            try:
                parsed = ip_interface(str(raw))
            except ValueError as exc:
                errors.append(
                    f"{record.display_path}: interface {iface_name} has invalid IPv4 '{raw}': {exc}"
                )
                continue

            if parsed.version != 4:
                errors.append(
                    f"{record.display_path}: interface {iface_name} has non-IPv4 address '{raw}'"
                )
                continue

            key = parsed.ip.exploded
            source = (
                f"{record.display_path}::{iface_name} "
                f"({record.hostname}, {parsed.with_prefixlen})"
            )
            assignments[key].append(source)

    if errors:
        context.report_issue("\n".join(errors))

    duplicates = {
        ip: entries for ip, entries in assignments.items() if len(entries) > 1
    }

    if duplicates:
        lines = ["Duplicate IPv4 addresses detected:"]
        for ip, entries in sorted(duplicates.items()):
            lines.append(f"  {ip}")
            for entry in entries:
                lines.append(f"    {entry}")
        context.report_issue("\n".join(lines))
