#!/bin/bash
# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

read -p "Enter version number: " VERSION

if [ -z "$VERSION" ]; then
  echo "Error: Version number cannot be empty!"
  exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
podmanFILE_PATH="$SCRIPT_DIR/Dockerfile"

if [ ! -f "$podmanFILE_PATH" ]; then
  echo "Error: Dockerfile not found at '$podmanFILE_PATH'!"
  exit 1
fi

IMAGE_NAME="length/rpi-upload-srv:$VERSION"

if podman images -q "$IMAGE_NAME" 2> /dev/null | grep -q .; then
  echo "Warning: Image for version $VERSION already exists."
  read -p "Do you want to delete the existing image and rebuild? (y/n): " CONFIRM
  
  if [[ "$CONFIRM" == [Yy] ]]; then
    echo "Deleting existing image $IMAGE_NAME ..."
    podman rmi -f "$IMAGE_NAME"
    if [ $? -ne 0 ]; then
      echo "Error: Failed to delete image."
      exit 1
    fi
  else
    echo "Build canceled."
    exit 0
  fi
fi

echo "Starting build for image: $IMAGE_NAME ..."
podman build -t "$IMAGE_NAME" -f "$podmanFILE_PATH" --build-arg VERSION=$VERSION "$SCRIPT_DIR"

if [ $? -eq 0 ]; then
  echo "Successfully built image: $IMAGE_NAME"
else
  echo "Error: Image build failed!"
  exit 1
fi