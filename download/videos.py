import argparse
import os
import os.path as osp
# https://stackoverflow.com/a/78898726
from pytubefix import YouTube
# from pytube import YouTube

from momaapi import MOMA


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--dir-moma", type=str, default=".data")
    args = parser.parse_args()
    dir_moma: str = args.dir_moma

    os.makedirs(dir_moma, exist_ok=True)
    moma = MOMA(args.dir_moma)

    ids_act = moma.get_ids_act()
    N = len(ids_act)
    for i, id_act in enumerate(ids_act, start=1):
        path = osp.join(dir_moma, f"videos/raw/{id_act}.mp4")
        url = f"https://youtu.be/{id_act}"
        progress = f"[{i}/{N}]\t"
        if osp.isdir(path):
            already_downloaded = os.listdir(path)
            if len(already_downloaded) > 0:
                assert len(already_downloaded) == 1
                print(f"{progress}skipping downloaded video {url} at {already_downloaded[0]}")
                continue
        print(f"{progress}downloading video from {url} to {path} ...")
        try:
            # https://stackoverflow.com/a/76588698
            yt = YouTube(url, use_oauth=True)

            # fmt: off
            yt.streams\
                .filter(progressive=True, file_extension="mp4")\
                .order_by("resolution")\
                .desc()\
                .first()\
                .download(path) # type: ignore
            # fmt: on
        except Exception as e:
            print(f"\t\tFAILED: {e}")


if __name__ == "__main__":
    main()
