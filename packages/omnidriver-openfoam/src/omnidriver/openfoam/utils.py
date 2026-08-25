from pathlib import Path

from .mutators import update_foam_entry


def set_delta_t(control_dict_path: Path, delta_t_seconds: float) -> None:
    update_foam_entry(control_dict_path, "deltaT", delta_t_seconds)


def set_end_time(control_dict_path: Path, t_s: float) -> None:
    update_foam_entry(control_dict_path, "endTime", t_s)



def replace_block_mesh_resolutions(
    block_mesh_dict_path: Path,
    cell_counts_str: str,
    *,
    expected_blocks: int = 1,
) -> None:
    """Rewrite lines starting with ``hex (`` in an existing `block_mesh_dict_path`.
    Replaces the cell counts portion of the hex definition with `cell_counts_str`.
    Validates that exactly `expected_blocks` were replaced.
    """
    if not block_mesh_dict_path.exists():
        raise FileNotFoundError(f"Missing mesh dictionary: {block_mesh_dict_path}")

    lines = block_mesh_dict_path.read_text().splitlines(keepends=True)
    replaced_count = 0

    with block_mesh_dict_path.open("w") as handle:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("hex (") and not stripped.startswith("//"):
                prefix, _, suffix = line.partition(") (")
                if not suffix:
                    handle.write(line)
                    continue
                _, _, trailing = suffix.partition(") simpleGrading")
                handle.write(f"{prefix}) ({cell_counts_str}) simpleGrading{trailing}")
                replaced_count += 1
            else:
                handle.write(line)

    if replaced_count != expected_blocks:
        raise KeyError(
            f"Expected to update {expected_blocks} hex blocks in {block_mesh_dict_path}, "
            f"but found {replaced_count}."
        )
