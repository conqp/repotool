"""Logging facility."""

from logging import getLogger


__all__ = ['LOG_FORMAT', 'LOGGER']


LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
LOGGER = getLogger(__file__)
