from backend.mapping import slots_to_targets_and_genres
from backend.vibe_schema import VibeSlots


def test_slots_to_targets_and_genres_bounds():
    slots = VibeSlots(
        mood="romantic",
        activity="dinner",
        time_of_day="sunset",
        place="Paris",
        era=None,
        intensity=4,
        style_hints=["jazz", "chanson"],
        language_or_locale="fr",
        confidence=0.9,
    )

    targets, seeds = slots_to_targets_and_genres(slots)

    assert 3 <= len(seeds) <= 5
    assert len(set(seeds)) == len(seeds)

    for key, value in targets.items():
        if key == "target_tempo":
            assert 50.0 <= value <= 160.0
        else:
            assert 0.0 <= value <= 1.0
