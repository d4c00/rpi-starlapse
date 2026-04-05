#!/bin/bash
# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

CONF_DIR="/home/length/conf"
BACKUP_DIR="/home/length"
FONT_DIR="/home/length/fonts"
FONT_FILE="VCR_OSD_MONO_1.001.ttf"

FILES=("rpi-upload-srv.ini" "time-lapse-maker.ini" "convert-tif.ini")

echo ">>> Checking configurations in $CONF_DIR..."

for FILE in "${FILES[@]}"; do
    if [ ! -f "$CONF_DIR/$FILE" ]; then
        echo "Warning: $FILE not found in $CONF_DIR."
        if [ -f "$BACKUP_DIR/$FILE" ]; then
            echo "Copying default $FILE from $BACKUP_DIR to $CONF_DIR..."
            cp "$BACKUP_DIR/$FILE" "$CONF_DIR/$FILE"
        else
            echo "Error: Default $FILE not found in $BACKUP_DIR. Application might fail."
        fi
    else
        echo "OK: $FILE exists."
    fi
done

echo ">>> Checking fonts in $FONT_DIR..."
mkdir -p "$FONT_DIR"
if [ ! -f "$FONT_DIR/$FONT_FILE" ]; then
    if [ -f "$BACKUP_DIR/$FONT_FILE" ]; then
        echo "Copying $FONT_FILE to $FONT_DIR..."
        cp "$BACKUP_DIR/$FONT_FILE" "$FONT_DIR/"
    else
        echo "Warning: $FONT_FILE not found in $BACKUP_DIR."
    fi
else
    echo "OK: $FONT_FILE exists."
fi

TARGET_MODE=${MODE:-1}

echo "Current Mode: $TARGET_MODE"

case "$TARGET_MODE" in
    "1")
        echo ">>> [Mode 1] Starting rpi-upload-srv.py ..."
        exec gunicorn -w 2 -b 0.0.0.0:8443 --access-logfile - --error-logfile - rpi-upload-srv:app
        ;;
    "2")
        echo ">>> [Mode 2] Starting convert-tif.py ..."
        python3 /home/length/bin/convert-tif.py
        ;;
    "3")
        echo ">>> [Mode 3] Starting time-lapse-maker.py ..."
        python3 /home/length/bin/time-lapse-maker.py
        ;;
    *)
        echo "Error: Unknown MODE '$TARGET_MODE'. Use 1 or 2 or 3."
        exit 1
        ;;
esac