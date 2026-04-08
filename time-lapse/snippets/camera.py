# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import time
import subprocess
import numpy as np
from snippets.sensors import sensor
from snippets.utils import setup_logger

logger = setup_logger("HW_DRV")

class V4L2Camera:
    @staticmethod
    def probe_resolution():
        return sensor.WIDTH, sensor.HEIGHT

    def __init__(self):
        self._run(f"media-ctl -d {sensor.m_node} -V \"'{sensor.MEDIA_ENTITY_NAME}':0 [fmt:{sensor.MEDIA_CTL_FMT}/{sensor.WIDTH}x{sensor.HEIGHT}]\"")
        self._run(f"v4l2-ctl -d {sensor.v_node} --set-fmt-video=width={sensor.WIDTH},height={sensor.HEIGHT},pixelformat={sensor.V4L2_PIXELFORMAT}")

        if sensor.extensions:
            ext_cmds = [f"{k}={v}" for k, v in sensor.extensions.items() if k in sensor.hw_inventory]
            if ext_cmds:
                self._run(f"v4l2-ctl -d {sensor.s_node} --set-ctrl={','.join(ext_cmds)}")

    def _run(self, cmd):
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)

    def capture_to_path(self, target_us, gain, out_path):
        req_vmax = int((target_us / 1000.0 * sensor.pixel_rate) / (1000 * sensor.hmax))

        ctrls_to_set = sensor.raw_config.get_runtime_ctrls(req_vmax, gain, sensor)

        if ctrls_to_set:
            cmd_str = ",".join([f"{k}={v}" for k, v in ctrls_to_set.items()])
            self._run(f"v4l2-ctl -d {sensor.s_node} --set-ctrl={cmd_str}")

        t0 = time.perf_counter()
        self._run(f"v4l2-ctl -d {sensor.v_node} --stream-mmap --stream-count=1 --stream-to={out_path}")
        return True, (time.perf_counter() - t0) * 1000
