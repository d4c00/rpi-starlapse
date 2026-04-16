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
            
            print(f"[*] Hardware Limits Loaded for {getattr(self, 'SENSOR_NAME', 'Unknown')}:")
            if hasattr(self, 'HW_MIN_LINES'):
                print(f"    - Exposure (Lines): min={self.HW_MIN_LINES}, max={self.HW_MAX_LINES}")
                if hasattr(self, '_calculate_phys_exposure'):
                    min_s = self._calculate_phys_exposure(self.HW_MIN_LINES, mode="min")
                    max_s = getattr(self, 'MAX_EXPOSURE', self._calculate_phys_exposure(self.HW_MAX_LINES, mode="max"))
                    min_str = f"{min_s:.6f}s ({min_s*1000:.3f}ms)" if min_s < 1 else f"{min_s:.3f}s"
                    max_str = f"{max_s:.6f}s ({max_s*1000:.3f}ms)" if max_s < 1 else f"{max_s:.3f}s"
                    print(f"    - Exposure (Time):  min={min_str}, max={max_str}")

            if hasattr(self, 'MIN_GAIN'):
                print(f"    - Analogue Gain: min={self.MIN_GAIN}, max={self.MAX_GAIN}")

def _init_factory():
    pkg_path = os.path.dirname(__file__)
    driver_files = sorted([f[:-3] for f in os.listdir(pkg_path) if f.endswith(".py") and f != "__init__.py"])
    target_driver = driver_files[SENSOR_INDEX]
    spec = importlib.util.spec_from_file_location(target_driver, os.path.join(pkg_path, f"{target_driver}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return BaseSensor(mod)

sensor = _init_factory()