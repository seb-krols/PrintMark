"""Dependency-free SVG diagnostics, with the same underside view as the popup."""

from __future__ import annotations

from html import escape

from .footprint import polygons


def svg_preview(footprint, surface, placements) -> str:
    left, bottom, right, top = footprint.bounds
    width, height = right - left, top - bottom
    pad = max(width, height) * 0.06 + 2

    def path(geometry, fill, stroke, opacity=1):
        commands = []
        for poly in polygons(geometry):
            for ring in [poly.exterior, *poly.interiors]:
                coords = list(ring.coords)
                commands.append("M " + " L ".join(f"{-x:.4f},{-y:.4f}" for x, y in coords) + " Z")
        return (
            f'<path d="{" ".join(commands)}" fill="{fill}" fill-rule="evenodd" '
            f'stroke="{stroke}" stroke-width="0.08" opacity="{opacity}"/>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="760"
 viewBox="{-right - pad} {-top - pad} {width + 2 * pad} {height + 2 * pad}">
<title>BaseMark — {escape(placements[0].text)} — seen from below</title>
<rect x="{-right - pad}" y="{-top - pad}" width="{width + 2 * pad}" height="{height + 2 * pad}"
 fill="#f5f3ee"/>
{path(footprint, "#d9dfda", "#8d9a92")}
{path(surface, "#eaf0e8", "none")}
{"".join(path(p.geometry, "#137d6b", "none") for p in placements)}
</svg>'''
