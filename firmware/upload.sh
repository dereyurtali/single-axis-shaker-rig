#!/bin/bash
# Compiles shaker.ino and flashes it to an Arduino Nano. No need to open the Arduino
# IDE; this uses the compiler and avrdude that ship inside it.
#
#   ./upload.sh --build-only   compile only, do not touch the board
#   ./upload.sh                find the port, confirm, flash
#   ./upload.sh /dev/cu.usbserial-10
#   ./upload.sh /dev/cu.usbserial-10 old     clone Nano with the old bootloader
#
set -euo pipefail

ONLY_BUILD=0
[ "${1:-}" = "--build-only" ] && { ONLY_BUILD=1; shift; }

AVR=/Applications/Arduino.app/Contents/Java/hardware/tools/avr
CORE=/Applications/Arduino.app/Contents/Java/hardware/arduino/avr
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"

[ -d "$AVR" ] || { echo "Arduino IDE not found: $AVR"; exit 1; }

# ---- port ----
PORT="${1:-}"
if [ $ONLY_BUILD -eq 0 ]; then
  if [ -z "$PORT" ]; then
    # The Nano's USB-serial chip shows up as cu.usbserial / cu.wchusbserial.
    # Bluetooth and the debug console also live under /dev/cu.*, so the name match
    # is kept narrow.
    #
    # No arrays (mapfile/readarray): macOS still ships bash 3.2, which has no
    # mapfile. Plain text plus a line count works everywhere.
    CANDS=$(ls /dev/cu.usbserial* /dev/cu.wchusbserial* /dev/cu.usbmodem* 2>/dev/null || true)
    [ -n "$CANDS" ] || { echo "No serial port found. Is the Nano plugged in?"; exit 1; }
    N=$(printf '%s\n' "$CANDS" | grep -c .)
    if [ "$N" -gt 1 ]; then
      echo "More than one port:"
      printf '%s\n' "$CANDS" | sed 's/^/  /'
      echo "Say which one:  ./upload.sh <port>"
      exit 1
    fi
    PORT=$(printf '%s\n' "$CANDS" | head -1)
  fi

  # Ask first. /dev/cu.* can hold devices other than the Nano, and flashing the
  # wrong one can brick it; avrdude will also lock the port and sit waiting for a
  # reply for minutes.
  SPEED=115200
  [ "${2:-}" = "old" ] && SPEED=57600
  echo "port  : $PORT"
  echo "speed : $SPEED baud"
  read -r -p "Flash this port? [y/N] " yn
  case "$yn" in [yY]) ;; *) echo "cancelled"; exit 1 ;; esac
fi

# ---- build ----
mkdir -p "$BUILD/core"
FLAGS="-Os -ffunction-sections -fdata-sections -mmcu=atmega328p -DF_CPU=16000000L
       -DARDUINO=10813 -DARDUINO_AVR_NANO -DARDUINO_ARCH_AVR
       -I$CORE/cores/arduino -I$CORE/variants/eightanaloginputs -w"

if [ ! -f "$BUILD/core.a" ]; then
  echo "compiling the core (once)…"
  for f in "$CORE"/cores/arduino/*.cpp; do
    "$AVR/bin/avr-g++" -c -std=gnu++11 -fpermissive -fno-exceptions \
      -fno-threadsafe-statics $FLAGS "$f" -o "$BUILD/core/$(basename "$f").o"
  done
  for f in "$CORE"/cores/arduino/*.c; do
    "$AVR/bin/avr-gcc" -c -std=gnu11 $FLAGS "$f" -o "$BUILD/core/$(basename "$f").o"
  done
  "$AVR/bin/avr-gcc-ar" rcs "$BUILD/core.a" "$BUILD"/core/*.o
fi

echo "compiling shaker.ino…"
{ echo '#include <Arduino.h>'; cat "$HERE/shaker/shaker.ino"; } > "$BUILD/shaker.cpp"
"$AVR/bin/avr-g++" -c -std=gnu++11 -fpermissive -fno-exceptions \
  -fno-threadsafe-statics $FLAGS "$BUILD/shaker.cpp" -o "$BUILD/shaker.o"
"$AVR/bin/avr-gcc" -Os -Wl,--gc-sections -mmcu=atmega328p \
  -o "$BUILD/shaker.elf" "$BUILD/shaker.o" "$BUILD/core.a" -lm
"$AVR/bin/avr-objcopy" -O ihex -R .eeprom "$BUILD/shaker.elf" "$BUILD/shaker.hex"
"$AVR/bin/avr-size" --format=avr --mcu=atmega328p "$BUILD/shaker.elf" | grep -E "Program|Data"

if [ $ONLY_BUILD -eq 1 ]; then
  echo; echo "Built: $BUILD/shaker.hex  (board untouched)"
  exit 0
fi

# ---- flash ----
echo "flashing…"
"$AVR/bin/avrdude" -C "$AVR/etc/avrdude.conf" -v -patmega328p -carduino \
  -P "$PORT" -b $SPEED -D -Uflash:w:"$BUILD/shaker.hex":i 2>&1 \
  | grep -Ev "^avrdude: (reading|writing|verifying) " | tail -25

echo
echo "Done. Now:  cd ../software && ./.venv/bin/python app.py"
