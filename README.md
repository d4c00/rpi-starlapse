### The development has moved to Codeberg / 开发已迁移至 Codeberg:<br>https://codeberg.org/length/rpi-starlapse
<br>

## Raspberry Pi Starry Sky Time-Lapse Photography

<div align="center">
  <h3>
    <a href="/README.md">English</a> &nbsp; | &nbsp; <a href="/docs/zh-cn/README.md">简体中文</a>
  </h3>
</div>

* **Automated Long-Exposure**
* **Multi-Node Capture and Automated Backend Upload**
* **Automatically make time-lapse videos using Star-Aligned Sliding Stacking**

<div align="center">
  <img src="https://assets.length.cc/media/2026_04_08_1.jpg" width="25%" />
  <img src="https://assets.length.cc/media/2026_04_08_2.jpg" width="25%" />
  <img src="https://assets.length.cc/media/2026_04_08_3.jpg" width="25%" />
</div>

###### but it might not be limited to just the Raspberry Pi, and it might not even be limited to starry skies.

Stacking 756 frames in Siril：<br>
<div align="center">
  <img src="https://assets.length.cc/media/2026_04_26.jpg" width="100%" />
</div>

Receiver (Server) Mode 3 Star-Aligned Sliding Stacking video sample (Single frame from video, 65 frames per stack):<br>
<div align="center">
  <img src="https://assets.length.cc/media/20260425_212341~20260426_051319.jpg" width="100%" />
</div>

**Watch on YouTube:** [20260425_212341~20260426_051319.mp4](https://youtu.be/1oTHF_3T_xM)
> **Solved Map:** [Astrometry](https://nova.astrometry.net/user_images/15167486) <br>

## COST: $54.37
###### The reason for choosing this combination is to capture clear infrared Milky Way images in light-polluted cities at a low cost.<br>Unit costs for the core components are as follows:
    Raspberry Pi Zero 2W: $18.98
    IMX662 Module: $24.50
    800nm Long-pass Filter + 8mm f/1.2 M12 Lens: $10.89
    Total: $54.37 (excluding SD card, power bank, cables, acrylic enclosure, and aluminum heatsinks).
###### Below is my approximate architecture:
    Sender (Pi) (Supports multiple devices via IDs: 01, 02...)
     ├── capture (v4l2)
     ├── buffer (/dev/shm)
     └── upload (HTTPS)
     
    Receiver (Server)
     ├── upload handler
     ├── RAW processing
     ├── calibration
     └── timelapse rendering

# [ Getting Started ]

### [Installation](docs/en/installation.md)<br> <sup>How to set up the software and hardware from scratch.</sup>

### [Technical Details](docs/en/technical.md)<br> <sup>How it works: sensors, logic, and why I chose these parts.</sup>

### [Workflow](docs/en/workflow.md)<br> <sup>How to use it in the field and process your photos.</sup>

### [FAQ](docs/en/faq.md)<br> <sup>Quick fixes for common hardware and connection issues.</sup>
<br>

###### Last Updated: 2026-05-04

###### Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)<br>Licensed under the MIT License.<br>Font (RedHatMono-Regular.ttf): Designed by MCKL. Licensed under SIL Open Font License 1.1.
