from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Device:
    id: int
    name: str
    source: str
    sample_rate: int
    channels: int
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def map_devices(
    records: list[dict[str, Any]], host_id: int, default_loopback: int, default_input: int
) -> list[Device]:
    result = []
    for record in records:
        if int(record["hostApi"]) != host_id or int(record["maxInputChannels"]) < 1:
            continue
        loopback = bool(record.get("isLoopbackDevice", False))
        index = int(record["index"])
        result.append(
            Device(
                index,
                str(record["name"]),
                "system" if loopback else "microphone",
                int(record["defaultSampleRate"]),
                min(2, int(record["maxInputChannels"])),
                index == (default_loopback if loopback else default_input),
            )
        )
    return result


def select_device(devices: list[Device], source: str, selector: str | None) -> Device:
    candidates = [device for device in devices if device.source == source]
    if selector is None:
        matches = [device for device in candidates if device.is_default]
    elif selector.isdecimal():
        matches = [device for device in candidates if device.id == int(selector)]
    else:
        matches = [device for device in candidates if device.name.casefold() == selector.casefold()]
    if len(matches) != 1:
        raise ValueError(
            f"Cannot uniquely select {source} device {selector or '(default)'!r}. "
            "Run 'classscribe devices' and supply its numeric ID or exact name."
        )
    return matches[0]
