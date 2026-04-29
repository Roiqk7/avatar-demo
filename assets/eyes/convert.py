#!/usr/bin/env python3
"""Extract individual eye sprites from the sprite sheet (eyes_set.png).

The source image is a 3000x3000 sprite sheet with a 5-row x 3-column grid
of eye sprites on a saturated yellow background. The grid has significant
margins and gaps between cells:

  - Margins: ~295px top, ~194px left, ~271px bottom, ~158px right
  - Gaps between rows: ~136px,  between columns: ~176px
  - Actual cell size: ~768x378  (NOT the naive 1000x600)

The script auto-detects grid boundaries by scanning for horizontal/vertical
bands of pure background, so it is robust to small layout variations.

Background removal uses flood-fill from cell edges: any pixel within a
small RGB distance of the background color that is connected to the border
is made transparent.  This preserves interior yellow-ish content (golden
eye rings, eyelid shading) that a naive color-key would destroy.

Usage:
    cd assets/eyes
    python convert.py

Overwrites any existing eye-*.png files in the current directory.
"""

from PIL import Image
import numpy as np

NAMES: list[str] = [
    "open-neutral",        # row 0, col 0
    "open-pupils-left",    # row 0, col 1
    "open-large-pupils",   # row 0, col 2
    "blink-half-top",      # row 1, col 0
    "blink-closed",        # row 1, col 1
    "sleepy-asymmetric",   # row 1, col 2
    "neutral",             # row 2, col 0
    "angry",               # row 2, col 1
    "looking-right",       # row 2, col 2
    "squinting",           # row 3, col 0
    "open-looking-up",     # row 3, col 1
    "side-glance",         # row 3, col 2
    "droopy",              # row 4, col 0
    "crossed",             # row 4, col 1
    "small-pupils",        # row 4, col 2
]

ROWS, COLS = 5, 3


def _find_bg_color(arr: np.ndarray) -> np.ndarray:
    """Return the RGB background color (sampled from corners)."""
    corners = [arr[0, 0, :3], arr[0, -1, :3], arr[-1, 0, :3], arr[-1, -1, :3]]
    return np.median(corners, axis=0).astype(np.uint8)


def _find_gaps(counts: np.ndarray, min_gap: int = 20) -> list[tuple[int, int]]:
    """Find contiguous runs of near-zero values (background-only bands).

    Returns a list of (start, end) inclusive index pairs for each gap.
    Only gaps wider than *min_gap* pixels are kept (to ignore noise).
    """
    gaps: list[tuple[int, int]] = []
    in_gap = False
    gap_start = 0
    for i in range(len(counts)):
        if counts[i] <= 2:
            if not in_gap:
                gap_start = i
                in_gap = True
        else:
            if in_gap:
                if i - gap_start >= min_gap:
                    gaps.append((gap_start, i - 1))
                in_gap = False
    if in_gap and len(counts) - gap_start >= min_gap:
        gaps.append((gap_start, len(counts) - 1))
    return gaps


def _cells_from_gaps(gaps: list[tuple[int, int]], expected: int) -> list[tuple[int, int]]:
    """Derive cell (start, end) ranges from the gaps between them.

    *gaps* must include the leading/trailing margin gaps, so there are
    ``expected + 1`` gaps for ``expected`` cells.
    """
    if len(gaps) != expected + 1:
        raise ValueError(
            f"Expected {expected + 1} gaps for {expected} cells, found {len(gaps)}"
        )
    cells: list[tuple[int, int]] = []
    for i in range(expected):
        start = gaps[i][1] + 1
        end   = gaps[i + 1][0] - 1
        cells.append((start, end))
    return cells


def remove_yellow_bg(arr: np.ndarray, bg_rgb: np.ndarray) -> np.ndarray:
    """Remove background via flood-fill from edges.

    Uses an adaptive threshold: if the cell's max colour distance from *bg_rgb*
    is high (>100, meaning it contains clearly non-yellow content like eyeballs),
    a generous threshold (60) is used to fully clean the background gradient.
    For all-yellow cells (e.g. blink-closed eyelids, max dist < 100) a tight
    threshold (15) is used so the subtle shading is not eaten.
    """
    diff = np.sqrt(np.sum((arr[:, :, :3].astype(float) - bg_rgb.astype(float)) ** 2, axis=2))
    dist_thresh = 60.0 if diff.max() > 100 else 15.0
    could_be_bg = diff < dist_thresh
    h, w = could_be_bg.shape

    # Seed from all edge pixels that look like bg
    reached = np.zeros_like(could_be_bg)
    reached[0, :] = could_be_bg[0, :]
    reached[-1, :] = could_be_bg[-1, :]
    reached[:, 0] = could_be_bg[:, 0]
    reached[:, -1] = could_be_bg[:, -1]

    # Iterative dilation: expand reached into could_be_bg neighbors
    while True:
        expanded = reached.copy()
        expanded[1:, :] |= reached[:-1, :]   # down
        expanded[:-1, :] |= reached[1:, :]   # up
        expanded[:, 1:] |= reached[:, :-1]   # right
        expanded[:, :-1] |= reached[:, 1:]   # left
        expanded &= could_be_bg
        if np.array_equal(expanded, reached):
            break
        reached = expanded

    result = arr.copy()
    result[reached, 3] = 0
    return result


def extract_sprites(src_path: str = "eyes_set.png") -> None:
    img = Image.open(src_path).convert("RGBA")
    arr = np.array(img)
    h, w = arr.shape[:2]

    # Detect background color and build a non-background mask
    bg = _find_bg_color(arr)
    tol = 10
    mask = np.any(np.abs(arr[:, :, :3].astype(int) - bg.astype(int)) > tol, axis=2)

    # Count non-bg pixels per row / column to locate grid gaps
    row_counts = np.sum(mask, axis=1)
    col_counts = np.sum(mask, axis=0)

    h_gaps = _find_gaps(row_counts)
    v_gaps = _find_gaps(col_counts)

    print(f"Image size: {w}x{h}")
    print(f"Detected {len(h_gaps)} horizontal gaps, {len(v_gaps)} vertical gaps")

    row_cells = _cells_from_gaps(h_gaps, ROWS)
    col_cells = _cells_from_gaps(v_gaps, COLS)

    for i, (rs, re) in enumerate(row_cells):
        print(f"  Row {i}: y={rs}-{re}  (h={re - rs + 1})")
    for i, (cs, ce) in enumerate(col_cells):
        print(f"  Col {i}: x={cs}-{ce}  (w={ce - cs + 1})")

    pad = 10

    for idx, name in enumerate(NAMES):
        row = idx // COLS
        col = idx % COLS

        rs, re = row_cells[row]
        cs, ce = col_cells[col]

        cell = img.crop((cs, rs, ce + 1, re + 1))
        cell_arr = np.array(cell)
        cell_arr = remove_yellow_bg(cell_arr, bg)
        result = Image.fromarray(cell_arr)

        bbox = result.getbbox()
        if bbox is None:
            print(f"  [{idx:2d}] {name}: EMPTY - skipped")
            continue

        cw, ch = ce - cs + 1, re - rs + 1
        bx1 = max(0, bbox[0] - pad)
        by1 = max(0, bbox[1] - pad)
        bx2 = min(cw, bbox[2] + pad)
        by2 = min(ch, bbox[3] + pad)

        cropped = result.crop((bx1, by1, bx2, by2))
        out = f"eye-{idx:02d}-{name}.png"
        cropped.save(out)
        print(f"  {out:40s}  {cropped.size[0]:4d}x{cropped.size[1]:<4d}")


def _fix_yellow_sprites(src_path: str = "eyes_set.png") -> None:
    """Re-extract sprites whose yellow eyelid/ring content gets eaten.

    The flood-fill bg removal eats into golden-ring edges and yellow eyelid
    shading because those pixels are close in colour to the background.

    Fix: for each affected sprite, borrow the alpha mask from row 0 of the
    same grid column (same pixel dimensions, same golden-ring outline).
    The outline is identical across all cells — only the interior differs.
    """
    FIX_INDICES = {3, 4, 5, 7, 9, 12, 13}

    img = Image.open(src_path).convert("RGBA")
    arr = np.array(img)
    bg = _find_bg_color(arr)

    tol = 10
    mask = np.any(np.abs(arr[:, :, :3].astype(int) - bg.astype(int)) > tol, axis=2)
    row_counts = np.sum(mask, axis=1)
    col_counts = np.sum(mask, axis=0)
    h_gaps = _find_gaps(row_counts)
    v_gaps = _find_gaps(col_counts)
    row_cells = _cells_from_gaps(h_gaps, ROWS)
    col_cells = _cells_from_gaps(v_gaps, COLS)

    # Build a reference alpha mask per column from row 0
    ref_masks: dict[int, np.ndarray] = {}
    for ci in range(COLS):
        cs, ce = col_cells[ci]
        rs_ref, re_ref = row_cells[0]
        ref_cell = arr[rs_ref:re_ref + 1, cs:ce + 1]
        ref_processed = remove_yellow_bg(ref_cell.copy(), bg)
        ref_masks[ci] = ref_processed[:, :, 3] > 0

    pad = 10

    for idx in sorted(FIX_INDICES):
        row = idx // COLS
        col = idx % COLS
        rs, re = row_cells[row]
        cs, ce = col_cells[col]

        cell = arr[rs:re + 1, cs:ce + 1].copy()
        cell[~ref_masks[col], 3] = 0

        result = Image.fromarray(cell)
        bbox = result.getbbox()
        if bbox is None:
            print(f"  [{idx:2d}] {NAMES[idx]}: EMPTY - skipped")
            continue

        cw, ch = ce - cs + 1, re - rs + 1
        bx1 = max(0, bbox[0] - pad)
        by1 = max(0, bbox[1] - pad)
        bx2 = min(cw, bbox[2] + pad)
        by2 = min(ch, bbox[3] + pad)

        cropped = result.crop((bx1, by1, bx2, by2))
        out = f"eye-{idx:02d}-{NAMES[idx]}.png"
        cropped.save(out)
        print(f"  {out:40s}  {cropped.size[0]:4d}x{cropped.size[1]:<4d}  (fixed)")


if __name__ == "__main__":
    extract_sprites()
    _fix_yellow_sprites()
