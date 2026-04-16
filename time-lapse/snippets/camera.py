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
        req.count = 2
        req.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        req.memory = v4l2.V4L2_MEMORY_MMAP
        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_REQBUFS, req)

        self.buffers = []
        for i in range(req.count):
            buf = v4l2.v4l2_buffer()
            buf.type = req.type
            buf.memory = req.memory
            buf.index = i

            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QUERYBUF, buf)

            mm = mmap.mmap(
                self.v_fd, buf.length,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=buf.m.offset
            )

            self.buffers.append(mm)
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QBUF, buf)

        fcntl.ioctl(
            self.v_fd,
            v4l2.VIDIOC_STREAMON,
            ctypes.c_int(req.type)
        )

        self.running = True

    def __del__(self):
        if getattr(self, "running", False):
            fcntl.ioctl(
                self.v_fd,
                v4l2.VIDIOC_STREAMOFF,
                ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
            )
            for b in self.buffers:
                b.close()
            os.close(self.v_fd)

    def capture_to_path(self, target_us, gain, out_path):
        if hasattr(sensor, "apply_runtime"):
            sensor.apply_runtime(target_us, gain, sensor)

        t0 = time.perf_counter()

        if not select.select([self.v_fd], [], [], 2.0)[0]:
            logger.error("Timeout")
            return False, 0

        buf = v4l2.v4l2_buffer()
        buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        buf.memory = v4l2.V4L2_MEMORY_MMAP

        try:
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_DQBUF, buf)
        except OSError as e:
            logger.error(f"DQBUF failed: {e}")
            return False, 0

        elapsed = (time.perf_counter() - t0) * 1000

        mm = self.buffers[buf.index]
        mm.seek(0)
        data = mm.read(sensor.EXACT_RAW_SIZE)

        ok = len(data) >= sensor.EXACT_RAW_SIZE
        if ok:
            with open(out_path, "wb") as f:
                f.write(data[:sensor.EXACT_RAW_SIZE])
        else:
            logger.error("Incomplete frame")

        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QBUF, buf)
        return ok, elapsed
