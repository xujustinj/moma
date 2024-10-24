import argparse
from collections import defaultdict
import os
import os.path as osp
from typing import Optional

# https://stackoverflow.com/a/78898726
from pytubefix import YouTube
# from pytube import YouTube

from momaapi import MOMA
from preprocess import VideoProcessor


def download(
        moma_dir: str,
        skip_missing: bool = False,
) -> tuple[set[str], dict[str, set[str]]]:
    os.makedirs(moma_dir, exist_ok=True)
    moma = MOMA(moma_dir)

    ids_act = moma.get_ids_act()
    N = len(ids_act)
    failures: dict[str, set[str]] = defaultdict(set)
    successes: set[str] = set()
    base_dir = osp.join(moma_dir, f"videos/raw")
    for i, act_id in enumerate(ids_act, start=1):
        filename = f"{act_id}.mp4"
        path = osp.join(base_dir, filename)
        url = f"https://youtu.be/{act_id}"
        progress = f"[{i}/{N}]\t"
        if osp.exists(path):
            if not skip_missing: # don't bother logging since we skip everything
                print(f"{progress}skipping downloaded video {url} at {path}")
            successes.add(act_id)
            continue

        if skip_missing:
            continue

        print(f"{progress}downloading video from {url} to {path} ...")
        try:
            # https://stackoverflow.com/a/76588698
            yt = YouTube(url, use_oauth=True)

            stream = yt.streams\
                .filter(progressive=True, file_extension="mp4")\
                .get_highest_resolution()

            assert stream is not None
            print(f"\t\tusing highest MP4 quality {stream.resolution}")
            stream.download(path, filename=filename)
            successes.add(act_id)

        except Exception as e:
            failure = str(e)
            print(f"\t\tFAILED: {failure}")
            _id, reason = failure.split(" ", maxsplit=1)
            assert _id == f"\033[91m{act_id}", list(_id)
            failures[reason].add(act_id)

    print("Download complete.")
    F = sum(len(ids_act) for ids_act in failures.values())
    if F > 0:
        print(f"{F}/{N} videos failed to download.")
        for reason, ids_act in failures.items():
            print(f"  {len(ids_act)} videos with error \"[ID] {reason}\":")
            for act_id in sorted(ids_act):
                print(f"    {act_id}")

    return successes, failures


def preprocess(moma_dir: str, act_ids: set[str], resize: Optional[int] = 320):
    processor = VideoProcessor(moma_dir)

    N = len(act_ids)
    for i, act_id in enumerate(sorted(act_ids), start=1):
        progress = f"{act_id} [{i}/{N}]\t"
        print(f"{progress}trimming activity")
        processor.trim_activity(act_id, resize=resize)
        print(f"{progress}trimming sub-activities")
        processor.trim_sub_activity(act_id, resize=resize)
        print(f"{progress}trimming high-level interactions")
        processor.trim_hoi(act_id, resize=resize)
        print(f"{progress}generating high-level interaction frames")
        processor.sample_hoi(act_id)
        processor.sample_hoi_frames(act_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--moma-dir", type=str, default=".data")
    args = parser.parse_args()
    moma_dir: str = args.moma_dir

    successes, _ = download(moma_dir=moma_dir, skip_missing=True)
    preprocess(moma_dir=moma_dir, act_ids=successes)
