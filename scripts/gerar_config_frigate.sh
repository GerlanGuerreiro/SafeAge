#!/bin/sh
set -e

mkdir -p /config

sed \
  -e "s|{CAMERA_USER}|${CAMERA_USER}|g" \
  -e "s|{CAMERA_PASS}|${CAMERA_PASS}|g" \
  -e "s|{CAMERA_HOST}|${CAMERA_HOST}|g" \
  -e "s|{CAMERA_PORT}|${CAMERA_PORT}|g" \
  -e "s|{CAMERA_ENDPOINT}|${CAMERA_ENDPOINT}|g" \
  /config_template/config.camera.yml > /config/config.yml

echo "config.yml gerado com sucesso"
exec /init
