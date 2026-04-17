# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, time, requests, queue
from snippets.camera import V4L2Camera
from snippets.config import *
from snippets.ae import process_ae_logic
from snippets.sensors import sensor
from snippets.utils import (pet_watchdog, setup_logger, set_led, flash_led, blink_loop, get_shm_paths, is_valid_raw, advance_frame, cleanup_shm, 
    upload_with_retry, log_pic, get_local_photos, disable_config_cam, dispatch_to_manager, move_to_local_storage, handle_net_failure, unpack_snap, 
    pack_snap, flush_old_frames
)

logger = setup_logger("WORKER")

MODE_MAP = {
    "lights_tmp": {"mode": "lights", "use_ae": True},
    "darks_tmp":  {"mode": "darks",  "use_ae": False},
    "biases_tmp": {"mode": "biases", "use_ae": False},
}

def capture_frame(cam, mode, target, r_path, sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q, bias_params=None):
    dev_id_str = sh_dev_id.value.decode().rstrip('\x00')

    if bias_params:
        s_us, g = bias_params["t_us"], bias_params["g"]
        p = {"ev": 0, "y": 0, "t_us": s_us, "g": g}
    else:
        p = unpack_snap(sh_snap.value)
        s_us, g = p["t_us"], p["g"]

    set_led(1)

    success, cap_dur = cam.capture_to_path(s_us, g, target)

    if success and is_valid_raw(target):
        curr_id = sh_frame_id.value + 1
        sh_frame_id.value = curr_id

        tag = target.split('.')[-1]
        final_ready_path = f"{r_path}.{tag}.{curr_id}"
        os.replace(target, final_ready_path)

        logger.info(f"[{mode.upper()} OK] ID:{curr_id} | Read:{cap_dur:.1f}ms")
        status = True
    else:
        logger.error(f"[{mode.upper()} FAIL] {mode} capture failed.")
        advance_frame(sh_frame_id, sh_last_ae_id)
        status = False

    set_led(0)

    return status

def camera_worker(sh_frame_id, sh_last_ae_id, data_q, stop_ev, trigger_ev, sh_snap, is_online, ready_ev, sh_dev_id, pause_ev, sh_cam_en):
    dev_id_str = sh_dev_id.value.decode().rstrip('\x00')
    w_path, r_path = get_shm_paths(dev_id_str)

    flush_old_frames(cam)
    try:
        cam = V4L2Camera()
    except Exception as e:
        logger.error(f"Hardware initialization failed: {e}"); return

    ready_ev.set()

    while not stop_ev.is_set():
        if not trigger_ev.wait(timeout=0.5): continue
        trigger_ev.clear()

        if os.path.exists(DARK_TRIGGER_FILE):
            try: os.remove(DARK_TRIGGER_FILE)
            except: pass
            
            logger.info(">>> [CALIBRATION] Starting calibration frames. Please cover the lens cap <<<")
            blink_loop(30, 0.2, 0.2) 
 
            flush_old_frames(cam)
            logger.info(f">>> [1/2] Capturing Darks (Count:{DARK_FRAME_COUNT})")
            for _ in range(DARK_FRAME_COUNT):
                if stop_ev.is_set(): break
                if not trigger_ev.wait(timeout=CAPTURE_INTERVAL + 5.0): break
                trigger_ev.clear()

                if sh_frame_id.value > sh_last_ae_id.value:
                    logger.warning(f"[SKIP-CAL] AE lagging during darks: Frame({sh_frame_id.value}) > LastAE({sh_last_ae_id.value})")
                    continue

                capture_frame(cam, "darks", f"{w_path}.darks_tmp", r_path, 
                              sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q)

            flush_old_frames(cam)
            if CAPTURE_BIAS_FRAMES:
                logger.info(f">>> [2/2] Capturing Biases (Count: {BIAS_FRAME_COUNT})")
                bias_cfg = {"t_us": int(sensor.MIN_EXPOSURE * 1e6), "g": sensor.MIN_GAIN}
                for _ in range(BIAS_FRAME_COUNT):
                    if stop_ev.is_set(): break
                    now = time.time()
                    time.sleep(BIAS_INTERVAL - (now % BIAS_INTERVAL))

                    if sh_frame_id.value > sh_last_ae_id.value:
                        logger.warning(f"[SKIP-CAL] AE lagging during biases: Frame({sh_frame_id.value}) > LastAE({sh_last_ae_id.value})")
                        continue

                    capture_frame(cam, "biases", f"{w_path}.biases_tmp", r_path, 
                                  sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q, 
                                  bias_params=bias_cfg)
            else:
                logger.info(">>> [2/2] Skipping Biases (Disabled in config)")

            logger.info(">>> Calibration complete. CAMERA_ENABLED in config.py has been set to False <<<")
            disable_config_cam(sh_cam_en)
            continue

        if not sh_cam_en.value or pause_ev.is_set():
            continue

        if sh_frame_id.value > sh_last_ae_id.value:
            logger.warning(f"[SKIP] AE lagging: Frame({sh_frame_id.value}) > LastAE({sh_last_ae_id.value})")
            continue

        try:
            capture_frame(cam, "lights", f"{w_path}.lights_tmp", r_path, 
                          sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q)
        except Exception as e:
            logger.error(f"camera_worker error: {e}")
            advance_frame(sh_frame_id, sh_last_ae_id) 

def ae_worker(stop_ev, sh_frame_id, sh_last_ae_id, sh_snap, sh_dev_id, data_q, ready_ev):
    last_id = 0
    dev_id_str = sh_dev_id.value.decode().rstrip('\x00')
    _, r_path = get_shm_paths(dev_id_str)
    W, H = 0, 0

    while not stop_ev.is_set():
        if sh_frame_id.value > last_id:
            try:
                curr_id = sh_frame_id.value
                t0 = time.perf_counter()

                target_raw = f"{r_path}.lights_tmp.{curr_id}"
                if not os.path.exists(target_raw):
                    found = False
                    for tag_trial in ["darks_tmp", "biases_tmp"]:
                        trial = f"{r_path}.{tag_trial}.{curr_id}"
                        if os.path.exists(trial):
                            target_raw = trial
                            found = True; break
                    if not found:
                        time.sleep(0.01); continue

                tag = target_raw.split('.')[-2]
                cfg = MODE_MAP.get(tag, MODE_MAP["lights_tmp"])
                mode, use_ae = cfg["mode"], cfg["use_ae"]

                if W == 0: W, H = V4L2Camera.probe_resolution()

                p = unpack_snap(sh_snap.value)
                p["id"] = curr_id
                limit_us = min((CAPTURE_INTERVAL - AE_MARGIN), sensor.MAX_EXPOSURE) * 1e6

                new_s, new_g, m_val, new_ev = process_ae_logic(
                    target_raw, W, H, p["t_us"], p["g"], 
                    limit_us,
                    sensor.AE_MIN_US,
                    sensor.MAX_GAIN, 
                    sensor.MIN_GAIN, 
                    sensor.BIT
                )

                p["y"] = m_val
                if not use_ae:
                    p["ev"] = 0.0
                    if mode == "biases":
                        s_target = int(sensor.MIN_EXPOSURE * 1e6)
                        g_target = sensor.MIN_GAIN
                    else:
                        s_target, g_target = p["t_us"], p["g"]
                    
                    snap_data = pack_snap(curr_id, s_target, g_target, 0.0, m_val)
                else:
                    p["ev"] = new_ev
                    snap_data = pack_snap(curr_id, new_s, new_g, new_ev, m_val)

                dispatch_to_manager(data_q, mode, dev_id_str, p, target_raw, logger)
                sh_snap.value = snap_data.encode()

                cost_ms = (time.perf_counter() - t0) * 1000
                logger.info(f"[AE-RAW] ID:{curr_id} | Mode:{mode} | Done:{cost_ms:.1f}ms | NextT:{ (new_s if use_ae else p['t_us'])/1000:.1f}ms | Y:{m_val:.3f}")

                sh_last_ae_id.value = curr_id
                last_id = curr_id

            except Exception as e:
                logger.error(f"AE Process Error: {e}")
                sh_last_ae_id.value = sh_frame_id.value
                last_id = sh_frame_id.value
        else:
            time.sleep(0.01)

def memory_manager_worker(data_q, is_online, stop_ev, sh_dev_id, sh_frame_id, always_set_ev, sh_retry_count):
    sess = requests.Session()
    logger = setup_logger("MEM_MGR")

    while not stop_ev.is_set():
        try:
            it = data_q.get(timeout=0.5)
            curr_id = it.get("id", 0)

            is_probe = (not is_online.value) and (curr_id > 0 and curr_id % LOCAL_TRY_UPLOAD_RATE == 0)
            
            success = False
            if is_online.value or is_probe:
                success = upload_with_retry(
                    sess, it["name"], it["path"], 
                    "LIVE" if is_online.value else "PROBE", 
                    f"ID:{curr_id}", is_online, stop_ev, 
                    sh_retry_count, MAX_UPLOAD_RETRY
                )

            if not success:
                if move_to_local_storage(it, logger):
                    log_pic("LOCAL", it["name"], "STORED", f"ID:{curr_id} | Q:{data_q.qsize()}")

        except queue.Empty: continue
        except Exception as e:
            logger.error(f"Manager Error: {e}")

def background_sync_worker(is_online, f_sync, s_sync, pause_ev, stop_ev, sh_cam_en, sh_retry_count):
    sess = requests.Session()
    check_boot_sync = BOOT_FIRST_LIVE_FAST_SYNC

    while not stop_ev.is_set():
        force_fast = not sh_cam_en.value
        if (check_boot_sync or f_sync.is_set() or force_fast) and is_online.value:
            f_sync.clear()
            check_boot_sync = False

            photos = get_local_photos(limit=500)
            if photos:
                logger.info(f"[SYNC-FAST] Blocking camera for {len(photos)} files.")
                pause_ev.set()
                try:
                    for idx, full_path in enumerate(photos):
                        if not is_online.value or stop_ev.is_set(): break
                        fname = os.path.basename(full_path)
                        if upload_with_retry(sess, fname, full_path, "SYNC-F", f"Seq-{idx}", is_online, stop_ev, sh_retry_count, MAX_UPLOAD_RETRY):
                            flash_led(0.05)
                        else:
                            logger.error("[SYNC-FAST] Network interrupted. Releasing camera.")
                            is_online.value = False
                            sh_retry_count.value = MAX_UPLOAD_RETRY
                            break
                        time.sleep(0.02)
                finally:
                    pause_ev.clear()

            elif force_fast:
                pet_watchdog()
                time.sleep(60)

        if s_sync.is_set() and is_online.value and not pause_ev.is_set():
            s_sync.clear()
            photos = get_local_photos(limit=SLOW_SYNC_COUNT_PER_CYCLE)
            if photos:
                gap = max(0.5, (CAPTURE_INTERVAL - 4.0) / (SLOW_SYNC_COUNT_PER_CYCLE + 1))
                for idx, full_path in enumerate(photos):
                    if not is_online.value or stop_ev.is_set() or pause_ev.is_set(): break
                    time.sleep(gap)
                    fname = os.path.basename(full_path)
                    upload_with_retry(sess, fname, full_path, "SYNC-S", f"Slow-{idx}", is_online, stop_ev, sh_retry_count, MAX_UPLOAD_RETRY)
        time.sleep(1.0)

def sync_scheduler_worker(s_sync, stop_ev):
    while not stop_ev.is_set():
        time.sleep(1.0)
        s_sync.set()

def timer_worker(trigger_ev, stop_ev):
    interval = CAPTURE_INTERVAL
    while not stop_ev.is_set():
        wait_time = interval - (time.time() % interval)
        time.sleep(wait_time)
        if not stop_ev.is_set():
            trigger_ev.set()
