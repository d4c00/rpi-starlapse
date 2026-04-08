# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, importlib, re, subprocess, pkgutil
import snippets.sensors as sensors_pkg
from snippets.config import SENSOR_INDEX

class SensorContainer:
    def __init__(self, mod):
        self.raw_config = mod

        for attr in dir(mod):
            if not attr.startswith("__"):
                setattr(self, attr, getattr(mod, attr))
        self.m_node, self.s_node, self.v_node = self._find_nodes()
        self.hw_inventory = mod.parse_hw_inventory(self)

    def _find_nodes(self):
        for i in range(10):
            path = f"/dev/media{i}"
            if not os.path.exists(path): continue
            out = subprocess.run(f"media-ctl -d {path} -p", shell=True, capture_output=True, text=True).stdout
            if self.SENSOR_NAME.lower() in out.lower():
                try:
                    sub = re.search(rf"{self.SENSOR_NAME}.*?device node name\s+(/dev/v4l-subdev\d+)", out, re.S).group(1)
                    vid = re.search(r"(?:unicam-image|video-sensor|vi-output|bm2835).*?device node name\s+(/dev/video\d+)", out, re.S).group(1)
                    return path, sub, vid
                except: continue
        raise RuntimeError(f"Sensor '{self.SENSOR_NAME}' not found.")

def _init_factory():
    entities = ""
    for i in range(5):
        p = f"/dev/media{i}"
        if os.path.exists(p):
            entities += subprocess.run(f"media-ctl -d {p} -p", shell=True, capture_output=True, text=True).stdout

    for _, module_name, _ in pkgutil.iter_modules(sensors_pkg.__path__):
        if module_name == "sensor": continue
        mod = importlib.import_module(f"snippets.sensors.{module_name}")
        if getattr(mod, "MEDIA_ENTITY_NAME", "N/A") in entities:
            return SensorContainer(mod)
    raise RuntimeError("No matching sensor config.")

sensor = _init_factory()
