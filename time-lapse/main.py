# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import sys, os, time, multiprocessing, signal
from snippets.utils import set_led, blink_loop, check_time_server, setup_logger, cleanup_shm_env, get_optimal_queue_size
from snippets.workers import (ae_worker, camera_worker, memory_manager_worker,
                              background_sync_worker, sync_scheduler_worker, timer_worker)
from snippets.config import (DEVICE_ID, SAVE_DIR, CAMERA_ENABLED)

logger = setup_logger("MAIN")

def run_core():
    logger.info(f"=== Starting Device {DEVICE_ID} ===")
    os.makedirs(SAVE_DIR, exist_ok=True)
    cleanup_shm_env()

    init_snap_str = "0|666666|1.0|0.0|0.0"
    sh_snap = multiprocessing.Array('c', 128)
    sh_snap.value = init_snap_str.encode()

    online = multiprocessing.Value('b', True)
    sh_dev_id = multiprocessing.Array('c', DEVICE_ID.encode())
    sh_frame_id = multiprocessing.Value('L', 0)
    sh_last_ae_id = multiprocessing.Value('L', 0)
    sh_cam_en = multiprocessing.Value('b', CAMERA_ENABLED)
    sh_retry_count = multiprocessing.Value('i', 0)
    
    always_set_ev = multiprocessing.Event()
    always_set_ev.set()

    while True:
        stop = multiprocessing.Event()
        trigger_ev = multiprocessing.Event()
        rdy = multiprocessing.Event()
        f_sync, s_sync, pause = [multiprocessing.Event() for _ in range(3)]

        data_q = multiprocessing.Queue(get_optimal_queue_size())

        def handle_exit(s, f): stop.set()
        signal.signal(signal.SIGTERM, handle_exit)
        signal.signal(signal.SIGINT, handle_exit)

        tasks = [
            (timer_worker, (trigger_ev, stop)),
            (camera_worker, (sh_frame_id, sh_last_ae_id, data_q, stop, trigger_ev, sh_snap, online, rdy, sh_dev_id, pause, sh_cam_en)),
            (ae_worker, (stop, sh_frame_id, sh_last_ae_id, sh_snap, sh_dev_id, data_q, rdy)),
            (memory_manager_worker, (data_q, online, stop, sh_dev_id, sh_frame_id, always_set_ev, sh_retry_count)),
            (sync_scheduler_worker, (s_sync, stop)),
            (background_sync_worker, (online, f_sync, s_sync, pause, stop, sh_cam_en, sh_retry_count)),
        ]

        procs = [multiprocessing.Process(target=t, args=a, daemon=True) for t, a in tasks]
        for p in procs: p.start()

        wait_start = time.time()
        is_boot_success = False
        while time.time() - wait_start < 12:
            if rdy.is_set():
                is_boot_success = True
                break
            if stop.is_set(): break
            time.sleep(0.5)

        if is_boot_success:
            logger.info("Camera verified READY. Core loop active.")
            break
        else:
            logger.error("Camera response timeout. Retrying...")
            stop.set()
            for p in procs:
                p.terminate()
                p.join(timeout=0.5)
            time.sleep(1.5)

    try:
        while not stop.is_set():
            if not procs[1].is_alive():
                logger.critical("Camera process died!")
                sys.exit(1)
            time.sleep(2.0)
    finally:
        stop.set()
        for p in procs: p.terminate()
        set_led(0)

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    while not check_time_server():
        blink_loop(1, 0.5, 0.5)
        time.sleep(1)
    run_core()
