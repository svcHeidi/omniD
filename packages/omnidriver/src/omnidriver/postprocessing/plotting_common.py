from __future__ import annotations

from collections.abc import Iterable, Mapping

import plotly.colors as plotly_colors


def lighten_hex_color(color: str, amount: float) -> str:
    """Lighten a hex color by amount (0=no change, 1=white)."""
    bounded_amount = min(max(float(amount), 0.0), 1.0)
    red, green, blue = plotly_colors.hex_to_rgb(color)
    light_red = int(red + (255 - red) * bounded_amount)
    light_green = int(green + (255 - green) * bounded_amount)
    light_blue = int(blue + (255 - blue) * bounded_amount)
    return f"rgb({light_red},{light_green},{light_blue})"


def ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def parse_two_part_stem(
    filename: str,
    *,
    first_map: Mapping[str, str],
    second_map: Mapping[str, str],
) -> tuple[str, str]:
    """Split a `<first>_<second>_...` filename stem and map both tokens.

    Tokens absent from their map pass through unchanged, so callers only supply
    the renames they care about.
    """
    from pathlib import Path
    file_base = Path(filename).stem
    parts = file_base.split("_")

    raw_first = parts[0] if parts else "UnknownFirst"
    raw_second = parts[1] if len(parts) > 1 else "UnknownSecond"

    return first_map.get(raw_first, raw_first), second_map.get(raw_second, raw_second)


def build_visibility_mask(trace_indices: Iterable[int], total_traces: int) -> list[bool]:
    selected = set(trace_indices)
    return [index in selected for index in range(total_traces)]
