# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import numpy as np
import math
import os
from snippets.config import AE_TARGET_LUMA

class AdaptiveExposureEngine:
    def __init__(self, reg_min, reg_max, virt_min, virt_max):
        self.target = AE_TARGET_LUMA
        self.ev = None
        self.min_energy = 1e-4

        self.velocity = 0.0 
        self.accel_factor = 1.0

        self.REG_MIN = reg_min
        self.REG_MAX = reg_max
        self.VIRT_GAIN_MIN = virt_min
        self.VIRT_GAIN_MAX = virt_max

    def _phys_to_virt_gain(self, reg_val):
        return 1.0 + (reg_val - self.REG_MIN) * (self.VIRT_GAIN_MAX - self.VIRT_GAIN_MIN) / (self.REG_MAX - self.REG_MIN)

    def _virt_to_phys_gain(self, virt_gain):
        reg = self.REG_MIN + (virt_gain - self.VIRT_GAIN_MIN) * (self.REG_MAX - self.REG_MIN) / (self.VIRT_GAIN_MAX - self.VIRT_GAIN_MIN)
        return int(np.clip(reg, self.REG_MIN, self.REG_MAX))

    def process_raw_frame(self, raw_path, width, height, current_us, current_reg_gain, max_us, min_us, max_reg_gain, raw_bits):
        current_virt_gain = self._phys_to_virt_gain(current_reg_gain)
        
        if not os.path.exists(raw_path):
            return int(current_us), float(current_reg_gain), self.target, 0.0

        try:
            raw_map = np.memmap(raw_path, dtype=np.uint16, mode='r', shape=(height, width))
            stride = 8
            ds_raw = raw_map[0::stride, 0::stride].astype(np.float32)
            bg = np.median(ds_raw)
            max_dynamic_range = float((1 << raw_bits) - 1)
            luma = np.clip(bg / max_dynamic_range, 1e-4, 1.0)
            
            del raw_map

            if self.ev is None:
                self.ev = math.log2(max(self.min_energy, (current_us * current_virt_gain) / 1e6) + 1e-9)
                self.velocity = 0.0

            exact_ev_step = math.log2(self.target / luma)

            base_pull = (exact_ev_step ** 2) * np.sign(exact_ev_step) * 0.001

            alignment = np.sign(self.velocity * exact_ev_step + 1e-9)

            is_same_dir = (0.5 * alignment + 0.5)

            brake_force = math.tanh((abs(exact_ev_step) / 1.6) ** 1.6)

            soft_damping = 1.0 - math.exp(-(abs(exact_ev_step) / 0.15) ** 2.0)

            self.accel_factor = (self.accel_factor * 2.0 * is_same_dir) + (4.0 * (1.0 - is_same_dir))
            self.accel_factor = min(self.accel_factor, 128.0)

            self.velocity = (self.velocity * is_same_dir * brake_force * soft_damping) + (base_pull * self.accel_factor)


            self.velocity = np.clip(self.velocity, -0.5, 0.5)
            self.ev += self.velocity

            total_energy_us = (2.0 ** self.ev) * 1e6

            limit_virt_gain_max = self._phys_to_virt_gain(max_reg_gain)
        
            if total_energy_us <= (max_us * self.VIRT_GAIN_MIN):
                next_us = np.clip(total_energy_us / self.VIRT_GAIN_MIN, min_us, max_us)
                next_virt_gain = self.VIRT_GAIN_MIN
            else:
                next_us = float(max_us)
                next_virt_gain = np.clip(total_energy_us / (next_us + 1e-9), self.VIRT_GAIN_MIN, limit_virt_gain_max)
            
            actual_phys_ev = math.log2((next_us * next_virt_gain) / 1e6 + 1e-9)
            self.ev = actual_phys_ev 

            next_reg_gain = self._virt_to_phys_gain(next_virt_gain)
            return int(next_us), float(next_reg_gain), float(luma), float(exact_ev_step)

        except Exception as e:
            print(f"[AE] RAW Process Error: {e}")
            if 'raw_map' in locals(): del raw_map
            return int(current_us), float(current_reg_gain), self.target, 0.0

_engine = None

def process_ae_logic(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, reg_min, raw_bits):
    global _engine
    if _engine is None:
        _engine = AdaptiveExposureEngine(reg_min, max_reg_gain, 1.0, 16.0)
    return _engine.process_raw_frame(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, raw_bits)
