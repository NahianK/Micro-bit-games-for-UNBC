#!/bin/bash
cd /home/pollen/treasure_hunt_reachy || exit 1
export PYTHONUNBUFFERED=1
exec /venvs/mini_daemon/bin/python agent.py --config /home/pollen/treasure_hunt_reachy/config.json

