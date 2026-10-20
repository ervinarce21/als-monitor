# ESP32 Firmware Investigation Guide

This guide explains how to locate, inspect, test, and safely modify the ESP32
firmware used by the NEXA grip monitor.

## 1. What Is Currently in This Repository

No ESP32 firmware source (`.ino`, `.cpp`, `.h`, or PlatformIO project) is
currently stored in this repository. The repository contains the Python code
that consumes data from the controller:

- `src/als_monitor/grip_monitor/main.py`
- `nexa_ui/grip_calibration.py`
- `nexa_ui/config.py`

The current host-side contract is:

| Setting | Required value |
|---|---|
| Connection | USB serial |
| Raspberry Pi port | `/dev/ttyUSB0` by default |
| Windows port | A device-specific port such as `COM3` |
| Baud rate | `115200` |
| Encoding | ASCII or UTF-8 compatible text |
| Record format | `right_counts,left_counts` |
| Record terminator | Newline (`\n`) |
| Values | Two finite numeric raw readings |

Example output:

```text
59521,-113984
59518,-113991
```

The first value is always the **right** load-cell channel and the second value
is the **left** channel. Calibration and conversion to newtons happen in the
Python application, so the firmware should normally transmit stable raw ADC
counts rather than calibrated force.

## 2. Find the Original Firmware Source

Before changing or flashing the board, search the development machines, old
project folders, removable media, and Git history.

### Windows PowerShell

```powershell
Get-ChildItem "$HOME\Documents" -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in '.ino', '.cpp', '.h', '.hpp' -or $_.Name -eq 'platformio.ini' } |
  Select-Object FullName
```

### Raspberry Pi

```bash
find "$HOME" -type f \( -name '*.ino' -o -name '*.cpp' -o -name '*.h' \
  -o -name '*.hpp' -o -name 'platformio.ini' \) 2>/dev/null
```

### Search this repository's Git history

```bash
git log --all --name-only -- '*.ino' '*.cpp' '*.h' 'platformio.ini'
git log --all -S 'HX711' --oneline
git branch --all
git remote -v
```

Also check Arduino IDE's configured sketchbook directory and PlatformIO's
recent-project list. Ask whoever programmed the board for the exact source,
board model, pin map, library versions, and last known working commit.

An ESP32 cannot reconstruct the original C/C++ source from its installed
firmware. Flash contents can be backed up as binary data, but decompilation will
not recover meaningful source names, comments, or the original project.

## 3. Identify the Hardware Before Opening Code

Disconnect external power and photograph both sides of the controller and load
cell interface. Record:

- ESP32 board/module marking, such as ESP32-WROOM or ESP32-S3.
- USB-to-serial chip, such as CP210x, CH340, or native USB.
- Load-cell ADC model. A common choice is HX711, but verify the actual board.
- GPIO connections for each ADC's data and clock pins.
- Supply voltage and grounding arrangement.
- Which physical load cell is left and which is right.

Do not connect 5 V logic directly to an ESP32 GPIO. Confirm the ADC breakout's
logic voltage and wiring from its documentation before probing or rewiring it.
Remove mechanical load before disconnecting load-cell wires.

## 4. Confirm the Serial Device

Close NEXA, Arduino Serial Monitor, and every other program that may hold the
serial port. Only one program can normally use the port at a time.

### Windows

```powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Name, PNPDeviceID
```

Unplug and reconnect the ESP32 to identify which `COM` entry disappears and
returns.

### Raspberry Pi

```bash
ls -l /dev/serial/by-id/ /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
dmesg | tail -n 30
```

Prefer the stable `/dev/serial/by-id/...` path during investigation when one is
available. The application currently defaults to `/dev/ttyUSB0`.

## 5. Observe the Existing Firmware Without Flashing

Install pyserial in the active Python environment if necessary:

```bash
python3 -m pip install pyserial
```

Open a read-only serial terminal on Raspberry Pi:

```bash
python3 -m serial.tools.miniterm /dev/ttyUSB0 115200
```

Or on Windows:

```powershell
py -3 -m serial.tools.miniterm COM3 115200
```

Press `Ctrl+]` to exit miniterm. Opening the port may reset the ESP32; the NEXA
calibration screen deliberately waits two seconds after opening it.

Observe and record:

1. Whether startup messages appear after reset.
2. Whether every data line contains exactly two comma-separated numbers.
3. The idle values for both channels.
4. Which value changes when only the left grip is loaded.
5. Which value changes when only the right grip is loaded.
6. Whether counts increase or decrease under load.
7. Approximate lines per second.
8. Drift, jumps, repeated values, missing lines, or malformed output.

If left loading changes the first number, the firmware channel order is wrong
for NEXA. Fix the mapping in firmware or deliberately change the complete
host-side contract; do not silently swap only one consumer.

## 6. Read the Source Systematically

Once the original project is found, make a copy or Git branch before editing.
Identify the following sections.

### Board and build configuration

- Arduino IDE board name or PlatformIO `board` identifier.
- CPU frequency, USB mode, flash size, and partition scheme.
- Framework and library versions.
- Conditional compilation flags and environment-specific settings.

### Pin mapping

Look for `#define`, `const`, or constructor arguments naming pins such as:

```cpp
RIGHT_DOUT
RIGHT_SCK
LEFT_DOUT
LEFT_SCK
```

Compare every definition with the photographed wiring. Check that selected
pins are valid for the exact ESP32 variant and are not problematic boot
strapping or flash pins.

### Sensor initialization

Find where both ADC objects are created and initialized. Confirm that:

- Both channels are initialized once.
- The code waits for each ADC to become ready instead of blocking forever.
- Gain and sample-rate settings match the installed ADC board.
- A missing sensor produces a controlled error rather than stale measurements.

### Main acquisition loop

Trace the path from ADC read to `Serial.print`. Confirm that one complete pair
comes from approximately the same sampling instant and that the output order is
right then left:

```cpp
Serial.print(right_counts);
Serial.print(',');
Serial.println(left_counts);
```

Look for long `delay()` calls, dynamic `String` creation, excessive averaging,
Wi-Fi/Bluetooth tasks, or debug output that could introduce pauses. Determine
whether filtering occurs in firmware; document any averaging or smoothing
because it changes peak-force response and comparability between sessions.

### Startup and fault behavior

Check what happens when one ADC is disconnected, returns invalid data, or never
becomes ready. A watchdog reset loop or indefinite wait will appear to NEXA as
an empty graph. Diagnostic text is useful during development, but production
output should remain a clean numeric stream.

## 7. Determine the Build System

An Arduino project normally contains a directory and `.ino` file with matching
names. A PlatformIO project normally contains `platformio.ini`, `src/`, and
possibly `include/` and `lib/`.

### Arduino CLI inspection

```bash
arduino-cli version
arduino-cli board list
arduino-cli core list
arduino-cli lib list
```

Compile only after identifying the correct fully qualified board name:

```bash
arduino-cli compile --fqbn <vendor:architecture:board> <sketch-directory>
```

### PlatformIO inspection

```bash
pio --version
pio project config
pio run
```

Compilation is safe for the connected board because it does not upload. Save
the full build output, including board target, dependency versions, warnings,
flash usage, and RAM usage.

## 8. Back Up Before Uploading

Do not upload merely to test whether a project compiles. First establish that
the source belongs to this hardware and preserve the working state.

At minimum, save:

- The discovered source tree and Git revision.
- Photos and a written pin map.
- Existing serial output under idle, left-load, and right-load conditions.
- Current NEXA calibration file: `nexa_data/grip_calibration.json`.
- Board type, flash size, MAC address, and installed USB driver details.

`esptool` can identify the chip and read flash, but use the command appropriate
to the installed esptool version and verified flash size:

```bash
python3 -m esptool --port /dev/ttyUSB0 chip_id
python3 -m esptool --port /dev/ttyUSB0 flash_id
```

Reading flash is not a source-code backup. Do not erase flash, change security
settings, or write flash while investigating. Flash encryption or secure boot
may also make a binary backup unusable on another board.

## 9. Add Diagnostics Safely

Use a compile-time flag so diagnostic output cannot accidentally ship in the
production measurement stream:

```cpp
#define NEXA_DEBUG 0

#if NEXA_DEBUG
  Serial.printf("# right_ready=%d left_ready=%d\n", rightReady, leftReady);
#endif
```

Lines beginning with `#` are currently ignored by the grip monitor because
they are not valid two-number records, but they consume serial bandwidth and
can affect timing. Disable them for measurement runs. Prefer a second debug
interface or infrequent counters when available.

Useful diagnostics include:

- Successful initialization of each ADC.
- Ready/not-ready and timeout counts per channel.
- Minimum, maximum, and mean loop interval.
- Number of samples transmitted.
- Reset reason and brownout events.
- Raw channel values before any filtering.

Avoid printing personal identifiers or clinical results from firmware.

## 10. Validate a Candidate Firmware Build

Perform these checks before using it in an assessment:

1. **Boot:** It starts reliably after power-up and after the serial port opens.
2. **Format:** Every production line is `right_counts,left_counts` plus newline.
3. **Isolation:** Loading one grip changes only its expected channel.
4. **Idle stability:** Both channels remain reasonably stable without load.
5. **Direction:** Record whether each channel rises or falls under compression.
6. **Rate:** Output is continuous, with no multi-second gaps or bursts.
7. **Overload:** Expected maximum grip does not saturate the ADC.
8. **Disconnect:** A missing sensor fails visibly and does not emit believable
   stale values.
9. **Long run:** Observe at least 10 minutes for drift, resets, and USB errors.
10. **Recalibration:** Recalibrate both hands in NEXA after firmware, wiring,
    filtering, ADC rate, or mechanical changes.

Run the standalone host monitor after the serial checks:

```bash
PYTHONPATH=src python3 -m als_monitor.grip_monitor
```

Then use **NEXA UI > System > Calibrate grips** with a known mass. The Python
calibration averages 50 fresh readings and stores each hand independently in
`nexa_data/grip_calibration.json`.

## 11. Common Fault Patterns

| Symptom | Investigate |
|---|---|
| No serial port | USB cable, power, driver, board USB mode, damaged connector |
| Port exists but no text | Wrong baud rate, firmware blocked waiting for ADC, wrong port |
| Unreadable characters | Baud mismatch or binary output |
| NEXA graph stays empty | Labels/debug text, missing comma/newline, nonnumeric values |
| Left and right inverted | Firmware print order or physical ADC wiring |
| Flat line | ADC not ready, wrong pins, disconnected bridge, stale-value loop |
| Large jumps | Loose wiring, power noise, grounding, mechanical movement, USB resets |
| Slow or bursty updates | Excessive averaging, blocking waits, delays, debug output |
| Force is wrong but raw data moves | Calibration, load direction, mechanical leverage |
| Values reset periodically | Brownout, watchdog, unstable supply, USB power problem |

## 12. Bring the Firmware Into This Repository

Once the verified source is found, store it in a dedicated directory such as:

```text
firmware/
  esp32_grip_monitor/
    platformio.ini          # for PlatformIO, if used
    src/
      main.cpp
    README.md
```

Or preserve the required Arduino sketch directory naming:

```text
firmware/
  esp32_grip_monitor/
    esp32_grip_monitor.ino
```

Its README should record the exact board, pin map, ADC/library versions,
protocol, output rate, build command, upload command, and a changelog for any
measurement-affecting modification. Commit the source and configuration, but
do not commit participant data, calibration files, build directories, serial
logs containing sensitive information, or device-specific secrets.

## Investigation Record

Fill this in while examining the deployed board:

```text
Date:
Investigator:
ESP32 board/module:
USB serial chip:
Serial device:
Firmware source location:
Git revision:
Build system and version:
Board target:
Flash size:
Right ADC model and pins:
Left ADC model and pins:
Observed output order:
Observed output rate:
Idle counts (right, left):
Loaded counts (right, left):
Filtering/averaging:
Known issues:
Backup location:
Validation result:
```
