import json
import math
import os
from typing import Any, Optional

import ffmpeg
from torchvision import io
from tqdm import tqdm

from .utils import assert_type


class VideoProcessor:
    """
    - all: unfiltered, untrimmed videos
    - raw: filtered, untrimmed videos
    - activity
    - sub-activity
    - higher-order interaction
    """
    def __init__(self, dir_moma: str, log_level: str = "quiet"):
        with open(os.path.join(dir_moma, "anns/anns.json"), "r") as f:
            anns: list[dict] = json.load(f)
        assert isinstance(anns, list)

        self.anns = { ann["activity"]["id"]: ann for ann in anns }

        self.log_level = log_level

        # paths
        self.dir_moma = dir_moma

        self.raw_dir = os.path.join(self.dir_moma, "videos/raw")

        self.activities_dir = os.path.join(self.dir_moma, "videos/activity")
        os.makedirs(self.activities_dir, exist_ok=True)

        self.sub_activities_dir = os.path.join(self.dir_moma, "videos/sub_activity")
        os.makedirs(self.sub_activities_dir, exist_ok=True)

        self.hoi_dir = os.path.join(self.dir_moma, "videos/interaction")
        os.makedirs(self.hoi_dir, exist_ok=True)

        self.hoi_videos_dir = os.path.join(self.dir_moma, "videos/interaction_video")
        os.makedirs(self.hoi_videos_dir, exist_ok=True)

        self.hoi_frames_dir = os.path.join(self.dir_moma, "videos/interaction_frames")
        os.makedirs(self.hoi_frames_dir, exist_ok=True)
        self.hoi_timestamps_path = os.path.join(self.hoi_frames_dir, "timestamps.json")

    def update_hoi_timestamps(
            self,
            new_timestamps: dict[str, list[tuple[str, float]]]
    ):
        # WARNING: this function is not thread safe
        saved_timestamps: dict[str, list[tuple[str, float]]] = {}
        if os.path.exists(self.hoi_timestamps_path):
            with open(self.hoi_timestamps_path) as f:
                s = f.read()
                if len(s) > 0:
                    saved_timestamps = assert_type(json.loads(s), dict)

                    # validation
                    for k, v in saved_timestamps.items():
                        assert isinstance(k, str)
                        assert isinstance(v, list)
                        for id, t in v:
                            assert isinstance(id, str)
                            assert isinstance(t, float)

        for key, timestamps in new_timestamps.items():
            if key in saved_timestamps:
                assert saved_timestamps[key] == timestamps
            else:
                saved_timestamps[key] = timestamps

        with open(self.hoi_timestamps_path, "w") as f:
            json.dump(saved_timestamps, f, indent=2, sort_keys=True)

    def sample_image(
            self,
            path_src: str,
            path_trg: str,
            time: float,
    ):
        ffmpeg.input(path_src, ss=time) \
            .output(path_trg, vframes=1, loglevel=self.log_level) \
            .run()
        # strange bug: sometimes ffmpeg does not read the last frame!
        if not os.path.isfile(path_trg):
            video = io.read_video(path_src, start_pts=time - 1, pts_unit="sec")
            video = video[0][-1].permute(2, 0, 1)
            io.write_jpeg(video, path_trg, quality=50)

    def trim_video(
            self,
            path_src: str,
            path_trg: str,
            start: float,
            end: float,
            resize: Optional[int] = None,
    ):
        trimmed = ffmpeg.input(path_src).video \
            .trim(start=start, end=end) \
            .setpts("PTS-STARTPTS")

        if resize is not None:
            probe = ffmpeg.probe(path_src)
            video_stream = next(
                stream for stream in probe["streams"]
                if stream["codec_type"] == "video"
            )
            width = int(video_stream["width"])
            height = int(video_stream["height"])

            if width < height:
                trimmed = trimmed.filter("scale", resize, -2)
            else:
                trimmed = trimmed.filter("scale", -2, resize)

        trimmed.output(path_trg, loglevel=self.log_level).run()

    def trim_activity(
            self,
            id: str,
            resize: Optional[int] = None,
            overwrite: bool = False,
    ) -> str:
        ann = self.anns[id]
        ann_act: dict[str, Any] = assert_type(ann["activity"], dict)
        filename = assert_type(ann["file_name"], str)
        path_src = os.path.join(self.raw_dir, filename)
        path_trg = os.path.join(self.activities_dir, filename)
        assert os.path.exists(path_src)
        if not os.path.exists(path_trg) or overwrite:
            start = assert_type(ann_act["start_time"], float)
            end = assert_type(ann_act["end_time"], float)
            self.trim_video(
                path_src=path_src,
                path_trg=path_trg,
                start=start,
                end=end,
                resize=resize,
            )
        return path_trg

    def trim_sub_activity(
            self,
            id: str,
            resize: Optional[int] = None,
            overwrite: bool = False,
    ) -> list[str]:
        paths_trg: list[str] = []

        ann = self.anns[id]
        filename = assert_type(ann["file_name"], str)

        path_src = os.path.join(self.raw_dir, filename)
        assert os.path.exists(path_src)

        sub_activities: list[dict] = assert_type(ann["activity"]["sub_activities"], list)
        for ann_sact in tqdm(sub_activities):
            sact_id = assert_type(ann_sact['id'], str)
            path_trg = os.path.join(self.sub_activities_dir, f"{sact_id}.mp4")
            if not os.path.exists(path_trg) or overwrite:
                start = assert_type(ann_sact["start_time"], float)
                end = assert_type(ann_sact["end_time"], float)
                self.trim_video(
                    path_src=path_src,
                    path_trg=path_trg,
                    start=start,
                    end=end,
                    resize=resize,
                )
            paths_trg.append(path_trg)

        return paths_trg

    def trim_hoi(
            self,
            id: str,
            duration: int = 1,
            resize: Optional[int] = None,
            overwrite: bool = False,
    ) -> list[str]:
        paths_trg: list[str] = []

        ann = self.anns[id]
        filename = assert_type(ann["file_name"], str)
        path_src = os.path.join(self.raw_dir, filename)
        assert os.path.exists(path_src)

        anns_hoi: list[dict] = sorted([
            ann_hoi
            for ann_sact in assert_type(ann["activity"]["sub_activities"], list)
            for ann_hoi in assert_type(ann_sact["higher_order_interactions"], list)
        ], key=lambda x: x["time"])
        for ann_hoi in tqdm(anns_hoi):
            hoi_id = assert_type(ann_hoi['id'], str)
            path_trg = os.path.join(self.hoi_videos_dir, f"{hoi_id}.mp4")
            if not os.path.exists(path_trg) or overwrite:
                if ann_hoi["time"] - duration / 2 < 0:
                    start = 0
                    end = duration
                elif ann_hoi["time"] + duration / 2 > ann["duration"]:
                    end = ann["duration"]
                    start = end - duration
                else:
                    start = ann_hoi["time"] - duration / 2
                    end = start + duration
                assert math.isclose(end - start, duration, rel_tol=1e-4), \
                    f"{ann_hoi['time']} -> [{start}, {end}) ({duration}s) from [0, {ann['duration']})"
                self.trim_video(
                    path_src=path_src,
                    path_trg=path_trg,
                    start=start,
                    end=end,
                    resize=resize,
                )
            paths_trg.append(path_trg)

        return paths_trg

    def sample_hoi(self, id: str, overwrite: bool = False) -> list[str]:
        paths_trg: list[str] = []

        ann = self.anns[id]
        filename = assert_type(ann["file_name"], str)
        path_src = os.path.join(self.raw_dir, filename)
        assert os.path.exists(path_src)

        anns_hoi: list[dict] = sorted([
            ann_hoi
            for ann_sact in assert_type(ann["activity"]["sub_activities"], list)
            for ann_hoi in assert_type(ann_sact["higher_order_interactions"], list)
        ], key=lambda x: x["time"])
        for ann_hoi in tqdm(anns_hoi):
            hoi_id = assert_type(ann_hoi['id'], str)
            path_trg = os.path.join(self.hoi_dir, f"{hoi_id}.jpg")
            if not os.path.exists(path_trg) or overwrite:
                time = assert_type(ann_hoi["time"], float)
                self.sample_image(
                    path_src=path_src,
                    path_trg=path_trg,
                    time=time,
                )
            paths_trg.append(path_trg)

        return paths_trg

    def sample_hoi_frames(
            self,
            id: str,
            num_frames: int = 5,
            overwrite: bool = False,
    ) -> list[str]:
        assert num_frames > 0
        assert num_frames % 2 == 1  # odd number

        paths_trg_frames: list[str] = []

        ann = self.anns[id]
        filename = assert_type(ann["file_name"], str)
        path_src = os.path.join(self.raw_dir, filename)
        assert os.path.exists(path_src)

        new_timestamps: dict[str, list[tuple[str, float]]] = {}
        anns_sact = assert_type(ann["activity"]["sub_activities"], list)
        for ann_sact in tqdm(anns_sact):
            anns_hoi = ann_sact["higher_order_interactions"]
            anns_hoi = sorted(anns_hoi, key=lambda x: x["time"])
            for i, ann_hoi in enumerate(anns_hoi):
                hoi_id = assert_type(ann_hoi['id'], str)

                now = assert_type(ann_hoi["time"], float)
                if i == 0:
                    next_time = assert_type(anns_hoi[i+1]["time"], float)
                    delta_right = (next_time - now) / num_frames
                    delta_left = delta_right
                elif i == len(anns_hoi) - 1:
                    prev_time = assert_type(anns_hoi[i-1]["time"], float)
                    delta_left = (now - prev_time) / num_frames
                    delta_right = delta_left
                else:
                    next_time = assert_type(anns_hoi[i+1]["time"], float)
                    prev_time = assert_type(anns_hoi[i-1]["time"], float)
                    delta_left = (now - prev_time) / num_frames
                    delta_right = (next_time - now) / num_frames

                timestamps: list[tuple[str, float]] = []
                for j in range(num_frames // 2):
                    # left
                    id_hoi = f"{ann_hoi['id']}_l{j+1}"
                    time = now - delta_left * (j + 1)
                    if time >= 0:
                        timestamps.append((id_hoi, time))
                    # right
                    id_hoi = f"{ann_hoi['id']}_r{j+1}"
                    time = now + delta_right * (j + 1)
                    if time < ann["duration"]:
                        timestamps.append((id_hoi, time))
                timestamps.sort(key=lambda x: x[1])
                new_timestamps[hoi_id] = timestamps

                for id_hoi, time in timestamps:
                    path_trg = os.path.join(self.hoi_frames_dir, f"{id_hoi}.jpg")
                    if not os.path.exists(path_trg) or overwrite:
                        self.sample_image(
                            path_src=path_src,
                            path_trg=path_trg,
                            time=time,
                        )
                    paths_trg_frames.append(path_trg)

        self.update_hoi_timestamps(new_timestamps)

        return paths_trg_frames
