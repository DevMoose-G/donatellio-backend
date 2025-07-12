import os
from typing import List

import cv2


def extract_frames(video_path: str, output_dir: str) -> List[str]:
    # open the video file
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video_path}")

    # total number of frames in the video
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # choose frame indices: first, middle, last
    indices = [0, total_frames // 2, total_frames - 1]

    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, frame_no in enumerate(indices, start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if not ret:
            print(f"⚠️  Frame {frame_no} could not be read")
            continue
        out_path = os.path.join(output_dir, f"frame_{i}.jpg")
        paths.append(out_path)
        cv2.imwrite(out_path, frame)
        print(f"Saved frame {i} (#{frame_no}) → {out_path}")

    cap.release()

    return paths
