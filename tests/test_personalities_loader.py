import pytest

from backend.personalities import list_personality_ids, load_personality
from backend.personalities.loader import _merge_animation_vibe, _mouth_pools
from backend.rendering.animation_config import build_eye_config
from backend.rendering.avatar_config import ASSETS_DIR, default_face_layout_ratios


def test_list_personality_ids_includes_builtins():
    ids = list_personality_ids()
    assert "peter" in ids
    assert "ted" in ids
    assert "emma" in ids
    assert "trevor" in ids


def test_load_peter_uses_default_face_layout():
    p = load_personality("Peter")
    assert p.face_layout == default_face_layout_ratios()


def test_load_emma_and_trevor_have_face_layout_overrides():
    base = default_face_layout_ratios()
    emma = load_personality("emma")
    assert emma.face_layout.eye_y_ratio > base.eye_y_ratio
    assert emma.face_layout.eye_width_ratio < base.eye_width_ratio
    trevor = load_personality("trevor")
    assert trevor.face_layout.eye_y_ratio > base.eye_y_ratio
    assert trevor.face_layout.eye_width_ratio < base.eye_width_ratio


def test_load_peter():
    p = load_personality("Peter")
    assert p.id == "peter"
    assert p.display_name == "Peter"
    assert "Peter" in p.llm_system_prompt or "peter" in p.llm_system_prompt.lower()
    assert p.azure_voice_name
    assert p.emotes
    face_path = (p.assets.face_root / p.assets.face_filename).resolve()
    try:
        face_path.relative_to(ASSETS_DIR.resolve())
    except ValueError:
        pytest.fail("personality face path must live under ASSETS_DIR")
    assert face_path.is_file()
    assert p.assets.sprites_root == ASSETS_DIR


def test_load_ted_has_no_emotes():
    p = load_personality("ted")
    assert p.emotes == ()
    assert not p.emote_timing.enabled
    assert p.mouth_idle_enabled is False
    assert not any(
        (p.idle_mouth_pools.subtle, p.idle_mouth_pools.happy, p.idle_mouth_pools.goofy, p.idle_mouth_pools.dramatic)
    )
    assert p.eye_config.enable_goofy_sequences is False
    assert p.eye_config.enable_expr_glance is False
    assert p.eye_config.enable_micro_glance is False
    assert p.eye_config.enable_long_glance is True
    assert p.eye_config.glance_indices == (1, 8)
    assert 11 not in p.eye_config.glance_indices
    assert p.eye_config.blink_initial_ms == (3077.0, 6154.0)
    assert p.eye_config.blink_after_ms == (3462.0, 7692.0)


def test_load_unknown_raises():
    with pytest.raises(FileNotFoundError):
        load_personality("nonexistent-personality-xyz")


def test_build_eye_config_yaml_overrides_merge():
    cfg = build_eye_config(
        {
            "preset": "hyperactive",
            "eye_preset": "stoic",
            "eyes": {
                "long_glance": False,
                "blink": {"initial_ms": [100, 200], "after_ms": [300, 400]},
            },
        }
    )
    assert cfg.enable_long_glance is False
    assert cfg.enable_goofy_sequences is False
    assert cfg.blink_initial_ms == (100.0, 200.0)
    assert cfg.blink_after_ms == (300.0, 400.0)


def test_build_eye_config_defaults_eye_preset_to_preset():
    cfg = build_eye_config({"preset": "boring"})
    assert cfg.enable_micro_glance is False
    assert cfg.enable_long_glance is False


def test_load_emma_excludes_eye_11_and_smug_soft():
    p = load_personality("emma")
    assert 11 not in p.eye_config.micro_glance_indices
    assert 11 not in p.eye_config.glance_indices
    assert p.eye_config.forbidden_eye_indices == frozenset({11})
    assert p.emotes[1].name == "smug_soft"
    assert p.emotes[1].mouth == "wide-smile"
    assert "on-side" not in p.idle_mouth_pools.subtle
    for em in p.emotes:
        assert 11 not in {idx for idx, _, _ in em.eye_seq}


def test_build_eye_config_exclude_eye_indices():
    cfg = build_eye_config(
        {
            "preset": "moderate",
            "eyes": {"exclude_eye_indices": [11]},
        }
    )
    assert 11 not in cfg.micro_glance_indices
    assert 11 not in cfg.glance_indices


def test_merge_animation_vibe_calm():
    d: dict = {"animation": {"vibe": "calm"}}
    _merge_animation_vibe(d, "t")
    assert d["animation"]["preset"] == "boring"
    assert d["animation"]["eye_preset"] == "stoic"
    assert d["mouth_idle_enabled"] is False


def test_merge_animation_vibe_explicit_preset_wins():
    d = {"animation": {"vibe": "wild", "preset": "moderate"}}
    _merge_animation_vibe(d, "t")
    assert d["animation"]["preset"] == "moderate"


def test_merge_animation_vibe_unknown_raises():
    with pytest.raises(ValueError, match="unknown animation.vibe"):
        _merge_animation_vibe({"animation": {"vibe": "nope"}}, "t")


def test_mouth_pools_strip_disallowed(caplog: pytest.LogCaptureFixture):
    caplog.set_level("WARNING")
    data = {
        "idle_mouths": {
            "subtle": ["stunt", "wide-smile"],
            "happy": [],
            "goofy": [],
            "dramatic": [],
        }
    }
    p = _mouth_pools(data, "test")
    assert p.subtle == ("wide-smile",)
    assert "stunt" in caplog.text


def test_mouth_pools_idle_mouth_profile_standard():
    data = {"idle_mouth_profile": "standard"}
    p = _mouth_pools(data, "t")
    assert "laugh" in p.goofy
    assert p.subtle == ("stunt2",)
