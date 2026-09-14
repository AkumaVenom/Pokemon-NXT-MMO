"""Backward-compatible optional [console] policy; no configuration writes."""
from dataclasses import dataclass
from .admin_registry import BY_NAME, canonical

@dataclass(frozen=True)
class ConsolePolicy:
    enabled: bool = True
    allow_developer_commands: bool = False
    disabled_commands: frozenset = frozenset()
    confirmation_seconds: int = 60

    @classmethod
    def load(cls, config):
        enabled = config.getboolean('console', 'enabled', fallback=True)
        dev = config.getboolean('console', 'allow_developer_commands', fallback=False)
        seconds = config.getint('console', 'confirmation_seconds', fallback=60)
        if not 15 <= seconds <= 300:
            raise ValueError('console.confirmation_seconds must be 15..300')
        raw = config.get('console', 'disabled_commands', fallback='')
        disabled = frozenset(canonical(s.strip()) for s in raw.split(',') if s.strip())
        if disabled - set(BY_NAME):
            raise ValueError('console.disabled_commands contains an unknown command')
        if disabled & {'help', 'confirm', 'cancel', 'cancelshutdown'}:
            raise ValueError('Console help and cancellation controls cannot be disabled individually')
        if config.has_section('console') and set(config.options('console')) - {'enabled','allow_developer_commands','disabled_commands','confirmation_seconds'}:
            raise ValueError('Unknown [console] option')
        return cls(enabled, dev, disabled, seconds)

    def allows(self, command):
        return self.enabled and command.name not in self.disabled_commands and (not command.developer or self.allow_developer_commands)
