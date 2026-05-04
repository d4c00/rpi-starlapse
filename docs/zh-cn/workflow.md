## My Usage

**The CAD drawing for the acrylic enclosure shown in the examples can be found at: [PMMA_3mm_BLK_Opaque_Matte_260408.dwg](https://github.com/d4c00/rpi-starlapse/raw/refs/heads/main/assets/PMMA_3mm_BLK_Opaque_Matte_260408.dwg)** 

Although there is no dedicated flat-field shooting option, the logic is exactly the same as bright-field shooting, so you don’t need special code to shoot flats either.  
For example, you can set `CAPTURE_BIAS_FRAMES` to `true`, shoot your flat fields first, then start shooting calibration frames. This way you get both flat/dark frames and bias frames. Flats are usually shot together with bias frames and used as a bundle.

---

For a single sender, the receiver will create a directory named after the device number, such as "01". In the example I'm using, the path `/mnt/ssd_data/podman/rpi-upload-srv/uploads/01` can support four folders, like this:

```
rpi-upload-srv
├── conf
│   ├── convert-tif.ini
│   ├── rpi-upload-srv.ini
│   └── time-lapse-maker.ini
├── fonts
├── output
└── uploads
    └── 01
        ├── biases  <<
        ├── darks   <<
        ├── flats   <<
        └── lights  <<
```

The `lights` folder contains the light frames (the actual images). The `darks`, `flats`, and `biases` are calibration frames. Only **mode 3** of rpi-upload-srv will use the calibration frames (alternatively, you can run `rpi-upload-srv-2` to convert them to TIF and then manually import them into Siril for stacking).

Only the `lights` folder is mandatory. The other three folders are optional — the video can still be generated even if they are missing.

If the exposure time for your flat frames is very short, you usually only need flats + bias frames.  
If the exposure time for your flat frames is very long, you may need dark flats. In that case, you can put the captured dark flats into the `biases` folder and use them as bias frames.

Running `rpi-upload-srv-3` will calibrate each light frame image, overlay the photo information in the top-left corner, and then stitch everything together into a final video.

---

In actual shooting, I usually prepare the Sender at home: pre-configuring parameters, ensuring the camera is disabled via the switch, and then connecting it to a power bank before wrapping it in plastic wrap for waterproofing.

Once at the dark-sky site, I set up the shooting angle, connect the Pi to my phone's hotspot, and `touch /dev/shm/time-lapse/01/switch` to turn the camera on.

I wait a moment for the auto-exposure algorithm to converge near the target luma (default 0.333). To verify the framing and exposure, I SSH into my home server (the Receiver) and run `systemctl --user restart rpi-upload-srv-2` to convert the incoming RAW files into JPEGs for a quick preview. Once everything looks good, I disconnect the hotspot and leave the device for a few hours.

When the session is over, I reconnect to the device, `touch /dev/shm/time-lapse/01/calibration`, and once I see the LED flashing to remind me, I simply block the lens with my power bank to capture dark frames on-site.

My home windows have no view of the Milky Way, which is why I use this "deploy and retrieve" workflow. However, if you have a location with a clear view, stable power, and Wi-Fi, you can keep the system running 24/7. Your backend server will then continuously receive and process real-time imagery from all your active nodes.

Back home, I power the Pi back on, connect it to the internal network that can reach the upload server, and it will automatically start uploading all the captured .raw files. The Server-side will then generate the video and convert files to TIF. Finally I use Siril to stack them and try to create beautiful final photos.

---
For capturing flats and dark-flats, I start a normal session and use two layers of cotton cloth over the lens with a phone flashlight or window light to adjust the exposure to a few seconds. I keep moving the cloth and the light source (if handheld) while capturing about 32 frames, then `touch /dev/shm/time-lapse/01/calibration` to shoot the matching dark frames (with bias capture disabled).

Afterward, I manually prune the lights directory of any uneven or improperly exposed frames, check the darks for light leaks, and finally rename lights to flats and darks to biases to fit the processing workflow.
