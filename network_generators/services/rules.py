"""Infrastructure for applying user-defined data normalization rules."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

from loguru import logger

__all__ = ["Rule", "RuleContext", "RuleEngine", "rule"]

DEFAULT_RULES_MODULE = "network_generators.rules"

Rule = Callable[["RuleContext"], None]

INVALID_RULE_MESSAGE = "Rule {candidate!r} is not callable"


@dataclass(slots=True)
class RuleContext:
    """Execution context provided to rule callables."""

    device: dict[str, Any]
    site: str
    source_path: Path

    @property
    def hostname(self) -> str:
        """Return the hostname from the device data if present."""
        value = self.device.get("hostname")
        return value if isinstance(value, str) else ""


class RuleEngine:
    """Load and execute user supplied rules for device normalization."""

    def __init__(
        self,
        *,
        module_name: str = DEFAULT_RULES_MODULE,
        rules: Iterable[Rule] | None = None,
    ) -> None:
        """Initialize the rule engine either from callables or a module."""
        self.module_name = module_name
        if rules is not None:
            self.rules = _validate_rules(rules)
            self._loaded_from_module = False
        else:
            self.rules = self._load_from_module(module_name)
            self._loaded_from_module = True

    def apply(self, device: dict[str, Any], *, site: str, source_path: Path) -> None:
        """Execute every discovered rule against the provided device."""
        if not self.rules:
            return

        context = RuleContext(device=device, site=site, source_path=source_path)
        for rule_callable in self.rules:
            rule_callable(context)

    def _load_from_module(self, module_name: str) -> tuple[Rule, ...]:
        """Attempt to import rules from the configured module."""
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            logger.debug("Rules module %s not found; skipping rule application", module_name)
            return ()
        except Exception as exc:  # pragma: no cover - defensive
            msg = f"Failed to import rules module {module_name!r}"
            raise RuntimeError(msg) from exc

        rules = _discover_rules(module)
        if rules:
            logger.debug("Loaded %s rule(s) from %s", len(rules), module_name)
        else:
            logger.debug("No rules discovered in %s", module_name)
        return rules


def rule(func: Rule) -> Rule:
    """Mark a callable as a rule."""
    func.__network_rule__ = True
    return func


def _discover_rules(module: ModuleType) -> tuple[Rule, ...]:
    """Inspect a module and collect candidate rule callables."""
    explicit_attrs = ("DATA_RULES", "RULES")
    for attr_name in explicit_attrs:
        payload = getattr(module, attr_name, None)
        if payload is not None:
            return _validate_rules(payload)

    callable_attrs = ("get_rules", "rules")
    for attr_name in callable_attrs:
        candidate = getattr(module, attr_name, None)
        if callable(candidate):
            return _validate_rules(candidate())

    decorated = [
        _ensure_rule(value)
        for value in module.__dict__.values()
        if getattr(value, "__network_rule__", False)
    ]
    if decorated:
        return tuple(decorated)

    return ()


def _validate_rules(candidate: Iterable[Any]) -> tuple[Rule, ...]:
    """Ensure the candidate iterable only contains callable rules."""
    return tuple(_ensure_rule(item) for item in candidate)


def _ensure_rule(candidate: Any) -> Rule:
    """Validate an individual rule candidate."""
    if not callable(candidate):
        message = INVALID_RULE_MESSAGE.format(candidate=candidate)
        raise TypeError(message)
    return candidate
