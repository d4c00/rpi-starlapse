# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import time
import fcntl
import mmap
import select
import ctypes
import videodev2 as v4l2

from snippets.sensors import sensor
from snippets.utils import setup_logger

logger = setup_logger("HW_DRV")


class V4L2Camera:
    @staticmethod
    def probe_resolution():
        return sensor.WIDTH, sensor.HEIGHT

    def __init__(self):
        self.v_fd = os.open(sensor.v_node, os.O_RDWR | os.O_NONBLOCK)
        sensor.v_fd = self.v_fd

        req = v4l2.v4l2_requestbuffers()
        req.count = 1
        req.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        req.memory = v4l2.V4L2_MEMORY_MMAP
        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_REQBUFS, req)

        self.buffers = []
        buf = v4l2.v4l2_buffer()
        buf.type = req.type
        buf.memory = req.memory
        buf.index = 0
        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QUERYBUF, buf)
        
        mm = mmap.mmap(
            self.v_fd, buf.length,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=buf.m.offset
        )
        self.buffers.append(mm)
        
        self.running = True
        logger.info("V4L2 Hybrid-Snapshot Mode Initialized.")

    def __del__(self):
        if hasattr(self, "v_fd"):
            try:
                fcntl.ioctl(self.v_fd, v4l2.VIDIOC_STREAMOFF, ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE))
            except: pass
            for b in self.buffers: b.close()
            os.close(self.v_fd)

    def capture_to_path(self, target_us, gain, out_path):
        if hasattr(sensor, "apply_runtime"):
            sensor.apply_runtime(target_us, gain, sensor)

        t0 = time.perf_counter()

        buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
        buf = v4l2.v4l2_buffer()
        buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        buf.memory = v4l2.V4L2_MEMORY_MMAP
        buf.index = 0

        try:
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QBUF, buf)
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_STREAMON, buf_type)
        except Exception as e:
            logger.error(f"Failed to start snapshot: {e}")
            return False, 0

        timeout_sec = (target_us / 1e6) + 0.5
        ready = select.select([self.v_fd], [], [], timeout_sec)[0]

        if not ready:
            logger.error(f"Capture Timeout ({timeout_sec}s)")
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_STREAMOFF, buf_type)
            return False, 0

        try:
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_DQBUF, buf)

            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_STREAMOFF, buf_type)
        except OSError as e:
            logger.error(f"Capture failed during DQBUF: {e}")
            return False, 0

        elapsed = (time.perf_counter() - t0) * 1000

        mm = self.buffers[0]
        mm.seek(0)
        data = mm.read(sensor.EXACT_RAW_SIZE)

        ok = len(data) >= sensor.EXACT_RAW_SIZE
        if ok:
            with open(out_path, "wb") as f:
                f.write(data)
        else:
            logger.error("Incomplete data")

        return ok, elapsed
