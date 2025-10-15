"""Infrastructure for applying user-defined data normalization rules."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

from loguru import logger

__all__ = [
    "FleetContext",
    "FleetRule",
    "Rule",
    "RuleContext",
    "RuleEngine",
    "RuleViolationError",
    "fleet_rule",
    "rule",
]

DEFAULT_RULES_MODULE = "network_generators.rules"

Rule = Callable[["RuleContext"], None]
FleetRule = Callable[["FleetContext"], None]

INVALID_RULE_MESSAGE = "Rule {candidate!r} is not callable"
INVALID_FLEET_RULE_MESSAGE = "Fleet rule {candidate!r} is not callable"


@dataclass(slots=True)
class RuleContext:
    """Execution context provided to rule callables."""

    device: dict[str, Any]
    site: str
    source_path: Path
    _record_issue: Callable[[str], None] | None = field(default=None, repr=False)

    @property
    def hostname(self) -> str:
        """Return the hostname from the device data if present."""
        value = self.device.get("hostname")
        return value if isinstance(value, str) else ""

    def report_issue(self, message: str) -> None:
        """Record an issue to be surfaced after all rules run."""
        if self._record_issue is None:
            raise RuntimeError("Issue reporting is not enabled for this context")
        self._record_issue(message)


@dataclass(slots=True)
class DeviceRecord:
    """Snapshot of a processed device for fleet-wide validation."""

    device: dict[str, Any]
    site: str
    source_path: Path
    display_path: str

    @property
    def hostname(self) -> str:
        value = self.device.get("hostname")
        return value if isinstance(value, str) and value else self.source_path.stem


@dataclass(slots=True)
class FleetContext:
    """Context provided to fleet-wide validation rules."""

    devices: tuple[DeviceRecord, ...]
    _record_issue: Callable[[str], None] = field(repr=False)

    def report_issue(self, message: str) -> None:
        """Record a validation error message."""
        self._record_issue(message)


class RuleViolationError(RuntimeError):
    """Raised when rule execution detects validation issues."""

    def __init__(self, issues: Iterable[str]) -> None:
        self.issues = tuple(issues)
        message = "\n\n".join(self.issues)
        super().__init__(message)


class RuleEngine:
    """Load and execute user supplied rules for device normalization."""

    def __init__(
        self,
        *,
        module_name: str = DEFAULT_RULES_MODULE,
        rules: Iterable[Rule] | None = None,
        fleet_rules: Iterable[FleetRule] | None = None,
    ) -> None:
        """Initialize the rule engine either from callables or a module."""
        self.module_name = module_name
        if rules is not None:
            self.rules = _validate_rules(rules)
            self.fleet_rules = _validate_fleet_rules(fleet_rules or ())
            self._loaded_from_module = False
        else:
            device_rules, module_fleet_rules = self._load_from_module(module_name)
            self.rules = device_rules
            if fleet_rules is not None:
                self.fleet_rules = _validate_fleet_rules(fleet_rules)
            else:
                self.fleet_rules = module_fleet_rules
            self._loaded_from_module = True

    def create_session(self) -> "RuleEngineSession":
        """Return a session for applying rules across multiple devices."""
        return RuleEngineSession(self.rules, self.fleet_rules)

    def apply(self, device: dict[str, Any], *, site: str, source_path: Path) -> None:
        """Execute every discovered rule against the provided device."""
        session = self.create_session()
        session.apply(device, site=site, source_path=source_path)
        session.finalize()

    def _load_from_module(
        self, module_name: str
    ) -> tuple[tuple[Rule, ...], tuple[FleetRule, ...]]:
        """Attempt to import rules from the configured module."""
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            logger.debug("Rules module %s not found; skipping rule application", module_name)
            return (), ()
        except Exception as exc:  # pragma: no cover - defensive
            msg = f"Failed to import rules module {module_name!r}"
            raise RuntimeError(msg) from exc

        device_rules = _discover_device_rules(module)
        fleet_rules = _discover_fleet_rules(module)

        if device_rules or fleet_rules:
            logger.debug(
                "Loaded %s device rule(s) and %s fleet rule(s) from %s",
                len(device_rules),
                len(fleet_rules),
                module_name,
            )
        else:
            logger.debug("No rules discovered in %s", module_name)

        return device_rules, fleet_rules


def rule(func: Rule) -> Rule:
    """Mark a callable as a rule."""
    func.__network_rule__ = True
    return func


def fleet_rule(func: FleetRule) -> FleetRule:
    """Mark a callable as a fleet-wide rule."""
    func.__network_fleet_rule__ = True
    return func


class RuleEngineSession:
    """Coordinate device rule application and fleet-wide validations."""

    def __init__(
        self,
        rules: tuple[Rule, ...],
        fleet_rules: tuple[FleetRule, ...],
    ) -> None:
        self._rules = rules
        self._fleet_rules = fleet_rules
        self._issues: list[str] = []
        self._devices: list[DeviceRecord] = []

    def apply(
        self,
        device: dict[str, Any],
        *,
        site: str,
        source_path: Path,
        display_path: str | None = None,
    ) -> None:
        """Apply per-device rules and record the device for fleet checks."""
        if not self._rules and not self._fleet_rules:
            return

        display = display_path or str(source_path)
        context = RuleContext(
            device=device,
            site=site,
            source_path=source_path,
            _record_issue=self._issues.append,
        )
        for rule_callable in self._rules:
            rule_callable(context)

        self._devices.append(
            DeviceRecord(
                device=device,
                site=site,
                source_path=source_path,
                display_path=display,
            )
        )

    def finalize(self) -> None:
        """Execute fleet-wide rules and raise if any issues are detected."""
        if not self._fleet_rules and not self._issues:
            return

        if self._fleet_rules:
            context = FleetContext(
                devices=tuple(self._devices),
                _record_issue=self._issues.append,
            )
            for fleet_rule_callable in self._fleet_rules:
                fleet_rule_callable(context)

        if self._issues:
            raise RuleViolationError(self._issues)


def _discover_device_rules(module: ModuleType) -> tuple[Rule, ...]:
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


def _discover_fleet_rules(module: ModuleType) -> tuple[FleetRule, ...]:
    """Inspect a module and collect fleet-wide rule callables."""
    explicit_attrs = ("FLEET_RULES",)
    for attr_name in explicit_attrs:
        payload = getattr(module, attr_name, None)
        if payload is not None:
            return _validate_fleet_rules(payload)

    callable_attrs = ("get_fleet_rules", "fleet_rules")
    for attr_name in callable_attrs:
        candidate = getattr(module, attr_name, None)
        if callable(candidate):
            return _validate_fleet_rules(candidate())

    decorated = [
        _ensure_fleet_rule(value)
        for value in module.__dict__.values()
        if getattr(value, "__network_fleet_rule__", False)
    ]
    if decorated:
        return tuple(decorated)

    return ()


def _validate_rules(candidate: Iterable[Any]) -> tuple[Rule, ...]:
    """Ensure the candidate iterable only contains callable rules."""
    return tuple(_ensure_rule(item) for item in candidate)


def _validate_fleet_rules(candidate: Iterable[Any]) -> tuple[FleetRule, ...]:
    """Ensure the candidate iterable only contains callable fleet rules."""
    return tuple(_ensure_fleet_rule(item) for item in candidate)


def _ensure_rule(candidate: Any) -> Rule:
    """Validate an individual rule candidate."""
    if not callable(candidate):
        message = INVALID_RULE_MESSAGE.format(candidate=candidate)
        raise TypeError(message)
    return candidate


def _ensure_fleet_rule(candidate: Any) -> FleetRule:
    """Validate an individual fleet rule candidate."""
    if not callable(candidate):
        message = INVALID_FLEET_RULE_MESSAGE.format(candidate=candidate)
        raise TypeError(message)
    return candidate
