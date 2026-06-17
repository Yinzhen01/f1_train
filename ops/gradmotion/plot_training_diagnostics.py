#!/usr/bin/env python3
"""Render Gradmotion training diagnostics from train_focused_view logs.

The script intentionally uses only the Python standard library so it can run on
minimal cloud desktops without matplotlib.
"""

from __future__ import annotations

import argparse
import html
import math
import re
from pathlib import Path


COLORS = (
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#4f46e5",
    "#be123c",
)


def parse_key_values(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, raw in re.findall(r"([A-Za-z0-9_]+)=(-?[0-9.]+)", text):
        try:
            values[key] = float(raw)
        except ValueError:
            pass
    return values


def parse_log(path: Path) -> dict[str, object]:
    termination_rows = []
    joint_top_rows = []
    joint_group_rows = []
    body_top_rows = []
    body_group_rows = []
    config: dict[str, str] = {}
    current_term_step = None
    current_joint_step = None
    current_body_step = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()

        if stripped.startswith("rewards.") or stripped.startswith("reward_scale."):
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                config[key.strip()] = value.strip()
            continue

        match = re.match(r"termination_diag_step:\s+(\d+)", stripped)
        if match:
            current_term_step = int(match.group(1))
            continue

        if stripped.startswith("termination_diag:"):
            row = parse_key_values(stripped)
            if current_term_step is not None:
                row["step"] = float(current_term_step)
            termination_rows.append(row)
            continue

        match = re.match(r"joint_diag_step:\s+(\d+)", stripped)
        if match:
            current_joint_step = int(match.group(1))
            continue

        match = re.match(
            r"joint_diag_top:\s+(\d+)\s+(\S+)\s+(\S+)\s+"
            r"(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)",
            stripped,
        )
        if match:
            joint_top_rows.append(
                {
                    "step": current_joint_step,
                    "idx": int(match.group(1)),
                    "name": match.group(2),
                    "group": match.group(3),
                    "mean_abs_pos_err": float(match.group(4)),
                    "mean_abs_vel_err": float(match.group(5)),
                    "mean_abs_ref_delta": float(match.group(6)),
                }
            )
            continue

        match = re.match(
            r"joint_diag_group:\s+(\S+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)",
            stripped,
        )
        if match:
            joint_group_rows.append(
                {
                    "step": current_joint_step,
                    "group": match.group(1),
                    "mean_abs_pos_err": float(match.group(2)),
                    "mean_abs_vel_err": float(match.group(3)),
                    "mean_abs_ref_delta": float(match.group(4)),
                }
            )

        match = re.match(r"body_pos_diag_step:\s+(\d+)", stripped)
        if match:
            current_body_step = int(match.group(1))
            continue

        match = re.match(
            r"body_pos_diag_top:\s+(\d+)\s+(\S+)\s+(\S+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)",
            stripped,
        )
        if match:
            body_top_rows.append(
                {
                    "step": current_body_step,
                    "idx": int(match.group(1)),
                    "name": match.group(2),
                    "group": match.group(3),
                    "mean_pos_err_m": float(match.group(4)),
                    "focus_pos_err_m": float(match.group(5)),
                }
            )
            continue

        match = re.match(
            r"body_pos_diag_group:\s+(\S+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)",
            stripped,
        )
        if match:
            body_group_rows.append(
                {
                    "step": current_body_step,
                    "group": match.group(1),
                    "mean_pos_err_m": float(match.group(2)),
                    "focus_pos_err_m": float(match.group(3)),
                }
            )
            continue

    return {
        "termination": termination_rows,
        "joint_top": joint_top_rows,
        "joint_group": joint_group_rows,
        "body_top": body_top_rows,
        "body_group": body_group_rows,
        "config": config,
    }


def nice_range(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    lo = min(values)
    hi = max(values)
    if math.isclose(lo, hi):
        pad = abs(hi) * 0.1 or 1.0
        return lo - pad, hi + pad
    pad = (hi - lo) * 0.08
    return lo - pad, hi + pad


def svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#111827}'
        '.small{font-size:12px}.label{font-size:13px}.title{font-size:20px;font-weight:700}'
        '.axis{stroke:#374151;stroke-width:1}.grid{stroke:#e5e7eb;stroke-width:1}'
        '</style>',
    ]


def line_chart(
    title: str,
    series: dict[str, list[tuple[float, float]]],
    output: Path,
    ylabel: str,
    width: int = 1100,
    height: int = 620,
) -> None:
    margin_l, margin_r, margin_t, margin_b = 90, 220, 70, 70
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    all_x = [x for points in series.values() for x, _ in points]
    all_y = [y for points in series.values() for _, y in points]
    x_min, x_max = nice_range(all_x)
    y_min, y_max = nice_range(all_y)
    if x_min < 0 < x_max:
        x_min = 0.0
    if y_min < 0 < y_max:
        y_min = 0.0

    def sx(x: float) -> float:
        return margin_l + (x - x_min) / (x_max - x_min) * plot_w

    def sy(y: float) -> float:
        return margin_t + plot_h - (y - y_min) / (y_max - y_min) * plot_h

    svg = svg_header(width, height)
    svg.append(f'<text x="{margin_l}" y="36" class="title">{html.escape(title)}</text>')

    for i in range(6):
        gy = margin_t + i * plot_h / 5
        y_val = y_max - i * (y_max - y_min) / 5
        svg.append(f'<line x1="{margin_l}" y1="{gy:.1f}" x2="{margin_l + plot_w}" y2="{gy:.1f}" class="grid"/>')
        svg.append(f'<text x="{margin_l - 12}" y="{gy + 4:.1f}" text-anchor="end" class="small">{y_val:.3g}</text>')

    for i in range(6):
        gx = margin_l + i * plot_w / 5
        x_val = x_min + i * (x_max - x_min) / 5
        svg.append(f'<line x1="{gx:.1f}" y1="{margin_t}" x2="{gx:.1f}" y2="{margin_t + plot_h}" class="grid"/>')
        svg.append(f'<text x="{gx:.1f}" y="{margin_t + plot_h + 24}" text-anchor="middle" class="small">{x_val:.0f}</text>')

    svg.append(f'<line x1="{margin_l}" y1="{margin_t + plot_h}" x2="{margin_l + plot_w}" y2="{margin_t + plot_h}" class="axis"/>')
    svg.append(f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l}" y2="{margin_t + plot_h}" class="axis"/>')
    svg.append(f'<text x="{margin_l + plot_w / 2}" y="{height - 22}" text-anchor="middle" class="label">diag step</text>')
    svg.append(f'<text x="22" y="{margin_t + plot_h / 2}" transform="rotate(-90 22 {margin_t + plot_h / 2})" text-anchor="middle" class="label">{html.escape(ylabel)}</text>')

    for idx, (name, points) in enumerate(series.items()):
        if not points:
            continue
        color = COLORS[idx % len(COLORS)]
        path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
        svg.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        lx = margin_l + plot_w + 28
        ly = margin_t + 24 + idx * 24
        svg.append(f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 22}" y2="{ly - 4}" stroke="{color}" stroke-width="3"/>')
        svg.append(f'<text x="{lx + 30}" y="{ly}" class="small">{html.escape(name)}</text>')

    svg.append("</svg>")
    output.write_text("\n".join(svg), encoding="utf-8")


def bar_chart(title: str, rows: list[dict[str, object]], output: Path) -> None:
    width, height = 1150, 720
    margin_l, margin_r, margin_t, margin_b = 300, 70, 70, 60
    plot_w = width - margin_l - margin_r
    bar_h = 28
    gap = 12
    rows = rows[:14]
    max_value = max([float(row["mean_abs_pos_err"]) for row in rows] or [1.0])
    svg = svg_header(width, height)
    svg.append(f'<text x="{margin_l}" y="36" class="title">{html.escape(title)}</text>')
    svg.append(f'<text x="{margin_l}" y="{height - 22}" class="label">mean abs angle error (rad)</text>')
    for i, row in enumerate(rows):
        y = margin_t + i * (bar_h + gap)
        label = f'{row["idx"]} {row["name"]}'
        value = float(row["mean_abs_pos_err"])
        w = 0 if max_value <= 0 else value / max_value * plot_w
        color = COLORS[i % len(COLORS)]
        svg.append(f'<text x="{margin_l - 12}" y="{y + 20}" text-anchor="end" class="small">{html.escape(label)}</text>')
        svg.append(f'<rect x="{margin_l}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{color}" opacity="0.88"/>')
        svg.append(f'<text x="{margin_l + w + 8:.1f}" y="{y + 20}" class="small">{value:.4f}</text>')
    svg.append("</svg>")
    output.write_text("\n".join(svg), encoding="utf-8")


def body_bar_chart(title: str, rows: list[dict[str, object]], output: Path) -> None:
    width, height = 1150, 720
    margin_l, margin_r, margin_t, margin_b = 300, 70, 70, 60
    plot_w = width - margin_l - margin_r
    bar_h = 28
    gap = 12
    rows = rows[:14]
    max_value = max([float(row["mean_pos_err_m"]) for row in rows] or [1.0])
    svg = svg_header(width, height)
    svg.append(f'<text x="{margin_l}" y="36" class="title">{html.escape(title)}</text>')
    svg.append(f'<text x="{margin_l}" y="{height - 22}" class="label">mean root-local position error (m)</text>')
    for i, row in enumerate(rows):
        y = margin_t + i * (bar_h + gap)
        label = f'{row["idx"]} {row["name"]}'
        value = float(row["mean_pos_err_m"])
        w = 0 if max_value <= 0 else value / max_value * plot_w
        color = COLORS[i % len(COLORS)]
        svg.append(f'<text x="{margin_l - 12}" y="{y + 20}" text-anchor="end" class="small">{html.escape(label)}</text>')
        svg.append(f'<rect x="{margin_l}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{color}" opacity="0.88"/>')
        svg.append(f'<text x="{margin_l + w + 8:.1f}" y="{y + 20}" class="small">{value:.4f}</text>')
    svg.append("</svg>")
    output.write_text("\n".join(svg), encoding="utf-8")


def write_summary(data: dict[str, object], output: Path) -> None:
    termination = data["termination"]
    joint_top = data["joint_top"]
    body_top = data["body_top"]
    config = data["config"]
    latest_term = termination[-1] if termination else {}
    latest_step = int(latest_term.get("step", -1)) if latest_term else None
    latest_joint_step = joint_top[-1]["step"] if joint_top else None

    lines = [
        "# Gradmotion Training Diagnostics",
        "",
        "## Current Failure Thresholds",
        "",
        f"- termination_min_base_height: {config.get('rewards.termination_min_base_height', '<not logged>')} m",
        f"- termination_max_ref_root_xy_distance: {config.get('rewards.termination_max_ref_root_xy_distance', '<not logged>')} m",
        f"- termination_max_ref_joint_pos_error: {config.get('rewards.termination_max_ref_joint_pos_error', '<not logged>')}",
        f"- termination_support_rect_margin: {config.get('rewards.termination_support_rect_margin', '<not logged>')} m",
        f"- termination_world_keypoint_thresholds: {config.get('rewards.termination_world_keypoint_thresholds', '<not logged>')}",
        "",
        "For F1 motion imitation, `ref_keypoint_pos` uses aligned world-space keypoint error when body_pos/body_names exist in the motion NPZ.",
        "The current motion-imitation profile hard-resets when ankle world error exceeds 0.10 m or head/neck world error exceeds 0.15 m.",
        "",
        "## Latest Termination Diagnostics",
        "",
    ]

    if latest_term:
        lines.append(f"- latest termination diag step: {latest_step}")
        for key in ("reset_total", "base_contact", "support_rect", "height", "ref_xy", "ref_joint"):
            lines.append(f"- {key}: {latest_term.get(key, '<missing>')}")
        for key in ("base_height_min", "ref_xy_dist_max", "support_rect_outside_max", "ref_joint_err_max"):
            lines.append(f"- {key}: {latest_term.get(key, '<missing>')}")
    else:
        lines.append("- no termination diagnostics parsed")

    lines.extend(["", "## Latest Joint Angle Error Top Entries", ""])
    if joint_top:
        rows = [row for row in joint_top if row["step"] == latest_joint_step]
        for row in rows[:12]:
            lines.append(
                f"- {row['idx']} {row['name']}: "
                f"mean_abs_pos_err={row['mean_abs_pos_err']:.6f} rad, "
                f"mean_abs_vel_err={row['mean_abs_vel_err']:.6f}"
            )
    else:
        lines.append("- no joint diagnostics parsed")

    lines.extend(["", "## Latest Body Position Error Top Entries", ""])
    if body_top:
        latest_body_step = body_top[-1]["step"]
        rows = [row for row in body_top if row["step"] == latest_body_step]
        for row in rows[:12]:
            lines.append(
                f"- {row['idx']} {row['name']}: "
                f"mean_pos_err_m={row['mean_pos_err_m']:.6f}, "
                f"focus_pos_err_m={row['focus_pos_err_m']:.6f}"
            )
    else:
        lines.append("- no body position diagnostics parsed")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render(data: dict[str, object], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    termination = data["termination"]
    joint_group = data["joint_group"]
    joint_top = data["joint_top"]
    body_group = data["body_group"]
    body_top = data["body_top"]

    term_series: dict[str, list[tuple[float, float]]] = {}
    for key in ("reset_total", "base_contact", "support_rect", "height", "ref_xy", "ref_joint"):
        term_series[key] = [
            (float(row["step"]), float(row.get(key, 0.0)))
            for row in termination
            if "step" in row
        ]
    line_chart("Termination Counts", term_series, out_dir / "termination_counts.svg", "count")

    term_metric_series: dict[str, list[tuple[float, float]]] = {}
    for key in ("base_height_min", "ref_xy_dist_max", "support_rect_outside_max", "ref_joint_err_max"):
        term_metric_series[key] = [
            (float(row["step"]), float(row.get(key, 0.0)))
            for row in termination
            if "step" in row
        ]
    line_chart("Termination Metric Values", term_metric_series, out_dir / "termination_metrics.svg", "metric value")

    groups = sorted({str(row["group"]) for row in joint_group})
    group_series = {
        group: [
            (float(row["step"]), float(row["mean_abs_pos_err"]))
            for row in joint_group
            if row["group"] == group and row["step"] is not None
        ]
        for group in groups
    }
    line_chart("Joint Angle Error by Group", group_series, out_dir / "joint_angle_error_by_group.svg", "mean abs angle error (rad)")

    if joint_top:
        latest_step = joint_top[-1]["step"]
        latest_rows = [row for row in joint_top if row["step"] == latest_step]
        bar_chart(f"Latest Joint Angle Error Top Entries (step {latest_step})", latest_rows, out_dir / "latest_joint_angle_error_top.svg")

    groups = sorted({str(row["group"]) for row in body_group})
    body_group_series = {
        group: [
            (float(row["step"]), float(row["mean_pos_err_m"]))
            for row in body_group
            if row["group"] == group and row["step"] is not None
        ]
        for group in groups
    }
    if body_group_series:
        line_chart("Body Position Error by Group", body_group_series, out_dir / "body_position_error_by_group.svg", "mean root-local position error (m)")

    if body_top:
        latest_step = body_top[-1]["step"]
        latest_rows = [row for row in body_top if row["step"] == latest_step]
        body_bar_chart(f"Latest Body Position Error Top Entries (step {latest_step})", latest_rows, out_dir / "latest_body_position_error_top.svg")

    write_summary(data, out_dir / "summary.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Path to a train_focused_view log file")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for SVG and summary outputs")
    args = parser.parse_args()

    data = parse_log(args.log)
    render(data, args.out_dir)
    print(f"Wrote diagnostics to {args.out_dir}")


if __name__ == "__main__":
    main()
