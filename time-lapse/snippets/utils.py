# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, time, sys, logging, subprocess, random, shutil, socket
from datetime import datetime, UTC
from snippets.config import *
from snippets.sensors import sensor

def handle_net_failure(is_online_val, logger, filename=None):
    if is_online_val.value:
        msg = f"Network interrupted" + (f" on {filename}" if filename else "")
        logger.warning(f"[NET] {msg}. Switching to OFFLINE.")
        is_online_val.value = False

def pack_snap(id_val, t_us, g, ev, y):
    return f"{id_val}|{int(t_us)}|{float(g):.1f}|{float(ev):.2f}|{float(y):.3f}"

def unpack_snap(snap_str):
    try:
        s = snap_str.decode() if isinstance(snap_str, bytes) else snap_str
        parts = s.split('|')
        return {
            "id": int(parts[0]),
            "t_us": int(parts[1]),
            "g": float(parts[2]),
            "ev": float(parts[3]),
            "y": float(parts[4])
        }
    except:
        return {"id":0, "t_us":666666, "g":34.0, "ev":0.0, "y":0.0}

def safe_put_queue(q, item, logger=None):
    try:
        q.put_nowait(item)
    except Exception:
        pass
    max_limit = getattr(q, '_maxsize', 0) 

    if q.qsize() > max_limit and max_limit > 0:
        try:
            temp_list = []
            while not q.empty():
                temp_list.append(q.get_nowait())

            temp_list.sort(key=lambda x: x['name'])
            oldest_item = temp_list.pop(0)

            for i in temp_list:
                q.put_nowait(i)
                
            return True, oldest_item
        except Exception as e:
            if logger: logger.error(f"Critical Queue Overflow Error: {e}")
            
    return True, None

def dispatch_to_manager(q, prefix, dev_id, p, src_path, logger=None):
    if not is_valid_raw(src_path):
        cleanup_shm(src_path)
        return False

    fname = generate_raw_filename(prefix, dev_id, p["t_us"], p["g"], p["ev"], p["y"])
    dest_path = os.path.join(SHM_QUEUE, fname)

    try:
        os.replace(src_path, dest_path)
        item = {"name": fname, "path": dest_path, "s_us": p["t_us"], "g": p["g"], "retry": 0, "id": p.get("id", 0)}

        _, overflow_item = safe_put_queue(q, item, logger)

        if overflow_item:
            if is_valid_raw(overflow_item["path"]):
                move_to_local_storage(overflow_item, logger)
            else:
                cleanup_shm(overflow_item["path"])
        
        return True
    except Exception as e:
        if logger: logger.error(f"Dispatch logic failure: {e}")
        return False

def move_to_local_storage(it, logger=None):
    if not is_valid_raw(it["path"]): return False

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR, exist_ok=True)
        
    prefix = it["name"].split('_')[0]
    t_dir = os.path.join(SAVE_DIR, SUB_DIRS.get(prefix, ""))

    try:
        os.makedirs(t_dir, exist_ok=True)
        shutil.move(it["path"], os.path.join(t_dir, it["name"]))
        return True
    except Exception as e:
        if logger: logger.error(f"Storage move failed: {e}")
        return False

def disable_config_cam(sh_cam_en=None, path="snippets/config.py"):
    if sh_cam_en is not None:
        sh_cam_en.value = False

    try:
        if not os.path.exists(path): return
        with open(path, "r") as f: content = f.read()
        if "CAMERA_ENABLED = True" in content:
            with open(path, "w") as f: 
                f.write(content.replace("CAMERA_ENABLED = True", "CAMERA_ENABLED = False"))
    except: pass

def setup_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger

def cleanup_shm_env():
    for d in ["tmp", "ready", "queue"]:
        path = os.path.join(SHM_ROOT, d)
        if os.path.exists(path): shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)

def get_shm_paths(dev_id_str):
    return (
        os.path.join(SHM_ROOT, "tmp", f"w_{dev_id_str}.raw"),
        os.path.join(SHM_ROOT, "ready", f"r_{dev_id_str}.raw")
    )

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(int(f.read()) / 1000)
    except: return 0

def generate_raw_filename(prefix, dev_id, s_us, g, ev, m):
    now = datetime.now(UTC)
    return f"{prefix}_{dev_id}_{now.strftime('%Y%m%d_%H%M%S')}_T{s_us/1000:.1f}_G{g:.1f}_E{ev:.1f}_Y{m:.3f}_CPU{get_cpu_temp()}.raw"

def cleanup_shm(*paths):
    for p in paths:
        try:
            if os.path.exists(p): os.remove(p)
        except: pass

def pet_watchdog():
    addr = os.getenv("NOTIFY_SOCKET")
    if not addr: return
    try:
        if addr.startswith("@"): addr = "\0" + addr[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(b"WATCHDOG=1", addr.encode())
    except: pass

def is_valid_raw(path):
    try:
        if not os.path.exists(path): return False
        if os.path.getsize(path) != sensor.EXACT_RAW_SIZE:
            print(f"[CLEANUP] Size mismatch: {path}. Deleting.")
            cleanup_shm(path)
            return False
        sample_count = 10000
        with open(path, "rb") as f:
            for _ in range(sample_count):
                f.seek(random.randint(0, sensor.EXACT_RAW_SIZE - 1))
                if ord(f.read(1) or b'\x00') != 0:
                    pet_watchdog()
                    return True
        print(f"[CLEANUP] All zeros: {path}. Deleting.")
        cleanup_shm(path)
        return False
    except Exception as e:
        print(f"[ERROR] is_valid_raw: {e}")
        return False

def get_local_photos(limit=100):
    res = []
    for sub in SUB_DIRS.values():
        d = os.path.join(SAVE_DIR, sub)
        if os.path.isdir(d):
            with os.scandir(d) as it:
                res.extend([e.path for e in it if e.is_file() and e.name.endswith(".raw")])
    res.sort()
    return res[:limit]

def check_and_clean_disk():
    try:
        usage = shutil.disk_usage(SAVE_DIR)
        if (usage.free / usage.total) >= DISK_THRESHOLD: return
        old_files = get_local_photos(limit=50)
        if old_files:
            print(f"[DISK] Space Low ({usage.free//1024**2}MB free). Cleaning {len(old_files)} files...")
            for fname in old_files: cleanup_shm(fname)
    except Exception as e:
        print(f"[DISK] Cleanup error: {e}")

def set_led(state):
    try:
        with open(LED_PATH, 'w') as f: f.write(str(state))
    except: pass

def flash_led(d=0.05):
    set_led(1); time.sleep(d); set_led(0); time.sleep(d)

def blink_loop(t, on, off):
    for _ in range(t): set_led(1); time.sleep(on); set_led(0); time.sleep(off)

def check_time_server():
    return subprocess.run(f"curl -I -s --connect-timeout 5 {TIME_SOURCE} | grep -i 'date:'", shell=True).returncode == 0

def api_upload(session, filename, path):
    headers = {
        "X-Device-Token": DEVICE_TOKEN,
        "X-Device-Id": DEVICE_ID,
        "X-Filename": filename,
        "Content-Type": "application/octet-stream"
    }
    try:
        with open(path, "rb") as f:
            resp = session.post(SERVER_URL, data=f, headers=headers, timeout=(3, 15))
        return resp
    except Exception as e:
        print(f"[NET-ERROR] Upload failed: {type(e).__name__} - {e}")
        return None

def log_pic(mode, filename, status, info):
    print(f"[{mode}] {filename} | {status} | {info}", flush=True)

def upload_with_retry(sess, filename, path, mode_label, info_prefix, is_online_val, stop_ev, sh_retry_count, r_limit=5):
    if not os.path.exists(path): return False
    if not is_valid_raw(path): return True

    actual_limit = r_limit if is_online_val.value else 0

    for r in range(actual_limit + 1):
        if stop_ev.is_set(): return False

        resp = api_upload(sess, filename, path)
        if resp and resp.status_code == 200:
            is_online_val.value = True
            sh_retry_count.value = 0
            log_pic(mode_label, filename, "OK", f"{info_prefix} | R:{r}")
            cleanup_shm(path)
            return True

        err_msg = f"HTTP:{resp.status_code}" if resp else "TIMEOUT"
        wait_sec = 0.1 * (3 ** r) if (r < actual_limit and is_online_val.value) else 0

        print(f"[{mode_label}] {filename} | FAIL ({err_msg}) | Retry:{r}/{actual_limit} | NextWait:{wait_sec:.1f}s", flush=True)

        if not is_online_val.value: return False

        if r < actual_limit:
            time.sleep(0.1 * (3 ** r))

    if is_online_val.value:
        handle_net_failure(is_online_val, setup_logger("NET"), filename)
    return False

def advance_frame(sh_frame_id, sh_last_ae_id):
    sh_frame_id.value += 1
    sh_last_ae_id.value = sh_frame_id.value

def get_optimal_queue_size() -> int:
    frame_size = sensor.EXACT_RAW_SIZE
    usage = shutil.disk_usage("/dev/shm")
    num_frames = int((usage.free * 0.9) // frame_size)
    if num_frames < 1:
        raise MemoryError(f"SHM Space Exhausted! Free: {usage.free//1024}KB")
    print(f"[SHM-DYNAMIC] Queue size set to {num_frames} based on physical memory.")
    return num_frames