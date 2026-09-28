"""Declarative Plotly figure construction for tutorial post-processing scripts:
load CSVs, build group-shaded traces, apply a shared layout, and write an
interactive HTML artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import plotly.graph_objects as go

from .plotting_common import build_visibility_mask, lighten_hex_color, ordered_unique
from .style import apply_plotly_layout, write_plotly_html


#: Default base-color palette for :class:`GroupShadedColors`, chosen to be
#: visually distinct on a white background.
DEFAULT_PALETTE: list[str] = [
    "#1f77b4",  # blue
    "#2ca02c",  # green
    "#eb1616",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#17becf",  # cyan
    "#bcbd22",  # yellow-green
]


class GroupShadedColors:
    """Assign colors to traces using a two-level group + shade strategy.

    Each group (e.g. a DX mesh size) gets a distinct base color from the
    palette; each shade within a group (e.g. a DT time step) is a lightened
    variant of that base color, so related traces stay visually grouped
    while remaining distinguishable.
    """

    def __init__(
        self,
        palette: list[str] | None = None,
        max_shade_amount: float = 0.4,
    ) -> None:
        self._palette = palette or DEFAULT_PALETTE
        self._max_shade = max_shade_amount
        self._group_order: list[Any] = []
        self._shades: dict[Any, list[Any]] = {}

    def register_groups(self, groups: Iterable[Any]) -> None:
        """Register group keys in display order (first seen = first color)."""
        for g in ordered_unique(list(groups)):
            if g not in self._group_order:
                self._group_order.append(g)

    def register_shades(self, group: Any, shades: Iterable[Any]) -> None:
        """Register shade variants for one group, sorted ascending."""
        self._shades[group] = sorted(set(shades))

    def color_for(self, group: Any, shade: Any) -> str:
        """Return the ``rgb(r,g,b)`` color string for a given (group, shade) pair."""
        if group in self._group_order:
            group_index = self._group_order.index(group)
        else:
            group_index = 0
        base_color = self._palette[group_index % len(self._palette)]

        shade_list = self._shades.get(group, [shade])
        try:
            shade_index = shade_list.index(shade)
        except ValueError:
            shade_index = 0
        shade_count = max(len(shade_list) - 1, 1)
        amount = (shade_index / shade_count) * self._max_shade

        return lighten_hex_color(base_color, amount)


def load_csv_folder(
    folder: str | Path,
    glob_pattern: str,
    *,
    drop_columns: list[str] | None = None,
) -> list[tuple[str, pd.DataFrame]]:
    """Load CSV files matching a glob pattern from *folder*, dropping any of
    *drop_columns* found in each (columns absent from a given file are
    silently skipped). Returns sorted ``(basename, DataFrame)`` pairs, or an
    empty list (with a warning printed) if nothing matches.
    """
    folder = Path(folder)
    paths = sorted(folder.glob(glob_pattern))
    if not paths:
        print(f"[plot_builder] No files match '{glob_pattern}' in {folder}")
        return []

    drop = set(drop_columns or [])
    result: list[tuple[str, pd.DataFrame]] = []
    for p in paths:
        df = pd.read_csv(p)
        to_drop = [c for c in drop if c in df.columns]
        if to_drop:
            df = df.drop(columns=to_drop)
        result.append((p.name, df))

    print(f"[plot_builder] Loaded {len(result)} file(s) matching '{glob_pattern}'")
    return result


@dataclass
class TraceSpec:
    """How to extract X/Y series from a DataFrame for one trace: column
    selectors, per-axis scale factors (e.g. ``1000.0`` for m to mm), and the
    Plotly trace ``mode``.
    """

    x_col: str | int = 0
    y_col: str | int = 1
    x_scale: float = 1.0
    y_scale: float = 1.0
    mode: str = "lines+markers"

    def x(self, df: pd.DataFrame) -> pd.Series:
        """Return the scaled X series from *df*."""
        col = df.columns[self.x_col] if isinstance(self.x_col, int) else self.x_col
        return df[col] * self.x_scale

    def y(self, df: pd.DataFrame) -> pd.Series:
        """Return the scaled Y series from *df*."""
        col = df.columns[self.y_col] if isinstance(self.y_col, int) else self.y_col
        return df[col] * self.y_scale


def build_line_traces(
    data: list[tuple[str, pd.DataFrame]],
    *,
    trace: TraceSpec,
    name_fn: Callable[[str], str],
    colors: GroupShadedColors | None = None,
    group_fn: Callable[[str], Any] | None = None,
    shade_fn: Callable[[str], Any] | None = None,
) -> list[go.Scatter]:
    """Build Plotly ``Scatter`` traces from ``(filename, DataFrame)`` pairs
    (see :func:`load_csv_folder`), one trace per file. ``colors``,
    ``group_fn`` and ``shade_fn`` must be given together to color traces by
    group/shade; otherwise Plotly's default color cycle is used.
    """
    use_colors = colors is not None and group_fn is not None and shade_fn is not None
    result: list[go.Scatter] = []

    for filename, df in data:
        x = trace.x(df)
        y = trace.y(df)
        name = name_fn(filename)
        kw: dict[str, Any] = {"mode": trace.mode}

        if use_colors:
            color = colors.color_for(group_fn(filename), shade_fn(filename))
            kw["line"] = dict(color=color)
            kw["marker"] = dict(color=color)

        result.append(go.Scatter(x=x, y=y, name=name, **kw))

    return result


@dataclass
class PlotSpec:
    """Everything needed to apply a layout and register a figure as a
    post-processing artifact; does not hold trace data itself (traces are
    added to a ``go.Figure`` separately before calling :func:`write_plot`).
    ``kind`` is the artifact kind: ``"plot"`` (default), ``"table"``,
    ``"data"``, or ``"report"``.
    """

    title: str
    xaxis_title: str
    yaxis_title: str
    output_filename: str
    label: str
    legend_title: str | None = None
    kind: str = "plot"
    height: int | None = None
    width: int | None = None
    template: str = "plotly_white"

    def artifact(self, output_dir: Path) -> dict[str, Any]:
        """Return the artifact dict for this figure."""
        return {
            "path": str(output_dir / self.output_filename),
            "label": self.label,
            "kind": self.kind,
            "format": "html",
        }


def write_plot(
    fig: go.Figure,
    spec: PlotSpec,
    output_dir: Path,
    *,
    updatemenus: list[dict[str, Any]] | None = None,
    show: bool = False,
) -> dict[str, Any]:
    """Apply layout from *spec* to *fig*, write the HTML file, and return the
    artifact dict, ready to be returned from a ``run_postprocessing``
    function. Pass :func:`make_toggle_button`'s output as *updatemenus* for
    a toggle.
    """
    apply_plotly_layout(
        fig,
        title=spec.title,
        xaxis_title=spec.xaxis_title,
        yaxis_title=spec.yaxis_title,
        legend_title=spec.legend_title,
        template=spec.template,
        showlegend=True,
        updatemenus=updatemenus,
        width=spec.width,
        height=spec.height,
    )
    output_path = output_dir / spec.output_filename
    write_plotly_html(fig, output_path)
    if show:
        fig.show()
    return spec.artifact(output_dir)


def make_toggle_button(
    fig: go.Figure,
    *,
    label_a: str,
    label_b: str,
    indices_a: Iterable[int],
    indices_b: Iterable[int],
    names_a: list[str] | None = None,
    names_b: list[str] | None = None,
    x: float = 0.2,
    y: float = 1.0,
) -> list[dict[str, Any]]:
    """Build a two-state Plotly toggle button (``updatemenus`` entry) that
    switches which trace indices are visible, and optionally renames traces
    per state (``names_a``/``names_b``, each matching ``len(fig.data)`` if
    given). Pass the result as ``updatemenus`` to :func:`write_plot`.
    """
    n = len(fig.data)
    set_a = set(indices_a)
    set_b = set(indices_b)
    vis_a = build_visibility_mask(set_a, n)
    vis_b = build_visibility_mask(set_b, n)

    args_a: dict[str, Any] = {"visible": vis_a}
    args_b: dict[str, Any] = {"visible": vis_b}
    if names_a is not None:
        args_a["name"] = names_a
    if names_b is not None:
        args_b["name"] = names_b

    return [
        {
            "type": "buttons",
            "direction": "right",
            "x": x,
            "y": y,
            "xanchor": "left",
            "yanchor": "top",
            "showactive": False,
            "buttons": [
                {"label": label_a, "method": "update", "args": [args_a]},
                {"label": label_b, "method": "update", "args": [args_b]},
            ],
        }
    ]
