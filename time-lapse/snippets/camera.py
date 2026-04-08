# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import time
import subprocess
from snippets.sensors import sensor
from snippets.utils import setup_logger

logger = setup_logger("HW_DRV")

class V4L2Camera:
    @staticmethod
    def probe_resolution():
        return sensor.WIDTH, sensor.HEIGHT

    def __init__(self):
        if hasattr(sensor.raw_config, "get_init_cmds"):
            init_cmds = sensor.raw_config.get_init_cmds(sensor)
            for cmd in init_cmds:
                self._run(cmd)

    def _run(self, cmd):
        try:
            return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd}\nError: {e.output}")
            raise

    def capture_to_path(self, target_us, gain, out_path):
        ctrls_list = sensor.get_runtime_ctrls(target_us, gain)

        if ctrls_list:
            for key, val in ctrls_list:
                self._run(f"v4l2-ctl -d {sensor.s_node} --set-ctrl={key}={val}")

        t0 = time.perf_counter()
        self._run(f"v4l2-ctl -d {sensor.v_node} --stream-mmap --stream-count=1 --stream-to={out_path}")
        return True, (time.perf_counter() - t0) * 1000
