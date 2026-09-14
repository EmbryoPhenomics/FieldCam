#!/bin/bash

nmcli con add type wifi ifname wlan0 con-name lic_hotspot_2 autoconnect yes ssid lic_hotspot_2
nmcli con modify lic_hotspot_2 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
nmcli con modify lic_hotspot_2 wifi-sec.key-mgmt wpa-psk
nmcli con modify lic_hotspot_2 wifi-sec.psk "lic_hotspot_2_1234"
nmcli con up lic_hotspot_2
