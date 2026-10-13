from xek.hardware import recommend


def machine(ram=16, free=3, vram=4, disk=118):
    return {"ram_gb": ram, "free_ram_gb": free, "gpus": [{"vram_gb": vram}], "disk_free_gb": disk}


def test_actual_low_memory_profile_offers_motion_comic_without_download():
    plan = recommend(machine())
    assert plan["production_mode"] == "motion-comic" and plan["video_model"] is None
    assert plan["image_profile"] == "flux-schnell-gguf" and plan["tts_device"] == "cpu"
    assert not plan["download_allowed"] and plan["blockers"]


def test_freed_memory_does_not_invent_more_vram():
    plan = recommend(machine(free=12))
    assert plan["download_allowed"] and plan["video_model"] is None


def test_higher_capacity_host_selects_video_candidate():
    plan = recommend(machine(ram=32, free=24, vram=16))
    assert plan["video_model"] == "wan2.2-ti2v-5b" and plan["download_allowed"]


def test_unknown_ram_never_implies_compatible_hardware():
    plan = recommend({"ram_gb": None, "free_ram_gb": None, "gpus": [], "disk_free_gb": 100})
    assert not plan["download_allowed"]
