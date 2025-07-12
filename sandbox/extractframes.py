import cv2
import os

def extract_frames(video_path: str, output_dir: str):
    # open the video file
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video_path}")

    # total number of frames in the video
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # choose frame indices: first, middle, last
    indices = [0, total_frames // 3, 2 * total_frames // 3, total_frames - 1]
    cap.release()

    os.makedirs(output_dir, exist_ok=True)
    for i, frame_no in enumerate(indices, start=1):
        cap = cv2.VideoCapture(video_path)
        ok = cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        assert ok
        ret, frame = cap.read()
        if not ret:
            print(f"⚠️  Frame {frame_no} could not be read")
            continue
        out_path = os.path.join(output_dir, f"frame_{i}.jpg")
        cv2.imwrite(out_path, frame)
        cap.release()
        print(f"Saved frame {i} (#{frame_no}) → {out_path}")

    cap.release()

if __name__ == "__main__":
    extract_frames("golem-nobg-360.mp4", "frames_golem_nobg")
