#!/bin/bash
# Build the DOS side with Open Watcom (portable snapshot in C:\WATCOM).
set -e
cd "$(dirname "$0")"
export WATCOM=C:/WATCOM PATH="/c/WATCOM/binnt64:$PATH" INCLUDE="C:/WATCOM/h"
# -bt=dos 16-bit DOS, -ms small model, -5 Pentium codegen, -fpi87 inline x87,
# -s no stack probes (the API handler runs on a private stack), -os size.
wcl -q -bt=dos -ms -5 -fpi87 -s -os -fe=braispk.exe braispk.c
wcl -q -bt=dos -ms -0 -os -fe=say.exe say.c
wcl -q -bt=dos -ms -5 -os -fpi87 -fe=pwmtest.exe pwmtest.c
python patch_talkhun.py          # third_party/brailab/TALKHUN.COM
ls -la braispk.exe say.exe TALKHUNS.COM
