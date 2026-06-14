"""Pure, GUI-free helpers for persisting and migrating CopyTool settings.

The job cards are stored as a single JSON string under ``cards_json`` (see
``CARDS_KEY``). Encoding the whole list as one string sidesteps the native
``QSettings`` backend quirks that previously crashed the app on startup:

* an empty Python ``list`` is read back as ``None``
* a single-element ``list`` is read back as the bare element

Both are handled by :func:`normalize_legacy_cards` when migrating data written
by versions prior to ``SETTINGS_VERSION`` 1.

This module intentionally imports nothing from Qt so it can be unit-tested
without a display or PySide6 installed.
"""

import json
from typing import List, Optional, Sequence, Tuple

#: Current on-disk settings schema version.
SETTINGS_VERSION = 1

#: New-format keys.
CARDS_KEY = 'cards_json'
VERSION_KEY = 'settings_version'

#: Legacy keys migrated (and removed) on first load of a new version.
LEGACY_CARDS_KEY = 'cards'
LEGACY_SOURCE_KEY = 'source'
LEGACY_TARGET_KEY = 'target'

Card = Tuple[str, str]


def _coerce_pair(item) -> Optional[Card]:
    """Return ``(src, tgt)`` if ``item`` is a 2-element pair of strings."""
    if isinstance(item, (list, tuple)) and len(item) == 2 \
            and all(isinstance(x, str) for x in item):
        return item[0], item[1]
    return None


def _coerce_card_list(data) -> List[Card]:
    """Coerce a list of pairs into a clean ``list[(src, tgt)]``.

    Entries that are not 2-string pairs are dropped rather than raising, so a
    partially corrupt store degrades gracefully instead of crashing.
    """
    if not isinstance(data, (list, tuple)):
        return []
    cards = []
    for item in data:
        pair = _coerce_pair(item)
        if pair is not None:
            cards.append(pair)
    return cards


def serialize_cards(cards: Sequence[Sequence[str]]) -> str:
    """Encode an iterable of ``(src, tgt)`` pairs as a JSON string."""
    normalized = [[str(src), str(tgt)] for src, tgt in cards]
    return json.dumps(normalized)


def deserialize_cards(raw) -> List[Card]:
    """Decode the ``cards_json`` value into ``list[(src, tgt)]``.

    Returns ``[]`` for empty input or anything that is not valid JSON encoding
    a list of pairs. Never raises.
    """
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return _coerce_card_list(data)


def normalize_legacy_cards(value) -> List[Card]:
    """Convert a legacy ``cards`` QSettings value into ``list[(src, tgt)]``.

    Handles the native-backend quirks:

    * ``None`` (empty list written by an old version) -> ``[]``
    * a bare ``['src', 'tgt']`` pair (single-element list collapsed by the
      backend) -> ``[('src', 'tgt')]``
    * a normal list of ``[src, tgt]`` pairs / tuples -> coerced as-is
    """
    if value is None:
        return []
    # Single-card collapse: a bare 2-element pair of strings. A genuine
    # multi-card list has list/tuple elements, not strings, so this is
    # unambiguous.
    pair = _coerce_pair(value)
    if pair is not None:
        return [pair]
    return _coerce_card_list(value)


def build_migrated_cards(legacy_cards_value,
                         legacy_source: Optional[str],
                         legacy_target: Optional[str]) -> List[Card]:
    """Build the migrated card list from all legacy keys.

    Preserves the original load order: a card synthesized from the legacy
    single ``source``/``target`` keys comes first, followed by the legacy
    ``cards`` list.
    """
    cards: List[Card] = []
    if legacy_source is not None or legacy_target is not None:
        cards.append((legacy_source or '', legacy_target or ''))
    cards.extend(normalize_legacy_cards(legacy_cards_value))
    return cards
