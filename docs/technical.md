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
I also wrote a separate auto-exposure algorithm that bypasses the ISP and supports long exposure. It only pulls up the gain when pulling the shutter time to the upper limit still results in underexposure.
<br>
<br>
One receiver can simultaneously receive and process photos from multiple senders, categorized by device number.<br>
The Raspberry Pi that actually captures and sends the photos acts as the **Client-side (sender)**. Any other Linux device can be used as the **Server-side (receiver)**.<br>
Although it might work with any Linux device that can connect to a camera, I separated it into sender and receiver mainly because my Raspberry Pi Zero2w has poor performance.
<br>
<br>
On the sender side, v4l2 commands are used to grab the .raw files, which are then securely transmitted to the receiver’s server via HTTPS encryption and token authentication.
If the receiver server has unstable network or is completely unreachable, the system intelligently handles retransmissions and temporarily stores the files on disk. You can also choose to skip the receiver entirely and simply copy the files out from the SD card manually using SFTP or a card reader.
<br>
<br>
<br>
For more details, please check the code yourself.
<br>
<br>

### Help Me Support More Hardware

Theoretically, as long as you are using a Linux-based device with a camera connected via the **MIPI interface** and controlled by **V4L2 drivers**, your hardware should be compatible. By referring to the file `rpi-starlapse/time-lapse/snippets/sensors/imx662.py` and filling in the **V4L2 control mappings** specific to your sensor's driver, it can be made to work. Other brands of Pi-like development boards may also be compatible.

I do not have additional hardware for testing, but I have done my best to ensure system generality. I would be very happy to receive feedback from users with different hardware.

If you can write a sensor configuration file for hardware different from mine and run it successfully, I would be extremely grateful if you could create a PR to help me support more sensors.

If you have any questions, you are more than welcome to contact me at any time.
<br>
<br>

