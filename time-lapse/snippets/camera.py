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
        if hasattr(sensor, "get_init_cmds"):
            for cmd in sensor.get_init_cmds():
                self._run(cmd)

        self.stream_proc = subprocess.Popen(
            f"v4l2-ctl -d {sensor.v_node} --stream-mmap --stream-count=0 --stream-to=-",
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )

    def __del__(self):
        if hasattr(self, 'stream_proc'):
            self.stream_proc.terminate()

    def _run(self, cmd):
        try:
            return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd}\nError: {e.output}")
            raise

    def capture_to_path(self, target_us, gain, out_path):
        runtime_cmds = sensor.get_runtime_cmds(
            target_us=target_us, 
            gain=gain, 
            container=sensor
        )
        for cmd in runtime_cmds:
            self._run(cmd)

        t0 = time.perf_counter()

        raw_data = self.stream_proc.stdout.read(sensor.EXACT_RAW_SIZE)
        
        if len(raw_data) == sensor.EXACT_RAW_SIZE:
            with open(out_path, 'wb') as f:
                f.write(raw_data)
            return True, (time.perf_counter() - t0) * 1000
        else:
            logger.error("Frame read incomplete or stream died.")
            return False, 0
