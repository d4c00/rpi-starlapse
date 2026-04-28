# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

FROM python:slim

RUN groupadd -g 3012 rpi-upload-srv-user && useradd -u 3012 -g 3012 -m rpi-upload-srv-user
RUN apt-get update && apt-get install -y ffmpeg libgomp1 gcc python3-dev build-essential && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask tqdm gunicorn numpy opencv-python-headless Pillow tifffile scipy astroalign
RUN apt-get purge -y --auto-remove gcc python3-dev build-essential
RUN rm -rf /var/lib/apt/lists/*

COPY --chown=3012:3012 length /home/length

RUN chmod +x /home/length/entrypoint.sh

ENV MODE=1

WORKDIR /home/length/bin

USER 3012

ENTRYPOINT ["/bin/bash", "/home/length/entrypoint.sh"]
