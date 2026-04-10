from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.hmi.application import DiffConfig, compare_images  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    img_a = cv2.imread(args.a)
    img_b = cv2.imread(args.b)

    result = compare_images(img_a, img_b, DiffConfig())
    cv2.imwrite(os.path.join(args.out, "diff_mask.png"), result["debug_images"]["diff_mask"])
    cv2.imwrite(os.path.join(args.out, "overlay.png"), result["debug_images"]["overlay"])

    print("Diffs:", result["diffs"])
    print("Toggle changes:", result["toggle_changes"])


if __name__ == "__main__":
    main()
