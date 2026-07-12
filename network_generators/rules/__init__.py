"""Author custom data rules for network generators in this module.

Populate ``DATA_RULES`` or decorate callables with ``@rule`` to have them
applied automatically during data normalization. See ``RuleContext`` for the
values exposed to each rule.
"""

from __future__ import annotations

from network_generators.services.rules import Rule, RuleContext, rule

__all__ = ["DATA_RULES", "Rule", "RuleContext", "register", "rule"]

DATA_RULES: list[Rule] = []


def register(rule_callable: Rule) -> Rule:
    """Register a rule callable for execution."""
    DATA_RULES.append(rule_callable)
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
