#!/bin/bash

rmmod dummy
set -x
set -e

modprobe dummy
ifconfig dummy0
ip link set name eth0 dev dummy0
ifconfig eth0 hw ether 02:16:3e:1d:d3:5b
ifconfig eth0
