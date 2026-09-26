from contextlib import contextmanager
from decimal import Decimal
from threading import RLock

AUTHORITATIVE_MANDATE_LIMITS = {
    "MANDATE-TREASURY-001": Decimal("1000000.00"),
}

class _MonotonicAuthorityState:
    __slots__ = ("__version",)

    def __init__(self, initial_version: int) -> None:
        object.__setattr__(self, "_MonotonicAuthorityState__version", initial_version)

    @property
    def version(self) -> int:
        return self.__version

    def advance(self) -> int:
        object.__setattr__(
            self,
            "_MonotonicAuthorityState__version",
            self.__version + 1,
        )
        return self.__version


_AUTHORITY_STATE = _MonotonicAuthorityState(1)
_AUTHORITY_STATE_LOCK = RLock()


def get_authoritative_mandate_limit(mandate_id: str) -> Decimal | None:
    return AUTHORITATIVE_MANDATE_LIMITS.get(mandate_id)


def get_authority_state_version() -> int:
    with _AUTHORITY_STATE_LOCK:
        return _AUTHORITY_STATE.version


@contextmanager
def authority_state_guard():
    with _AUTHORITY_STATE_LOCK:
        yield


def get_authority_state_version_unlocked() -> int:
    return _AUTHORITY_STATE.version


def advance_authority_state_version() -> int:
    with _AUTHORITY_STATE_LOCK:
        return _AUTHORITY_STATE.advance()
