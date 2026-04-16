# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import importlib.util
import fcntl
import videodev2 as v4l2
from snippets.config import SENSOR_INDEX


class BaseSensor:
    def __init__(self, mod, v_node, s_node):
        self.__dict__.update({
            k: getattr(mod, k) for k in dir(mod) if not k.startswith("__")
        })

        self.v_node, self.s_node = v_node, s_node
        self.v_fd = os.open(v_node, os.O_RDWR | os.O_NONBLOCK)
        self.s_fd = os.open(s_node, os.O_RDWR)

        if hasattr(self, "WIDTH"):
            self.EXACT_RAW_SIZE = self.WIDTH * self.HEIGHT * 2

        if hasattr(self, "apply_init"):
            self.apply_init(self)

        self.ctrls = self._get_ctrls()
        self._load_limits()

    def _get_ctrls(self):
        ctrls = {}
        q = v4l2.v4l2_queryctrl()
        q.id = v4l2.V4L2_CTRL_FLAG_NEXT_CTRL

        while True:
            try:
                fcntl.ioctl(self.s_fd, v4l2.VIDIOC_QUERYCTRL, q)
            except OSError:
                break

            if not (q.flags & v4l2.V4L2_CTRL_FLAG_DISABLED):
                name = bytes(q.name).split(b"\0")[0].decode().lower().replace(" ", "_")

                try:
                    g = v4l2.v4l2_control(id=q.id)
                    fcntl.ioctl(self.s_fd, v4l2.VIDIOC_G_CTRL, g)
                    val = g.value
                except OSError:
                    val = q.default_value

                ctrls[name] = dict(
                    id=q.id,
                    min=q.minimum,
                    max=q.maximum,
                    val=val
                )

            q.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL

        return ctrls

    def set_ctrl(self, name, val):
        c = self.ctrls[name]
        ctrl = v4l2.v4l2_control(id=c["id"], value=int(val))
        fcntl.ioctl(self.s_fd, v4l2.VIDIOC_S_CTRL, ctrl)

    def _line_to_sec(self, lines, mode="val"):
        if not hasattr(self, "PIXEL_RATE_VAL"):
            raise RuntimeError("PIXEL_RATE not ready")

        h = self.ctrls["horizontal_blanking"][mode]
        return (lines * (self.WIDTH + h)) / self.PIXEL_RATE_VAL

    def _load_limits(self):
        c = self.ctrls

        if "exposure" in c:
            self.HW_MIN_LINES = c["exposure"]["min"]
            self.HW_MAX_LINES = c["exposure"]["max"]

        if "analogue_gain" in c:
            self.MIN_GAIN = c["analogue_gain"]["min"]
            self.MAX_GAIN = c["analogue_gain"]["max"]

        if hasattr(self, "PIXEL_RATE_VAL"):
            v_max = c.get("vertical_blanking", {}).get("max", 1000)

            self.MIN_EXPOSURE = self._line_to_sec(self.HW_MIN_LINES, "min")
            self.MAX_EXPOSURE = self._line_to_sec(self.HEIGHT + v_max, "max")
            self.AE_MIN_US = int(self.MIN_EXPOSURE * 1e6)

        print(f"[*] Loaded {getattr(self,'SENSOR_NAME','Unknown')}")
        if hasattr(self, "MIN_EXPOSURE"):
            print(f"    Exposure: {self.MIN_EXPOSURE*1000:.3f} ~ {self.MAX_EXPOSURE*1000:.3f} ms")
            print(f"    Gain: {self.MIN_GAIN} ~ {self.MAX_GAIN}")

    def __del__(self):
        for fd in ("s_fd", "v_fd"):
            if hasattr(self, fd):
                os.close(getattr(self, fd))

def _init_factory():
    base = "/sys/class/video4linux"

    sensors, v_node = [], None

    for dev in sorted(os.listdir(base)):
        name_p = f"{base}/{dev}/name"
        if not os.path.exists(name_p):
            continue

        name = open(name_p).read().lower()

        if "subdev" in dev:
            sensors.append((name, f"/dev/{dev}"))

        elif "video" in dev:
            u = f"{base}/{dev}/device/uevent"
            if os.path.exists(u) and "unicam" in open(u).read().lower():
                v_node = f"/dev/{dev}"

    pkg = os.path.dirname(__file__)
    matches = []

    for f in os.listdir(pkg):
        if not f.endswith(".py") or f == "__init__.py":
            continue

        spec = importlib.util.spec_from_file_location(f[:-3], f"{pkg}/{f}")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)

        if hasattr(m, "SENSOR_NAME"):
            for name, node in sensors:
                if m.SENSOR_NAME in name:
                    matches.append((m, node, v_node))

    if not matches:
        raise RuntimeError("No sensor matched")

    m, s, v = matches[SENSOR_INDEX % len(matches)]
    print(f"[*] Using {m.SENSOR_NAME} @ {s}")

    return BaseSensor(m, v, s)

sensor = _init_factory()
