import argparse
from collections import defaultdict
import os
import os.path as osp
# https://stackoverflow.com/a/78898726
from pytubefix import YouTube
# from pytube import YouTube

from momaapi import MOMA


def download(moma_dir: str):
    os.makedirs(moma_dir, exist_ok=True)
    moma = MOMA(moma_dir)

    ids_act = moma.get_ids_act()
    N = len(ids_act)
    failures: dict[str, list[str]] = defaultdict(list)
    base_dir = osp.join(moma_dir, f"videos/raw")
    for i, id_act in enumerate(ids_act, start=1):
        filename = f"{id_act}.mp4"
        path = osp.join(base_dir, filename)
        url = f"https://youtu.be/{id_act}"
        progress = f"[{i}/{N}]\t"
        if osp.exists(path):
            print(f"{progress}skipping downloaded video {url} at {path}")
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

        except Exception as e:
            failure = str(e)
            print(f"\t\tFAILED: {failure}")
            _id, reason = failure.split(" ", maxsplit=1)
            assert _id == f"\033[91m{id_act}", list(_id)
            failures[reason].append(id_act)

    print("Download complete.")
    F = sum(len(ids_act) for ids_act in failures.values())
    if F > 0:
        print(f"{F}/{N} videos failed to download.")
        for reason, ids_act in failures.items():
            print(f"  {len(ids_act)} videos with error \"[ID] {reason}\":")
            for id_act in ids_act:
                print(f"    {id_act}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--moma-dir", type=str, default=".data")
    args = parser.parse_args()
    moma_dir: str = args.moma_dir

    download(moma_dir=moma_dir)
