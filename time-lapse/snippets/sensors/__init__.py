# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import importlib
import importlib.util
import inspect
import subprocess
import re
from functools import partial
from snippets.config import SENSOR_INDEX

class BaseSensor:
    def __init__(self, mod):
        self.mod = mod
        for name in dir(mod):
            if not name.startswith("__"):
                setattr(self, name, getattr(mod, name))

        if hasattr(self, "WIDTH") and hasattr(self, "HEIGHT") and hasattr(self, "RAW_BPP"):
            self.EXACT_RAW_SIZE = self.WIDTH * self.HEIGHT * self.RAW_BPP
        self.v_node, self.s_node = self.find_nodes()
        self._refresh_hardware_limits()

    def _refresh_hardware_limits(self):
        try:
            out = subprocess.check_output(f"v4l2-ctl -d {self.s_node} --list-ctrls", shell=True, text=True)
            self.MIN_EXPOSURE = int(re.search(r"exposure.*?min=(\d+)", out).group(1))
            self.MAX_EXPOSURE = int(re.search(r"exposure.*?max=(\d+)", out).group(1))
            self.MIN_GAIN = int(re.search(r"analogue_gain.*?min=(\d+)", out).group(1))
            self.MAX_GAIN = int(re.search(r"analogue_gain.*?max=(\d+)", out).group(1)) 
        except:
            pass

def _init_factory():
    pkg_path = os.path.dirname(__file__)
    driver_files = sorted([f[:-3] for f in os.listdir(pkg_path) if f.endswith(".py") and f != "__init__.py"])
    target_driver = driver_files[SENSOR_INDEX]
    spec = importlib.util.spec_from_file_location(target_driver, os.path.join(pkg_path, f"{target_driver}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return BaseSensor(mod)

sensor = _init_factory()