# Copyright (c) 2026 length <me@length.cc>
# Licensed under the MIT License.

import numpy as np
import math
import os
from snippets.config import AE_TARGET_LUMA

MAX_LUMA_JUMP_RATIO = 0.33333
DELAY_FRAMES_COUNT = 2
MAX_HW_EV = 6.0
GAIN_DB_MIN_VAL = 30.3
GAIN_DB_MAX_VAL = 72.0

class AdaptiveExposureEngine:
    def __init__(self, reg_min, reg_max):
        self.target = AE_TARGET_LUMA
        self.REG_MIN, self.REG_MAX = reg_min, reg_max
        self.GAIN_DB_MIN, self.GAIN_DB_MAX = GAIN_DB_MIN_VAL, GAIN_DB_MAX_VAL
        self.MIN_LINEAR_GAIN = 10 ** (self.GAIN_DB_MIN / 20.0)

        self.LIMIT_DN = math.log2(1.0 - MAX_LUMA_JUMP_RATIO)
        self.LIMIT_UP = math.log2(1.0 + MAX_LUMA_JUMP_RATIO)

        self.delay_frames = DELAY_FRAMES_COUNT
        self.history = []

    def _phys_to_virt_gain(self, reg_val):
        if self.REG_MAX == self.REG_MIN: return 1.0
        db = self.GAIN_DB_MIN + (reg_val - self.REG_MIN) * (self.GAIN_DB_MAX - self.GAIN_DB_MIN) / (self.REG_MAX - self.REG_MIN)
        return 10 ** (db / 20.0)

    def _virt_to_phys_gain(self, virt_gain):
        if virt_gain <= 0: return self.REG_MIN
        db = 20.0 * math.log10(virt_gain)
        reg = self.REG_MIN + (db - self.GAIN_DB_MIN) * (self.REG_MAX - self.REG_MIN) / (self.GAIN_DB_MAX - self.GAIN_DB_MIN)
        return int(np.clip(reg, self.REG_MIN, self.REG_MAX))

    def _measure_luma(self, raw_path, width, height, raw_bits):
        if not os.path.exists(raw_path): return self.target
        try:
            raw_map = np.memmap(raw_path, dtype=np.uint16, mode="r", shape=(height, width))
            ds = raw_map[0::4, 0::4].astype(np.float32)
            luma = np.median(ds) / float((1 << raw_bits) - 1)
            del raw_map
            return np.clip(luma, 1e-4, 1.0)
        except: return self.target

    def _compute_ev_step(self, luma):
        if luma <= self.target:
            dist = (self.target - luma) / max(self.target, 1e-9)
            return (dist ** 0.5) * MAX_HW_EV
        else:
            dist = (luma - self.target) / max(1.0 - self.target, 1e-9)
            return -(dist ** 0.5) * MAX_HW_EV

    def _update_controller(self, remaining_ev):
        ratio = min(abs(remaining_ev) / MAX_HW_EV, 1.0)
        
        curve_gain = ratio ** 4.0 
        
        move = remaining_ev * curve_gain

        soft_damping = 1.0 - math.exp(-(abs(remaining_ev) / 0.5) ** 2.0)
        
        final_move = move * soft_damping

        return np.clip(final_move, self.LIMIT_DN, self.LIMIT_UP)

    def _allocate_energy(self, target_ev, max_us, min_us, max_reg_gain):
        total_energy = (2.0 ** target_ev) * 1e6
        if total_energy <= max_us * self.MIN_LINEAR_GAIN:
            next_us = np.clip(total_energy / self.MIN_LINEAR_GAIN, min_us, max_us)
            next_reg = self.REG_MIN
        else:
            next_us = float(max_us)
            next_reg = self._virt_to_phys_gain(total_energy / (next_us + 1e-9))
        return next_us, next_reg

    def process_raw_frame(self, raw_path, width, height, current_us, current_reg_gain, max_us, min_us, max_reg_gain, raw_bits):
        luma = self._measure_luma(raw_path, width, height, raw_bits)
        if len(self.history) < self.delay_frames:
            self.history.append((current_us, current_reg_gain))
            return current_us, float(current_reg_gain), float(luma), 0.0

        actual_us, actual_reg = self.history.pop(0)
        actual_ev = math.log2((actual_us * self._phys_to_virt_gain(actual_reg) / 1e6) + 1e-9)
        ev_step = self._compute_ev_step(luma)
        ideal_ev = actual_ev + ev_step
        latest_ev = math.log2((current_us * self._phys_to_virt_gain(current_reg_gain) / 1e6) + 1e-9)
        
        remaining = ideal_ev - latest_ev
        delta = self._update_controller(remaining)
        
        target_ev = latest_ev + delta
        next_us, next_reg = self._allocate_energy(target_ev, max_us, min_us, max_reg_gain)
        self.history.append((next_us, next_reg))
        return int(next_us), float(next_reg), float(luma), float(ev_step)

_engine = None

def process_ae_logic(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, reg_min, raw_bits):
    global _engine
    if _engine is None:
        _engine = AdaptiveExposureEngine(reg_min, max_reg_gain)
    return _engine.process_raw_frame(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, raw_bits)
