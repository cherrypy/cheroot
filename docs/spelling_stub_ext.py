"""Sphinx extension for making the spelling directive noop."""

from __future__ import annotations

from sphinx.application import Sphinx
from sphinx.config import Config as _SphinxConfig
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective
from sphinx.util.nodes import nodes

from cheroot import __version__


try:
    from enchant.tokenize import (
        Filter as _EnchantTokenizeFilterBase,
    )
except ImportError:
    _EnchantTokenizeFilterBase = object


logger = logging.getLogger(__name__)


def _configure_spelling_ext(app: Sphinx, config: _SphinxConfig) -> None:
    class VersionFilter(_EnchantTokenizeFilterBase):  # noqa: WPS431
        # NOTE: It's nested because we need to reference the config by closure.
        """Filter for treating version words as known."""

        def _skip(self, word: str) -> bool:
            # NOTE: Only accessing the config values in the method since they
            # NOTE: aren't yet populated when the config-inited event happens.
            known_version_words = {
                config.release,
                config.version,
                __version__,
            }
            if word not in known_version_words:
                return False

            logger.debug(
                'Known version words: %r',
                known_version_words,
            )
            logger.debug(
                'Ignoring %r because it is a known version',
                word,
            )

            return True

    # Resetting the release and version strings works around problems
    # with `setuptools-scm` generated versions being tokenized
    # by the spell checker incorrectly.
    app.config.release = 'dummy'
    app.config.version = 'dummy'

    app.config.spelling_filters = [VersionFilter]
    app.setup_extension('sphinxcontrib.spelling')

    # suppress unpicklable value warnings:
    del app.config.spelling_filters  # noqa: WPS420


class SpellingNoOpDirective(SphinxDirective):
    """Definition of the stub spelling directive."""

    has_content = True

    def run(self) -> list[nodes.Node]:
        """Generate nothing in place of the directive."""
        return []


def setup(app: Sphinx) -> None:
    """Initialize the extension."""
    if _EnchantTokenizeFilterBase is object:
        app.add_directive('spelling', SpellingNoOpDirective)
    else:
        app.connect('config-inited', _configure_spelling_ext)

    return {
        'parallel_read_safe': True,
        'version': __version__,
    }
