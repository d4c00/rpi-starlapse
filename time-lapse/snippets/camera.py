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
            for cmd in sensor.get_init_cmds():
                self._run(cmd)

    def _run(self, cmd):
        try:
            return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd}\nError: {e.output}")
            raise

    def capture_to_path(self, target_us, gain, out_path):
        runtime_cmds = sensor.get_runtime_cmds(target_us, gain)
        for cmd in runtime_cmds:
            self._run(cmd)

        capture_cmd = sensor.get_capture_cmd(out_path)
        
        t0 = time.perf_counter()
        self._run(capture_cmd)
        
        return True, (time.perf_counter() - t0) * 1000
