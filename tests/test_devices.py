import pytest

from classscribe.audio.devices import Device, map_devices, select_device


def test_enumeration_mapping_and_defaults():
    records = [
        {
            "index": 0,
            "name": "Speaker",
            "hostApi": 2,
            "maxInputChannels": 0,
            "defaultSampleRate": 48000,
        },
        {
            "index": 1,
            "name": "Mic",
            "hostApi": 2,
            "maxInputChannels": 1,
            "defaultSampleRate": 44100,
        },
        {
            "index": 7,
            "name": "Speaker loopback",
            "hostApi": 2,
            "maxInputChannels": 8,
            "defaultSampleRate": 48000,
            "isLoopbackDevice": True,
        },
        {
            "index": 8,
            "name": "Other API mic",
            "hostApi": 0,
            "maxInputChannels": 1,
            "defaultSampleRate": 44100,
        },
    ]
    devices = map_devices(records, 2, 7, 1)
    assert [d.id for d in devices] == [1, 7]
    assert select_device(devices, "system", None).id == 7
    assert select_device(devices, "microphone", None).id == 1
    assert devices[1].channels == 2


@pytest.mark.parametrize("selector", ["7", "sPeAkEr"])
def test_explicit_selection(selector):
    device = Device(7, "Speaker", "system", 48000, 2)
    assert select_device([device], "system", selector) == device


@pytest.mark.parametrize("selector", [None, "99", "missing", "Speak", "-1"])
def test_invalid_device(selector):
    with pytest.raises(ValueError, match="Cannot uniquely select"):
        select_device([Device(7, "Speaker", "system", 48000, 2)], "system", selector)


def test_ambiguous_name_and_wrong_source():
    devices = [Device(i, "Same", "system", 48000, 2) for i in (1, 2)]
    with pytest.raises(ValueError):
        select_device(devices, "system", "same")
    with pytest.raises(ValueError):
        select_device(devices, "microphone", "1")
