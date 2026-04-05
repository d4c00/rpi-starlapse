# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import time
import subprocess
import re
import os
from snippets.sensors import sensor 
from snippets.utils import setup_logger

logger = setup_logger("HW_DRV")

class V4L2Camera:
    @staticmethod
    def _run(cmd):
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)

    @staticmethod
    def _find_nodes():
        for i in range(5):
            path = f"/dev/media{i}"
            if not os.path.exists(path):
                continue
            out = subprocess.run(f"media-ctl -d {path} -p", shell=True, capture_output=True, text=True).stdout
            if sensor.SENSOR_NAME in out.lower():
                sub = re.search(rf"{sensor.SENSOR_NAME}.*?device node name\s+(/dev/v4l-subdev\d+)", out, re.S).group(1)
                vid = re.search(r"unicam-image.*?device node name\s+(/dev/video\d+)", out, re.S).group(1)
                return path, sub, vid
        raise RuntimeError("Sensor not found")

    @staticmethod
    def probe_resolution(v_node="/dev/video0"):
        out = subprocess.check_output(f"v4l2-ctl -d {v_node} --get-fmt-video", shell=True, text=True)
        w = int(re.search(r"Width/Height\s+:\s+(\d+)/", out).group(1))
        h = int(re.search(r"Width/Height\s+:\s+\d+/(\d+)", out).group(1))
        return w, h

    def __init__(self):
        self.m_node, self.s_node, self.v_node = self._find_nodes()

        self._run(f"media-ctl -d {self.m_node} -V \"'{sensor.MEDIA_ENTITY_NAME}':0 [fmt:{sensor.MEDIA_CTL_FMT}/{sensor.WIDTH}x{sensor.HEIGHT}]\"")
        self._run(f"v4l2-ctl -d {self.v_node} --set-fmt-video=width={sensor.WIDTH},height={sensor.HEIGHT},pixelformat={sensor.V4L2_PIXELFORMAT}")

        self.width, self.height = self.probe_resolution(self.v_node)

        pr_out = self._run(f"v4l2-ctl -d {self.s_node} --get-ctrl=pixel_rate")
        self.pixel_rate = int(pr_out.split(':')[-1].strip())

        ctrls = self._run(f"v4l2-ctl -d {self.s_node} --list-ctrls")
        self.hblank = int(re.search(r"horizontal_blanking.*value=(\d+)", ctrls).group(1))
        self.hmax = self.width + self.hblank

        if sensor.HCG_CTRL_NAME:
            self._run(f"v4l2-ctl -d {self.s_node} --set-ctrl={sensor.HCG_CTRL_NAME}={sensor.HCG_VALUE}")
            logger.info(f"HCG enabled: {sensor.HCG_CTRL_NAME}={sensor.HCG_VALUE}")

        logger.info(f"Driver Ready: {self.v_node} | {self.width}x{self.height} | Sensor={sensor.SENSOR_NAME}")

    def capture_to_path(self, target_us, gain, out_path):
        target_ms = target_us / 1000.0
        req_vmax = int((target_ms * self.pixel_rate) / (1000 * self.hmax))

        self._run(
            f"v4l2-ctl -d {self.s_node} --set-ctrl="
            f"{sensor.VBLANK_CTRL_NAME}={req_vmax - self.height},"
            f"{sensor.EXPOSURE_CTRL_NAME}={req_vmax - 8},"
            f"{sensor.GAIN_CTRL_NAME}={int(gain)}"
        )
        t0 = time.perf_counter()
        self._run(f"v4l2-ctl -d {self.v_node} --stream-mmap --stream-count=1 --stream-to={out_path}")
        return True, (time.perf_counter() - t0) * 1000