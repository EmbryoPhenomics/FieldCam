#!/bin/bash
cd /home/pi/remote_ui
python deployment.py |& tee "$(ls -1q *stdout.txt | wc -l)_stdout.txt"


