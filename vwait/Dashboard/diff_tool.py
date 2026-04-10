import argparse
import os
import cv2
from Dashboard.diff_engine import DiffConfig, compare_images


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True)
    ap.add_argument('--b', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    imgA = cv2.imread(args.a)
    imgB = cv2.imread(args.b)

    cfg = DiffConfig()
    result = compare_images(imgA, imgB, cfg)

    # save outputs
    cv2.imwrite(os.path.join(args.out, 'diff_mask.png'), result['debug_images']['diff_mask'])
    cv2.imwrite(os.path.join(args.out, 'overlay.png'), result['debug_images']['overlay'])

    print('Diffs:', result['diffs'])
    print('Toggle changes:', result['toggle_changes'])


if __name__ == '__main__':
    main()
