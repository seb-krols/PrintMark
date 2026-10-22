"""Generate an original 80 × 40 × 2 mm test coupon, ready to slice with a lab profile."""

from pathlib import Path


def write_coupon(path: Path):
    vertices = [
        (0, 0, 0),
        (80, 0, 0),
        (80, 40, 0),
        (0, 40, 0),
        (0, 0, 2),
        (80, 0, 2),
        (80, 40, 2),
        (0, 40, 2),
    ]
    faces = [
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
    ]
    lines = ["solid basemark_coupon"]
    for a, b, c in faces:
        lines += ["facet normal 0 0 0", "outer loop"]
        lines += ["vertex " + " ".join(map(str, vertices[i])) for i in (a, b, c)]
        lines += ["endloop", "endfacet"]
    lines.append("endsolid basemark_coupon")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


if __name__ == "__main__":
    write_coupon(Path("examples/basemark-coupon.stl"))
