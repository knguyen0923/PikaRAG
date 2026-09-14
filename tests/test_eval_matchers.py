import pytest

from eval.matchers import matches


def test_exact_match_is_case_insensitive():
    assert matches("Yes, Kommo-o learns Close Combat.", "yes", "exact") is True


def test_exact_match_requires_a_whole_word_not_a_bare_substring():
    # "no" is a substring of "known" -- a naive `in` check would false-positive.
    # word-boundary matching must not.
    assert matches("Kommo-o's known moves include Close Combat.", "no", "exact") is False


def test_exact_match_finds_the_word_when_genuinely_present():
    assert matches("No, Kommo-o cannot learn Tackle.", "no", "exact") is True


def test_set_match_requires_every_item_present():
    answer = "Kommo-o's base stats: HP 75, Attack 110, Defense 125."
    assert matches(answer, ["HP 75", "Attack 110", "Defense 125"], "set") is True


def test_set_match_fails_when_one_item_missing():
    answer = "Kommo-o's base stats: HP 75, Attack 110."
    assert matches(answer, ["HP 75", "Attack 110", "Defense 125"], "set") is False


def test_set_match_is_case_insensitive():
    answer = "abilities: bulletproof, overcoat"
    assert matches(answer, ["Bulletproof", "Overcoat"], "set") is True


def test_substring_match_finds_a_paraphrased_key_phrase():
    answer = "Life Orb boosts move power by 30 percent but you take recoil damage."
    assert matches(answer, "Boosts move power by 30%", "substring") is False  # exact text not present
    assert matches(answer, "boosts move power by 30", "substring") is True


def test_substring_match_is_case_insensitive():
    assert matches("LIFE ORB DESCRIPTION", "life orb description", "substring") is True


def test_unknown_match_type_raises():
    with pytest.raises(ValueError):
        matches("anything", "anything", "not-a-real-type")
