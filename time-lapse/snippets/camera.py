# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import time
import fcntl
import mmap
import select
import videodev2 as v4l2
import ctypes
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
        if hasattr(sensor, "apply_init"):
            sensor.apply_init(sensor)

        req = v4l2.v4l2_requestbuffers()
        req.count = 2
        req.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        req.memory = v4l2.V4L2_MEMORY_MMAP
        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_REQBUFS, req)

        self.buffers = []
        for i in range(req.count):
            buf = v4l2.v4l2_buffer()
            buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
            buf.memory = v4l2.V4L2_MEMORY_MMAP
            buf.index = i
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QUERYBUF, buf)
            mm = mmap.mmap(self.v_fd, buf.length, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=buf.m.offset)
            self.buffers.append(mm)
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QBUF, buf)

        buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_STREAMON, buf_type)
        self.running = True

    def __del__(self):
        if hasattr(self, 'running') and self.running:
            buf_type = ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_STREAMOFF, buf_type)
            for mm in self.buffers: mm.close()
            os.close(self.v_fd)
            self.running = False

    def capture_to_path(self, target_us, gain, out_path):
        if hasattr(sensor, "apply_runtime"):
            sensor.apply_runtime(target_us=target_us, gain=gain, container=sensor)
        t0 = time.perf_counter()
        r, _, _ = select.select((self.v_fd,), (), (), 2.0)
        if not r:
            logger.error("Timeout waiting for frame.")
            return False, 0
        buf = v4l2.v4l2_buffer()
        buf.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        buf.memory = v4l2.V4L2_MEMORY_MMAP
        try:
            fcntl.ioctl(self.v_fd, v4l2.VIDIOC_DQBUF, buf)
        except OSError as e:
            logger.error(f"DQBUF failed: {e}")
            return False, 0
        capture_elapsed_ms = (time.perf_counter() - t0) * 1000
        mm = self.buffers[buf.index]
        mm.seek(0)
        raw_data = mm.read(sensor.EXACT_RAW_SIZE)
        if len(raw_data) >= sensor.EXACT_RAW_SIZE:
            with open(out_path, 'wb') as f:
                f.write(raw_data[:sensor.EXACT_RAW_SIZE])
            ret = True
        else:
            logger.error("Frame read incomplete.")
            ret = False
        fcntl.ioctl(self.v_fd, v4l2.VIDIOC_QBUF, buf)
        return ret, capture_elapsed_ms
