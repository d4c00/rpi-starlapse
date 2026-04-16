# Copyright (c) 2026 length <me@length.cc>
# Licensed under the MIT License.

import numpy as np
import math
import os
from snippets.config import AE_TARGET_LUMA


MAX_LUMA_JUMP_RATIO = 0.5
DELAY_FRAMES_COUNT = 2
MAX_HW_EV = 12.0
GAIN_DB_MIN_VAL = 30.3
GAIN_DB_MAX_VAL = 72.0


class AdaptiveExposureEngine:
    def __init__(self, reg_min, reg_max):
        self.target = AE_TARGET_LUMA
        self.REG_MIN = reg_min
        self.REG_MAX = reg_max

        self.GAIN_DB_MIN = GAIN_DB_MIN_VAL
        self.GAIN_DB_MAX = GAIN_DB_MAX_VAL
        self.MIN_LINEAR_GAIN = 10 ** (self.GAIN_DB_MIN / 20.0)

        self.LIMIT_DN = math.log2(1.0 - MAX_LUMA_JUMP_RATIO)
        self.LIMIT_UP = math.log2(1.0 + MAX_LUMA_JUMP_RATIO)

        self.velocity = 0.0
        self.accel_factor = 1.0
        self.ev = None

        self.delay_frames = DELAY_FRAMES_COUNT
        self.history = []


    def _phys_to_virt_gain(self, reg_val):
        if self.REG_MAX == self.REG_MIN:
            return 1.0
        db = self.GAIN_DB_MIN + (reg_val - self.REG_MIN) * (
            self.GAIN_DB_MAX - self.GAIN_DB_MIN
        ) / (self.REG_MAX - self.REG_MIN)
        return 10 ** (db / 20.0)

    def _virt_to_phys_gain(self, virt_gain):
        if virt_gain <= 0:
            return self.REG_MIN
        db = 20.0 * math.log10(virt_gain)
        if self.GAIN_DB_MAX == self.GAIN_DB_MIN:
            return self.REG_MIN
        reg = self.REG_MIN + (db - self.GAIN_DB_MIN) * (
            self.REG_MAX - self.REG_MIN
        ) / (self.GAIN_DB_MAX - self.GAIN_DB_MIN)
        return int(np.clip(reg, self.REG_MIN, self.REG_MAX))

    def _compute_ev(self, exposure_us, virt_gain):
        return math.log2(((exposure_us * virt_gain) / 1e6) + 1e-9)

    def _measure_luma(self, raw_path, width, height, raw_bits):
        if not os.path.exists(raw_path):
            return self.target

        try:
            raw_map = np.memmap(raw_path, dtype=np.uint16, mode="r", shape=(height, width))
            ds = raw_map[0::4, 0::4].astype(np.float32)
            median = np.median(ds)
            del raw_map

            max_val = float((1 << raw_bits) - 1)
            return np.clip(median / max_val, 1e-4, 1.0)

        except Exception:
            return self.target

    def _compute_ev_step(self, luma):
        if luma <= self.target:
            dist = (self.target - luma) / max(self.target, 1e-9)
            return (dist ** 0.5) * MAX_HW_EV
        else:
            dist = (luma - self.target) / max(1.0 - self.target, 1e-9)
            return -(dist ** 0.5) * MAX_HW_EV

    def _update_controller(self, remaining_ev):
        base_pull = (remaining_ev ** 2) * np.sign(remaining_ev) * 1e-4

        alignment = np.sign(self.velocity * remaining_ev + 1e-9)
        is_same_dir = 0.5 * alignment + 0.5

        brake_force = math.tanh((abs(remaining_ev) / 12.0) ** 1.2)
        soft_damping = 1.0 - math.exp(-(abs(remaining_ev) / 2.0) ** 2.0)

        self.accel_factor = (
            self.accel_factor * 2.0 * is_same_dir
            + 4.0 * (1.0 - is_same_dir)
        )
        self.accel_factor = min(self.accel_factor, 256.0)

        raw_move = (
            self.velocity * is_same_dir * soft_damping
            + base_pull * self.accel_factor
        )

        self.velocity = raw_move * brake_force

        scale = self.LIMIT_UP if self.velocity > 0 else abs(self.LIMIT_DN)
        self.velocity = np.clip(self.velocity * scale, self.LIMIT_DN, self.LIMIT_UP)

        return self.velocity

    def _reset_controller(self):
        self.velocity = 0.0
        self.accel_factor = 1.0

    def _allocate_energy(self, target_ev, max_us, min_us, max_reg_gain):
        total_energy = (2.0 ** target_ev) * 1e6

        max_virt_gain = self._phys_to_virt_gain(max_reg_gain)

        if total_energy <= max_us * self.MIN_LINEAR_GAIN:
            next_us = np.clip(total_energy / self.MIN_LINEAR_GAIN, min_us, max_us)
            virt_gain = self.MIN_LINEAR_GAIN
        else:
            next_us = float(max_us)
            virt_gain = np.clip(
                total_energy / (next_us + 1e-9),
                self.MIN_LINEAR_GAIN,
                max_virt_gain,
            )

        reg_gain = self._virt_to_phys_gain(virt_gain)
        return next_us, reg_gain

    def _process_delay_frame(self, raw_path, width, height, current_us, current_reg_gain, raw_bits):
        luma = self._measure_luma(raw_path, width, height, raw_bits)

        virt_gain = self._phys_to_virt_gain(current_reg_gain)
        ev = self._compute_ev(current_us, virt_gain)

        step = self._compute_ev_step(luma)

        self._reset_controller()

        return current_us, current_reg_gain, luma, step

    def process_raw_frame(self, raw_path, width, height, current_us, current_reg_gain, max_us, min_us, max_reg_gain, raw_bits):
        if self.delay_frames > 0 and len(self.history) < self.delay_frames:
            self.history.append((current_us, current_reg_gain))
            return self._process_delay_frame(
                raw_path, width, height,
                current_us, current_reg_gain,
                raw_bits
            )

        if self.delay_frames > 0:
            actual_us, actual_reg = self.history.pop(0)
        else:
            actual_us, actual_reg = current_us, current_reg_gain

        luma = self._measure_luma(raw_path, width, height, raw_bits)

        actual_gain = self._phys_to_virt_gain(actual_reg)
        actual_ev = self._compute_ev(actual_us, actual_gain)

        ev_step = self._compute_ev_step(luma)
        ideal_ev = actual_ev + ev_step

        latest_gain = self._phys_to_virt_gain(current_reg_gain)
        latest_ev = self._compute_ev(current_us, latest_gain)

        remaining = ideal_ev - latest_ev

        delta = self._update_controller(remaining)
        target_ev = latest_ev + delta
        self.ev = target_ev

        next_us, next_reg = self._allocate_energy(
            target_ev, max_us, min_us, max_reg_gain)

        if self.delay_frames > 0:
            self.history.append((next_us, next_reg))

        return int(next_us), float(next_reg), float(luma), float(ev_step)


_engine = None


def process_ae_logic(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, reg_min, raw_bits):
    global _engine
    if _engine is None:
        _engine = AdaptiveExposureEngine(reg_min, max_reg_gain)

    return _engine.process_raw_frame(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, raw_bits)
