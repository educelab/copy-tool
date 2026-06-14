"""Unit tests for copy_tool.persistence — pure, no Qt required.

Covers the cards (de)serialization and the legacy-settings migration against
all the known native-QSettings poison shapes that crashed startup before 1.3.0.
"""

from copy_tool import persistence as p


# --- serialize / deserialize round-trip --------------------------------------

def test_round_trip_multiple_cards():
    cards = [('/src/a', '/tgt/a'), ('/src/b', '/tgt/b')]
    assert p.deserialize_cards(p.serialize_cards(cards)) == cards


def test_round_trip_single_card():
    cards = [('/src', '/tgt')]
    assert p.deserialize_cards(p.serialize_cards(cards)) == cards


def test_round_trip_empty_list():
    # The whole point: an empty list survives as the string "[]", not None.
    assert p.serialize_cards([]) == '[]'
    assert p.deserialize_cards('[]') == []


def test_serialize_coerces_to_strings_and_lists():
    assert p.serialize_cards([('a', 'b')]) == '[["a", "b"]]'


# --- deserialize robustness ---------------------------------------------------

def test_deserialize_none_and_empty_string():
    assert p.deserialize_cards(None) == []
    assert p.deserialize_cards('') == []


def test_deserialize_invalid_json():
    assert p.deserialize_cards('not json {') == []


def test_deserialize_non_list_json():
    assert p.deserialize_cards('{"a": 1}') == []
    assert p.deserialize_cards('"just a string"') == []


def test_deserialize_drops_malformed_entries():
    raw = '[["a", "b"], "junk", ["c"], ["d", "e", "f"], ["g", "h"]]'
    assert p.deserialize_cards(raw) == [('a', 'b'), ('g', 'h')]


# --- legacy normalization (the native-backend quirks) -------------------------

def test_normalize_legacy_none_is_empty():
    # Old empty list read back as None by the native backend.
    assert p.normalize_legacy_cards(None) == []


def test_normalize_legacy_single_card_collapse():
    # Old single-element list read back as the bare pair of strings.
    assert p.normalize_legacy_cards(['/src', '/tgt']) == [('/src', '/tgt')]
    assert p.normalize_legacy_cards(('/src', '/tgt')) == [('/src', '/tgt')]


def test_normalize_legacy_multiple_cards():
    value = [['/s1', '/t1'], ['/s2', '/t2']]
    assert p.normalize_legacy_cards(value) == [('/s1', '/t1'), ('/s2', '/t2')]


def test_normalize_legacy_single_card_not_collapsed():
    # Some backends keep the wrapping list for one card.
    assert p.normalize_legacy_cards([['/src', '/tgt']]) == [('/src', '/tgt')]


def test_normalize_legacy_garbage():
    assert p.normalize_legacy_cards('garbage') == []
    assert p.normalize_legacy_cards(42) == []


# --- full migration -----------------------------------------------------------

def test_migrate_cards_only():
    legacy = [['/s1', '/t1'], ['/s2', '/t2']]
    assert p.build_migrated_cards(legacy, None, None) == [
        ('/s1', '/t1'), ('/s2', '/t2')]


def test_migrate_source_target_only():
    assert p.build_migrated_cards(None, '/src', '/tgt') == [('/src', '/tgt')]


def test_migrate_source_target_precede_cards():
    # The synthesized source/target card comes first, then the cards list.
    legacy = [['/s1', '/t1']]
    assert p.build_migrated_cards(legacy, '/old_src', '/old_tgt') == [
        ('/old_src', '/old_tgt'), ('/s1', '/t1')]


def test_migrate_partial_source_only():
    assert p.build_migrated_cards(None, '/src', None) == [('/src', '')]


def test_migrate_collapsed_single_legacy_card():
    # Worst case: a single legacy card collapsed to a bare pair, plus a
    # leftover source/target. Both recovered, in order.
    assert p.build_migrated_cards(['/s', '/t'], '/old', '') == [
        ('/old', ''), ('/s', '/t')]
