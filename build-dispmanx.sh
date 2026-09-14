#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

gcc -std=c99 -O3 -Wall -Wextra \
    -I/opt/vc/include \
    -I/opt/vc/include/interface/vcos/pthreads \
    -I/opt/vc/include/interface/vmcs_host/linux \
    -L/opt/vc/lib -Wl,-rpath,/opt/vc/lib \
    -o dispmanx-grab dispmanx-grab.c \
    -lbcm_host -lvcos -lvchiq_arm -pthread -lrt

echo "Built $(pwd)/dispmanx-grab"
