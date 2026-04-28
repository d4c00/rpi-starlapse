## Explanation
<div align="center">
  <img src="./img/2026_04_01.jpg" width="75%" />
</div>
IMX662 Module and Raspberry Pi Zero 2W Integration

<br>
The Zero 2W was selected because it is compact and power-efficient; its performance is modest but sufficient for the task.

I chose the IMX662 because STARVIS 2 offers high QE (Quantum Efficiency) in the infrared spectrum while remaining affordable. However, the 74.25 MHz crystal oscillator I’m using might not be ideal for long exposures; a module with a 24 MHz oscillator—the lowest supported by the IMX662—might be more suitable.

Bortle Class 8 city, 9.5s exposure, 90 gain. Captured the Milky Way core using 756 light frames, calibrated with darks, flats, and dark flats.<br>
<div align="center">
  <img src="./img/2026_04_26.jpg" width="100%" />
</div>
For example, this one was shot with an 11% distortion lens without a tracker; after stacking with Siril's auto-alignment, you can see coma-like effects at the edges.<br>
If you don't have a star tracker but want to stack photos, choose a lens with minimal distortion if possible.<br>
<br>
By pairing it with an 800nm long-pass filter, the color sensor can function like a mono sensor (though faint Bayer patterns remain), achieving the same sharpness and clarity as a true mono sensor. The filter is an 8.5mm diameter interference filter attached to the back of the M12 lens (facing the sensor). The filter and lens were pre-assembled by the seller.
<br>


<img src="./img/2026_04_12.jpg" width="30%" /> Although it will affect heat dissipation, I made a simple waterproof cover using plastic wrap and rubber bands.<br>

Currently, it is only considered to be treated as a **monochrome** sensor. First, debayering under an 800nm long-pass filter is both troublesome and may reduce sharpness.<br>
The disadvantage is that color sensors will still have a faint grid-like feel (traces of the Bayer array), unless you are using a true monochrome sensor.
<br>
<br>
<br>
<br>

I separated it into sender and receiver.

## Sender (Pi)
Although it might work with any `Linux` device that can connect to a camera, I assume `Raspberry Pi OS` as the default environment. I have not tested other operating systems; I used the latest official `Raspberry Pi OS Lite` version for development.
<br>

Basically, it's a "set it and forget it" box. You set your capture intervals in `config.py`, and the system handles the rest. If you want to calibrate it (Darks/Biases), you just drop a trigger file into the folder.

### How it actually works (Step-by-Step)

#### 1. Getting Ready
When you turn it on, the system doesn't just start snapping photos. It waits for `check_time_server` to confirm the time is right so your filenames aren't messed up. Then, it wipes the temporary RAM folder (`/dev/shm`) to start fresh and figures out how many photos it can fit in RAM without crashing the Pi. Finally, it starts seven different "workers" (separate processes) to handle different jobs.

#### 2. Talking to the Camera (V4L2)
The system automatically finds the camera hardware. It looks through the Pi's system files, matches the camera model to its internal drivers, and sets up the raw format. Instead of using high-level software, it talks directly to the sensor using `ioctl` commands.

#### 3. Taking the Shot
The `timer_worker` is the boss of the schedule. Every time the clock hits your interval (like every 10 seconds), it tells the `camera_worker` to go.
* The camera worker maps a piece of memory (`mmap`) to grab the raw data.
* It turns the sensor on, grabs **exactly one frame**, and turns it off immediately. This keeps the sensor cool and saves power.
* The raw photo is saved directly to RAM, not the SD card (to keep it fast and save the card from wearing out).

#### 4. Auto-Exposure
As soon as a photo hits the RAM, the `ae_worker` grabs it. It looks at the brightness and decides if the next photo needs to be brighter or darker. 
* It adjusts the **shutter speed first** because that’s cleaner. 
* It only cranks up the **gain (ISO)** if it’s so dark that the shutter speed can't go any slower without hitting the next interval.
* It saves these new settings to a shared memory area so the camera worker knows what to do for the next shot.

#### 5. Handling the Data (Upload & Backup)
Now the `memory_manager_worker` takes the photo from RAM and tries to send it to the server via HTTPS.
* **If the internet is working:** It uploads the photo and deletes the RAM copy instantly.
* **If the internet is down:** It doesn't give up. It moves the photo from RAM to the **SD card** for safekeeping.
* **Catching up:** While the camera keeps taking new photos, a `sync_worker` stays in the background. As soon as the internet comes back, it starts quietly uploading those old photos from the SD card in the "gaps" between new shots so it doesn't lag the system.

#### 6. Staying Alive
The whole time this is happening, the system "pets" the watchdog. If any of the workers get stuck or the camera stops responding, the system realizes it, and restarts itself. It also blinks the Pi's LED in different patterns so you can see if it's syncing time, taking a photo, or if the internet is dead just by looking at the box.
<br>
<br>
<br>

## Receiver (Server)

Any other Linux device can be used as the **Server-side (receiver)**.<br>

One receiver can simultaneously receive and process photos from multiple senders, categorized by device number.<br>

3 Working Modes:

**Mode 1: Basic Storage**<br>
Simply receives and saves the `.raw` files from Senders.

**Mode 2: Auto-Convert (JPG/TIF) & Single-Frame Stacking**<br>
The system automatically converts incoming .raw files into .jpg or .tif formats.<br>
In this mode, the Stack function acts as a single-frame output.<br>
It uses the "moving center" logic to stack a few photos and output one clean, high-quality image.

**Mode 3: Full Time-lapse Production**<br>
This is the complete pipeline. <br>
It performs Star-Aligned Sliding Stacking for every frame, applies post-processing (denoise, contrast, etc.), and automatically renders the final time-lapse video.


<br>
<br>
<br>
For more details, please check the code yourself.
<br>
<br>

## Help Me Support More Hardware

Theoretically, as long as you are using a Linux-based device with a camera connected via the **MIPI interface** and controlled by **V4L2 drivers**, your hardware should be compatible. By referring to the file `rpi-starlapse/time-lapse/snippets/sensors/imx662.py` and filling in the **V4L2 control mappings** specific to your sensor's driver, it can be made to work. Other brands of Pi-like development boards may also be compatible.

I do not have additional hardware for testing, but I have done my best to ensure system generality. I would be very happy to receive feedback from users with different hardware.

If you can write a sensor configuration file for hardware different from mine and run it successfully, I would be extremely grateful if you could create a PR to help me support more sensors.

If you have any questions, you are more than welcome to contact me at any time.
<br>
<br>

