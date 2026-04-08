# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, importlib, re, subprocess, pkgutil
import snippets.sensors as sensors_pkg
from snippets.config import SENSOR_INDEX

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

        for attr in ["MIN_GAIN", "MAX_GAIN", "MIN_EXPOSURE", "MAX_EXPOSURE", 
                     "VIRT_GAIN_MIN", "VIRT_GAIN_MAX", "RAW_BPP"]:
            setattr(self, attr, getattr(mod, attr))
        
        self.EXACT_RAW_SIZE = self.WIDTH * self.HEIGHT * self.RAW_BPP
        self.extensions = getattr(mod, "EXTENSIONS", {})

    def get_runtime_ctrls(self, target_us, gain):
        return self.raw_config.get_runtime_ctrls(target_us, gain, self)

    def _find_nodes(self):
        found_count = 0
        for i in range(10):
            path = f"/dev/media{i}"
            if not os.path.exists(path): continue
            out = subprocess.run(f"media-ctl -d {path} -p", shell=True, capture_output=True, text=True).stdout
            if self.SENSOR_NAME.lower() in out.lower():
                if found_count == SENSOR_INDEX:
                    try:
                        sub = re.search(rf"{self.SENSOR_NAME}.*?device node name\s+(/dev/v4l-subdev\d+)", out, re.S).group(1)
                        vid = re.search(r"(?:unicam-image|video-sensor|vi-output).*?device node name\s+(/dev/video\d+)", out, re.S).group(1)
                        return path, sub, vid
                    except: continue
                else: found_count += 1
        raise RuntimeError(f"Sensor {self.SENSOR_NAME} not found.")

    def _scan_v4l2_controls(self):
        inventory = {}
        out = subprocess.check_output(f"v4l2-ctl -d {self.s_node} --list-ctrls", shell=True, text=True)
        int_p = re.compile(r"^\s*([a-zA-Z0-9_]+)\s+.*?min=(-?\d+)\s+max=(-?\d+).*\s+value=(-?\d+)")
        for line in out.splitlines():
            m = int_p.search(line)
            if m:
                inventory[m.group(1)] = {'min': int(m.group(2)), 'max': int(m.group(3)), 'val': int(m.group(4))}
        return inventory

def _init_factory():
    detected_entities = []
    for i in range(5):
        path = f"/dev/media{i}"
        if os.path.exists(path):
            out = subprocess.run(f"media-ctl -d {path} -p", shell=True, capture_output=True, text=True).stdout
            names = re.findall(r"Entity\s+\d+:\s+([a-zA-Z0-9\-_ ]+)\s+\(", out)
            detected_entities.extend([n.strip() for n in names])

    for loader, module_name, is_pkg in pkgutil.iter_modules(sensors_pkg.__path__):
        if module_name == "sensor": continue
        mod = importlib.import_module(f"snippets.sensors.{module_name}")
        target_entity = getattr(mod, "MEDIA_ENTITY_NAME", None)
        if target_entity and any(target_entity in ent for ent in detected_entities):
            if hasattr(mod, "get_runtime_ctrls"):
                return SensorContainer(mod)
    raise RuntimeError("No matching sensor config found.")

sensor = _init_factory()
