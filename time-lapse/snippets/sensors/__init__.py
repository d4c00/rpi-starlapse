# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, importlib, re, subprocess

class SensorContainer:
    def __init__(self, mod):
        self.raw_config = mod
        self.SENSOR_NAME = mod.SENSOR_NAME
        self.WIDTH, self.HEIGHT = mod.WIDTH, mod.HEIGHT
        self.MEDIA_ENTITY_NAME = mod.MEDIA_ENTITY_NAME
        self.MEDIA_CTL_FMT = mod.MEDIA_CTL_FMT
        self.V4L2_PIXELFORMAT = mod.V4L2_PIXELFORMAT

        self.m_node, self.s_node, self.v_node = self._find_nodes()

        self.hw_inventory = self._scan_v4l2_controls()
        self.core = mod.CORE_MAPPING

        self._compute_physics()

        self.extensions = getattr(mod, "EXTENSIONS", {})

        gain_info = self.hw_inventory[self.core['gain']]
        self.MIN_GAIN = gain_info['min']
        self.MAX_GAIN = gain_info['max']
        self.REG_GAIN_MIN = self.MIN_GAIN
        self.REG_GAIN_MAX = self.MAX_GAIN

        try:
            self.VIRT_GAIN_MIN = mod.VIRT_GAIN_MIN
            self.VIRT_GAIN_MAX = mod.VIRT_GAIN_MAX
            self.EXP_OFFSET    = mod.EXP_OFFSET
            self.RAW_BPP       = mod.RAW_BPP
        except AttributeError as e:
            raise AttributeError(f"Missing mandatory config in {self.SENSOR_NAME}.py: {e}")

        self.EXACT_RAW_SIZE = self.WIDTH * self.HEIGHT * self.RAW_BPP

    def _find_nodes(self):
        for i in range(5):
            path = f"/dev/media{i}"
            if not os.path.exists(path): continue
            out = subprocess.run(f"media-ctl -d {path} -p", shell=True, capture_output=True, text=True).stdout
            if self.SENSOR_NAME.lower() in out.lower():
                sub = re.search(rf"{self.SENSOR_NAME}.*?device node name\s+(/dev/v4l-subdev\d+)", out, re.S).group(1)
                vid = re.search(r"(?:unicam-image|video-sensor|vi-output).*?device node name\s+(/dev/video\d+)", out, re.S).group(1)
                return path, sub, vid
        raise RuntimeError(f"Sensor {self.SENSOR_NAME} not found")

    def _scan_v4l2_controls(self):
        inventory = {}
        out = subprocess.check_output(f"v4l2-ctl -d {self.s_node} --list-ctrls", shell=True, text=True)
        int_p = re.compile(r"^\s*([a-zA-Z0-9_]+)\s+.*?min=(-?\d+)\s+max=(-?\d+).*\s+value=(-?\d+)")
        base_p = re.compile(r"^\s*([a-zA-Z0-9_]+)\s+.*?default=(-?\d+)\s+value=(-?\d+)")
        
        for line in out.splitlines():
            m = int_p.search(line)
            if m:
                inventory[m.group(1)] = {'min': int(m.group(2)), 'max': int(m.group(3)), 'val': int(m.group(4))}
                continue
            m_b = base_p.search(line)
            if m_b:
                inventory[m_b.group(1)] = {'min': 0, 'max': 1, 'val': int(m_b.group(3))}
        return inventory

    def _compute_physics(self):
        res = subprocess.check_output(f"v4l2-ctl -d {self.s_node} --get-ctrl={self.core['pixel_rate']}", shell=True, text=True)
        self.pixel_rate = int(res.split(':')[-1].strip())

        hblank_val = self.hw_inventory[self.core['hblank']]['val']
        self.hmax = self.WIDTH + hblank_val
        self.line_time = self.hmax / self.pixel_rate

        exp_range = self.hw_inventory[self.core['exposure']]
        self.MIN_EXPOSURE = exp_range['min'] * self.line_time
        self.MAX_EXPOSURE = exp_range['max'] * self.line_time

        self.BIAS_EXPOSURE = self.MIN_EXPOSURE

def _init_factory():
    mod = importlib.import_module("snippets.sensors.imx662")
    return SensorContainer(mod)

sensor = _init_factory()