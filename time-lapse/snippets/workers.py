# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, time, requests, queue, glob
from snippets.camera import V4L2Camera
from snippets.config import *
from snippets.ae import process_ae_logic
from snippets.sensors import sensor
from snippets.utils import (pet_watchdog, setup_logger, set_led, led_play, get_shm_paths, is_valid_raw, advance_frame, cleanup_shm, 
    upload_with_retry, log_pic, get_local_photos, toggle_bool_config, dispatch_to_manager, move_to_local_storage, handle_net_failure, unpack_snap, 
    pack_snap, flush_old_frames
)

logger = setup_logger("WORKER")

def switch_worker(stop_ev, sh_cam_en, sh_ae_en):
    logger = setup_logger("SWITCH")
    logger.info("Switch worker started.")
    while not stop_ev.is_set():
        if os.path.exists(CAMERA_SWITCH_FILE):
            try:
                os.remove(CAMERA_SWITCH_FILE)
                toggle_bool_config(sh_cam_en, "CAMERA_ENABLED")
                status_text = "ENABLED" if sh_cam_en.value else "DISABLED"
                logger.info(f">>> [MANUAL] Camera state changed to: {status_text} <<<")
                if sh_cam_en.value:
                    led_play([(1, 0.05), (0, 0.05)], loop=8, block=False)
                else:
                    led_play([(1, 0.2), (0, 0.2)], loop=3, block=False)
            except Exception as e:
                logger.error(f"Switch worker error: {e}")

        if os.path.exists(AE_SWITCH_FILE):
            try:
                os.remove(AE_SWITCH_FILE)
                toggle_bool_config(sh_ae_en, "AE_ENABLED")
                logger.info(f">>> [MANUAL] AE state changed to: {'ON' if sh_ae_en.value else 'OFF'} <<<")
                if sh_ae_en.value:
                    led_play([(1, 0.02), (0, 0.02)], loop=3, block=False)
                else:
                    led_play([(1, 0.1), (0, 0.1)], loop=2, block=False)
            except Exception as e:
                logger.error(f"AE Switch worker error: {e}")
        time.sleep(1.0)

MODE_MAP = {
    "lights_tmp": {"mode": "lights", "use_ae": True},
    "darks_tmp":  {"mode": "darks",  "use_ae": False},
    "biases_tmp": {"mode": "biases", "use_ae": False},
}

def capture_frame(cam, mode, target, r_path, sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q, bias_params=None):
    dev_id_str = sh_dev_id.value.decode().rstrip('\x00')

    target_snap = bias_params if bias_params else unpack_snap(sh_snap.value)
    s_us, g = target_snap["t_us"], target_snap["g"]

    if is_online.value:
        set_led(1)
    else:
        led_play([(1, 0.03), (0, 0.1), (1, None)], block=False)

    success, cap_dur = cam.capture_to_path(s_us, g, target)

    if success and is_valid_raw(target):
        curr_id = sh_frame_id.value + 1
        sh_frame_id.value = curr_id

        tag = target.split('.')[-1]
        final_ready_path = f"{r_path}.{tag}.{curr_id}_{int(s_us)}_{int(g)}"
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

    cam = None
    ready_ev.set()

    while not stop_ev.is_set():
        if not sh_cam_en.value:
            if cam is not None:
                logger.info(">>> Camera disabled or paused. Releasing hardware. <<<")
                del cam
                cam = None
            time.sleep(0.5); continue

        if cam is None:
            try:
                cam = V4L2Camera()
                flush_old_frames(cam)
            except Exception as e:
                logger.error(f"Hardware initialization failed: {e}"); time.sleep(1.0); continue

        if not trigger_ev.wait(timeout=0.5): continue
        trigger_ev.clear()

        if os.path.exists(DARK_TRIGGER_FILE):
            try: os.remove(DARK_TRIGGER_FILE)
            except: pass
            
            logger.info(">>> [CALIBRATION] Starting calibration frames. Please cover the lens cap <<<")
            led_play([(1, 0.2), (0, 0.2)], loop=30, block=True) 

            trigger_ev.clear()
            flush_old_frames(cam)
            logger.info(f">>> [1/2] Capturing Darks (Count:{DARK_FRAME_COUNT})")
            for _ in range(DARK_FRAME_COUNT):
                if stop_ev.is_set() or not sh_cam_en.value: break
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
                    if stop_ev.is_set() or not sh_cam_en.value: break
                    now = time.time()
                    time.sleep(max(0, BIAS_INTERVAL - (now % BIAS_INTERVAL)))

                    if sh_frame_id.value > sh_last_ae_id.value:
                        logger.warning(f"[SKIP-CAL] AE lagging during biases: Frame({sh_frame_id.value}) > LastAE({sh_last_ae_id.value})")
                        continue

                    capture_frame(cam, "biases", f"{w_path}.biases_tmp", r_path, 
                                  sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q, 
                                  bias_params=bias_cfg)
            else:
                logger.info(">>> [2/2] Skipping Biases (Disabled in config)")

            logger.info(">>> Calibration complete. CAMERA_ENABLED in config.py has been set to False <<<")
            sh_snap.value = sensor.INIT_SNAP_STR.encode()
            toggle_bool_config(sh_cam_en, "CAMERA_ENABLED", target_state=False)
            flush_old_frames(cam)
            continue

        if sh_frame_id.value > sh_last_ae_id.value:
            logger.warning(f"[SKIP] AE lagging during lights: Frame({sh_frame_id.value}) > LastAE({sh_last_ae_id.value})")
            continue

        try:
            capture_frame(cam, "lights", f"{w_path}.lights_tmp", r_path, 
                          sh_frame_id, sh_last_ae_id, is_online, sh_dev_id, sh_snap, data_q)
        except Exception as e:
            logger.error(f"camera_worker error: {e}")
            advance_frame(sh_frame_id, sh_last_ae_id)

def ae_worker(stop_ev, sh_frame_id, sh_last_ae_id, sh_snap, sh_dev_id, data_q, ready_ev, sh_ae_en):
    last_id = 0
    dev_id_str = sh_dev_id.value.decode().rstrip('\x00')
    _, r_path = get_shm_paths(dev_id_str)
    W, H = 0, 0

    while not stop_ev.is_set():
        if sh_frame_id.value > last_id:
            try:
                curr_id = sh_frame_id.value
                t0 = time.perf_counter()

                pattern = f"{r_path}.*tmp.{curr_id}_*"
                found_files = glob.glob(pattern)
                
                if not found_files:
                    time.sleep(0.01); continue

                target_raw = found_files[0] 
                filename = os.path.basename(target_raw)

                parts = filename.split('.')
                tag = parts[-2]
                
                meta_parts = parts[-1].split('_')
                actual_t = float(meta_parts[1])
                actual_g = float(meta_parts[2])

                cfg = MODE_MAP.get(tag, MODE_MAP["lights_tmp"])
                mode, use_ae = cfg["mode"], cfg["use_ae"]

                if W == 0: W, H = V4L2Camera.probe_resolution()

                new_s, new_g, m_val, new_ev = process_ae_logic(
                    target_raw, W, H, actual_t, actual_g, 
                    min((CAPTURE_INTERVAL - 0.5), sensor.MAX_EXPOSURE) * 1e6,
                    sensor.AE_MIN_US, sensor.MAX_GAIN, sensor.MIN_GAIN,
                    sensor.GAIN_DB_MIN, sensor.GAIN_DB_MAX, sensor.BIT
                )

                p = {
                    "id": curr_id, 
                    "t_us": actual_t, 
                    "g": actual_g, 
                    "y": m_val, 
                    "ev": new_ev if use_ae else 0.0
                }

                if mode == "lights" and curr_id <= 1:
                    logger.info(f"[DROP] Dropping initial light frame ID:{curr_id}")
                    if os.path.exists(target_raw): os.remove(target_raw)
                else:
                    dispatch_to_manager(data_q, mode, dev_id_str, p, target_raw, logger)

                if mode == "lights":
                    if not sh_ae_en.value:
                        final_s = FIXED_EXPOSURE_SEC * 1e6
                        final_g = FIXED_GAIN
                    else:
                        final_s, final_g = new_s, new_g
                    
                    snap_data = pack_snap(curr_id, final_s, final_g, new_ev, m_val)
                    sh_snap.value = snap_data.encode()

                cost_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    f"[AE-RAW] ID:{curr_id} | Mode:{mode} | Done:{cost_ms:.1f}ms | "
                    f"NextT:{(final_s if mode=='lights' else actual_t)/1000:.1f}ms,G:{int(final_g if mode=='lights' else actual_g)}"
                )

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

def background_sync_worker(is_online, sync, pause_ev, stop_ev, sh_cam_en, sh_retry_count):
    sess = requests.Session()
    logger = setup_logger("SYNC")

    while not stop_ev.is_set():
        if not sync.wait(timeout=1.0): continue
        sync.clear()

        if not sh_cam_en.value:
            photos = get_local_photos(limit=1000)
            pause_ev.set()
            try:
                for idx, full_path in enumerate(photos):
                    if sh_cam_en.value or not is_online.value: break
                    upload_with_retry(sess, os.path.basename(full_path), full_path, "SYNC-F", 
                                     f"Seq-{idx}", is_online, stop_ev, sh_retry_count, MAX_UPLOAD_RETRY)
            finally:
                pause_ev.clear()

        else:
            photos = get_local_photos(limit=SLOW_SYNC_COUNT_PER_CYCLE)
            gap = (CAPTURE_INTERVAL - (time.time() % CAPTURE_INTERVAL)) / (len(photos) + 1)
            for idx, full_path in enumerate(photos):
                if not sh_cam_en.value or pause_ev.is_set() or not is_online.value: break
                time.sleep(gap)
                upload_with_retry(sess, os.path.basename(full_path), full_path, "SYNC-S", 
                                 f"Slow-{idx}", is_online, stop_ev, sh_retry_count, MAX_UPLOAD_RETRY)

def sync_scheduler_worker(sync, stop_ev, is_online, sh_cam_en, sh_retry_count):
    sess = requests.Session()
    logger = setup_logger("SCHEDULER")
    last_probe = 0
    fail_count = 0 

    while not stop_ev.is_set():
        time.sleep(1.0)
        now = time.time()

        photos = get_local_photos(limit=1)

        if not photos and not sh_cam_en.value:
            pet_watchdog()

        if not photos:
            fail_count = 0
            continue

        current_delay = 5 * (2 ** min(fail_count, 3))
        if now - last_probe < current_delay:
            continue

        last_probe = now
        success = upload_with_retry(
            sess, os.path.basename(photos[0]), photos[0], 
            "SYNC", "PROBE", is_online, 
            stop_ev, sh_retry_count, r_limit=0
        )

        if success:
            fail_count = 0
            sync.set()
        else:
            fail_count += 1
            logger.warning(f"[SYNC] Backlog pending. Next attempt in {5 * (2 ** min(fail_count, 3))}s")

def timer_worker(trigger_ev, stop_ev):
    interval = CAPTURE_INTERVAL
    while not stop_ev.is_set():
        wait_time = interval - (time.time() % interval)
        time.sleep(wait_time)
        if not stop_ev.is_set():
            trigger_ev.set()