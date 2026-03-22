"""
Filer registry -- maps filing_code strings to state filer classes.

Usage:
    from openclerc.filers import register_filer, get_filer_for_code

    register_filer("ca_soi", CaliforniaSOIFiler)
    filer = get_filer_for_code("ca_soi")
"""
import logging
from typing import Optional, Type

from openclerc.core.base_filer import BaseStateFiler

logger = logging.getLogger("openclerc")

_FILER_REGISTRY: dict[str, Type[BaseStateFiler]] = {}


def register_filer(filing_code: str, filer_class: Type[BaseStateFiler]):
    """Register a filer class for a filing code."""
    if filing_code in _FILER_REGISTRY:
        logger.warning(
            f"Overwriting filer for {filing_code}: "
            f"{_FILER_REGISTRY[filing_code].__name__} -> {filer_class.__name__}"
        )
    _FILER_REGISTRY[filing_code] = filer_class
    logger.info(f"Registered filer: {filing_code} -> {filer_class.__name__}")


def get_filer_for_code(filing_code: str) -> Optional[BaseStateFiler]:
    """Get an instance of the filer for the given filing code."""
    filer_class = _FILER_REGISTRY.get(filing_code)
    if filer_class is None:
        logger.warning(f"No filer registered for filing_code: {filing_code}")
        return None
    return filer_class()


def list_registered_filers() -> dict[str, str]:
    """Return a dict of {filing_code: filer_class_name}."""
    return {code: cls.__name__ for code, cls in _FILER_REGISTRY.items()}


# Auto-import filers to trigger registration
from openclerc.filers import dummy_filer  # noqa: F401, E402
from openclerc.filers import california_soi  # noqa: F401, E402
from openclerc.filers import delaware_franchise_tax  # noqa: F401, E402
from openclerc.filers import sf_business_reg  # noqa: F401, E402
