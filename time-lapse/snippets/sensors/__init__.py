# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import importlib.util
from snippets.config import SENSOR_INDEX

class BaseSensor:
    def __init__(self, mod):
        self.mod = mod
        for name in dir(mod):
            if not name.startswith("__"):
                setattr(self, name, getattr(mod, name))
        if hasattr(self, "WIDTH") and hasattr(self, "HEIGHT") and hasattr(self, "BIT"):
            self.RAW_BPP = 2
            self.EXACT_RAW_SIZE = self.WIDTH * self.HEIGHT * self.RAW_BPP
        self.v_node, self.s_node = self.find_nodes()
        self.s_fd = os.open(self.s_node, os.O_RDWR | os.O_NONBLOCK)
        self.v_fd = None 
        self._refresh_hardware_limits()

    def __del__(self):
        if hasattr(self, 's_fd'): os.close(self.s_fd)

    def _refresh_hardware_limits(self):
        if hasattr(self, "get_v4l2_ctrls"):
            ctrls = self.get_v4l2_ctrls(self.s_fd)
            if 'exposure' in ctrls:
                self.HW_MIN_LINES = ctrls['exposure']['min']
                self.HW_MAX_LINES = ctrls['exposure']['max']
            if 'analogue_gain' in ctrls:
                self.MIN_GAIN = ctrls['analogue_gain']['min']
                self.MAX_GAIN = ctrls['analogue_gain']['max']

def _init_factory():
    pkg_path = os.path.dirname(__file__)
    driver_files = sorted([f[:-3] for f in os.listdir(pkg_path) if f.endswith(".py") and f != "__init__.py"])
    target_driver = driver_files[SENSOR_INDEX]
    spec = importlib.util.spec_from_file_location(target_driver, os.path.join(pkg_path, f"{target_driver}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return BaseSensor(mod)

sensor = _init_factory()
