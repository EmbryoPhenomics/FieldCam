#!/bin/bash
sudo apt-get update
sudo apt-get install python3-pip -y
sudo apt-get install ffmpeg -y
sudo apt-get install python3-opencv -y
pip3 install -r ./requirements.txt --break-system-packages
