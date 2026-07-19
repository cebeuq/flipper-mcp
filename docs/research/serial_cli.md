# Flipper Zero Serial CLI — Implementation Reference (firmware 1.x / current `dev`)

Sourced directly from firmware source (`flipperdevices/flipperzero-firmware`, `dev` branch — the post-refactor pipe/registry/shell architecture used by the 1.x releases incl. ~1.4.x). Every prompt/output string below is quoted verbatim from the C source. Key files:

- `lib/toolbox/cli/shell/cli_shell.c`, `cli_shell_line.c` — shell, prompt, echo, line editing
- `lib/toolbox/cli/cli_ansi.h` — key codes (ETX=0x03), ANSI macros
- `lib/toolbox/cli/cli_command.c` / `.h` — `cli_print_usage`, flags, `CLI_COMMAND_INTERFACE`
- `applications/services/cli/cli_vcp.c` — USB CDC transport
- `applications/services/cli/cli_main_commands.c`, `cli_command_gpio.c`, `cli_main_shell.c`
- `applications/services/storage/storage_cli.c`, `power/power_cli.c`, `loader/loader_cli.c`, `input/input_cli.c`, `bt/bt_cli.c`, `rpc/rpc.c` + `rpc_cli.c`
- `applications/main/{subghz,nfc/cli,lfrfid,infrared}/*_cli.c`

> ⚠️ Big-picture note: the CLI was **rewritten** vs. the old `0.x`/single-`cli.c` docs floating around. Consequences you must design for: (1) `ps` no longer exists — it's now `top`; (2) `subghz`, `nfc`, `rfid`, `ir` are **external `.fal` plugins loaded from the SD card**, not built-in; (3) `nfc` opens a **nested sub-shell** with its own prompt; (4) there is **no `power info`** subcommand (battery info is `info power`).

---

## 1. Connection basics

### Transport
- USB **CDC-ACM Virtual COM Port** (VID `0x0483`, PID `0x5740`, interface 0). Enumerates as `/dev/ttyACM0` (Linux), `/dev/cu.usbmodemflip_*` (macOS), `COMx` (Windows).
- **Baud rate is irrelevant.** Data rides USB bulk endpoints; the firmware never reads the line-coding baud. pyserial `baudrate=` is ignored by the device. (Flipper's web/docs suggest `230400` only because some terminals demand *a* number.) Use anything.
- **You must assert DTR.** The shell thread is started by the CDC control-line callback when **DTR goes active** (`cli_vcp.c` → `CliVcpInternalEventConnected` from `CdcCtrlLineDTR`). If your serial library opens the port with DTR de-asserted, **you get no MOTD and no prompt**. In pyserial: `serial.Serial(port, dsrdtr=False)` then set `ser.dtr = True` (most drivers assert DTR on open by default; be explicit).
- After DTR, firmware does `furi_delay_ms(33)` before starting the shell ("minicom isn't ready yet"). Give it ~50–100 ms before expecting the banner.
- Dropping DTR / closing the port breaks the pipe and the shell exits.

### On connect: MOTD then prompt
Immediately after the shell starts it prints an orange ASCII-art banner (`cli_main_motd`) ending with:
```
Welcome to Flipper Zero Command Line Interface!
Read the manual: https://docs.flipper.net/zero/development/cli
Run `help` or `?` to list available commands

Firmware version: <branch> <version> (<githash>[-dirty] built on <date>)
```
…then the first prompt. The banner is wrapped in ANSI color (`\e[38;2;255;130;0m` … `\e[0m`).

### The prompt (exact bytes)
Built by `cli_shell_line_format_prompt`:
```c
snprintf(buf, length-1, "%s>: ", prompt ? prompt : "");
```
and emitted by `cli_shell_line_prompt`:
```c
printf("\r\n%s", buffer);   // -> "\r\n>: "
```
- Main VCP shell sets **no custom prefix**, so the prompt is exactly **`>: `** = bytes `0x3E 0x3A 0x20` (`>`, `:`, space).
- It is **always preceded by `\r\n`**. So the on-wire sentinel that means "ready for input" is **`\r\n>: `**.
- Sub-shells override the prefix (e.g. NFC uses `[` + green + `nfc` + reset + `]`, giving `[nfc]>: ` with embedded ANSI — see §2 `nfc`).

### Line endings
- **Device → host: `\r\n` (CRLF)** everywhere. Every `printf` in the firmware uses `\r\n`.
- **Host → device: submit a command with CR (`\r`, 0x0D).** The line editor maps `CliKeyCR` (0x0D) to "execute". `LF` (0x0A) is **not** a submit key and is silently ignored (it is `< 0x20`, so the "insert printable char" fallback rejects it). Therefore sending `"cmd\r"` **or** `"cmd\r\n"` both work (the trailing `\n` is dropped). Sending only `\n` does nothing.

### Echo & command lifecycle (on-wire byte flow)
The shell runs a full interactive line editor that **echoes every printable byte you send**, and interprets ANSI (arrow keys, Home/End, Ctrl-combos). For a command `help` you will see:

```
host→dev:  h e l p 0x0D
dev→host:  "help"            (echo of the 4 chars as you send them)
dev→host:  "\r\n"            (printed by the CR handler before running)
dev→host:  <command output>
dev→host:  "\r\n>: "         (next prompt)
```
- **Completion detection:** a command is done when you see the next prompt **`\r\n>: `**. That is the canonical "ready" marker. (Because output itself may contain `>: `-like text only rarely, matching on `\r\n>: ` at end-of-stream is robust; better still, gate on it after you've read the echoed command.)
- **Empty line** (just `\r`) → the shell reprints the prompt, nothing else.
- **Unknown command** → red text, no newline of its own (prompt supplies it):
  `\e[31mcould not find command `X`, try `help`\e[0m`
- **Command running in a thread**: default commands run in a spawned thread with the pipe as their stdio; your subsequent bytes are delivered to that command (this is how streaming commands read your Ctrl+C). Some commands (`help`, `?`, `exit`, `storage`) run on the shell thread (`CliCommandFlagUseShellThread`).
- **`this command cannot be run while an application is open`** (red) — printed for non-`ParallelSafe` commands if a GUI app is running on the device.

### ANSI you must tolerate
Output contains SGR color codes and, for some commands, cursor positioning:
- `help` list is green (`\e[32m` … `\e[0m`); errors red (`\e[31m`); MOTD orange.
- `top` uses `\e[1;1H`, `\e[K`, `\e[J` to repaint in place.
- Line editing emits `\e[C`/`\e[D` (cursor), `\e[4h`/`\e[4l` (insert mode), `\e[nG`, bell `0x07`.

A programmatic client should **strip CSI sequences** (`\e[` … final byte in `@`–`~`) from human-facing output, and must send arrow keys etc. as real escape sequences if it emulates a terminal (usually you don't need to).

### Control keys (from `cli_ansi.h`)
`CliKeyETX = 0x03` (Ctrl+C, **the universal abort**), `CliKeyEOT=0x04`, `Backspace=0x08`, `Tab=0x09` (completion), `LF=0x0A`, `FF=0x0C` (Ctrl+L clear screen), `CR=0x0D`, `ETB=0x17` (Ctrl+Backspace), `Esc=0x1B`, `DEL=0x7F`. At the prompt, **Ctrl+C** prints `^C` and redraws a fresh prompt (`\r\n>: `), clearing the current line.

---

## 2. Full command reference

Registration source of truth:
- **Built-in, always present** (main registry): `help`, `?`, `exit`, `reload_ext_cmds`, `!`, `info`, `device_info`, `uptime`, `date`, `log`, `sysctl`, `top`, `free`, `free_blocks`, `echo`, `sleep`, `vibro`, `led`, `gpio`, `i2c`, `storage`, `factory_reset`, `power`, `loader`, `input`, `bt`, `start_rpc_session`, plus extras `buzzer`, `neofetch`, `hello_world`, `subshell_demo`, `js`.
- **External SD plugins** (`CLI_COMMAND_INTERFACE`, loaded from `/ext/apps_data/cli/plugins/cli_<name>.fal`): `subghz`, `nfc`, `rfid`, `ir`. **Only present when the SD card is mounted and the plugin exists.** If missing → `\e[31mfailed to load external command\e[0m`. Run `reload_ext_cmds` after adding files.

Many subcommands are hidden unless **Debug mode** is enabled on-device (Settings → System → Debug).

---

### `help` / `?`
Lists commands, 3 per row, each field `%-30s`, wrapped in green:
```
Available commands:
<green>help                          ?                             !
info                          device_info                   uptime
...<reset>
If you added a new external command and can't see it above, run `reload_ext_cmds`
Find out more: https://docs.flipper.net/zero/development/cli
```
Order is registry/dictionary order (not alphabetical-guaranteed). `?` is a literal alias.

### `exit`
Ends the session; shell stops (no new prompt follows).

### `device_info`, `!`, `info`
`cli_command_info`. When invoked as `device_info` or `!` (context set), always dumps device info with **`_` key separator**; `info` takes a sub-arg:
- `info device` → device info, keys joined by `.`
- `info power` → **battery/charger info** (this is the real "power info")
- `info power_debug` → power debug dump
- bad arg → `info: illegal option -- <arg>\r\nusage: info <device|power|power_debug>`

Each line printed by callback as `"%-30s: %s\r\n"`. `device_info`/`!` use `_` (machine-readable, e.g. `hardware_model`, `firmware_version`, `radio_fw_...`); `info device` uses `.` (e.g. `hardware.model`). Example lines:
```
hardware_model                : Flipper Zero
firmware_version              : 1.4.3
...
```

### `uptime`
`printf("Uptime: %luh%lum%lus", ...)` — **no trailing newline**. E.g. `Uptime: 0h13m37s`.

### `date`
- No arg → current RTC, format `"%.4d-%.2d-%.2d %.2d:%.2d:%.2d %d"` → e.g. `2026-07-19 14:22:05 6` (last field = weekday 1–7). No trailing newline.
- With arg → set clock; input format `%Y-%m-%d %H:%M:%S %u` (7 fields). Success → `New datetime is: <same format>`. Bad → `Invalid datetime format, use ...` / `Invalid datetime data`.

### `log`
Streaming. Prints:
```
Current log level: <level>
Use <log ?> to list available log levels
Press CTRL+C to stop...
```
then streams live FURI logs until **0x03**. Optional arg sets level for the session: `error|warn|info|default|debug|trace` (invalid/`?` prints the level help and returns without streaming).

### `top`  (replaces the old `ps`)
Streaming thread/heap table, repainted with ANSI cursor control. Arg = refresh interval (duration, default `1000` ms); **interval `0` = single snapshot** (no streaming). Otherwise **Ctrl+C to stop**. Header + per-thread columns: `AppID Name State Prio "Stack start" Stack "Stack Min" Heap %CPU`, plus a `Threads/ISR Time/Uptime` line and a `Heap: total/free/minimum/max block` line.
> There is **no `ps` command** in 1.x — use `top 0` for a one-shot process list.

### `free`
```
Free heap size: <n>
Total heap size: <n>
Minimum heap size: <n>
Maximum heap block: <n>
Pool free: <n>
Maximum pool block: <n>
```

### `free_blocks`
Debug dump of the heap free-block map.

### `vibro`
`vibro 1` (on) / `vibro 0` (off). Bad arg → `vibro: illegal option -- <arg>\r\nusage: vibro <1|0>`. Caveats printed if device is in stealth mode or vibro disabled in settings. No output on success.

### `led`
`led <r|g|b|bl> <0-255>` — `r/g/b` = RGB notification LED channels, `bl` = display backlight. No success output. Bad → `led: illegal option -- ...\r\nusage: led <r|g|b|bl> <0-255>`.

### `input`  (buttons)
Subcommands (no `list`; it's `dump`):
- `input dump` → streams events, `key: <name> type: <name>` per line, `Press CTRL+C to stop` (0x03 to end).
- `input send <key> <type>` → inject one event. `<key>` ∈ `up down left right back ok`; `<type>` ∈ `press release short long`. Bad args print the send-usage block. No success output.
- bare/other → usage: `input <cmd> <args>` with `dump` / `send <key> <type>`.

### `gpio`
`cli_command_gpio`. Usage:
```
gpio mode <pin_name> <0|1>   (0 = input, 1 = output)
gpio set  <pin_name> <0|1>
gpio read <pin_name>
```
Outputs (no trailing newline):
- `mode` output → `Pin <name> is now an output (low)`; input → `Pin <name> is now an input`
- `set` → `Pin <name> => <0|1>`; if not an output → `Err: pin <name> is not set as an output.`
- `read` → `Pin <name> <= <0|1>`; if not an input → `Err: pin <name> is not set as an input.`
- Unknown pin → `Wrong pin name. Available pins: <space-separated list>` (send a bogus name to enumerate the exact names for the connected hardware). Standard external names: `PA7 PA6 PA4 PB3 PB2 PC3 PC1 PC0` (more appear in Debug mode).
- **Debug pins prompt**: `Changing this pin mode may damage hardware. Are you sure you want to continue? (y/n)?` then a single `getchar()`; non-`y/Y` → `Cancelled.` (blocking!).

### `i2c`
Scans external I²C (PC0=SCL/PC1=SDA, 100 kHz, 7-bit) and prints an address grid:
```
Scanning external i2c on PC0(SCL)/PC1(SDA)
Clock: 100khz, 7bit address

  | 0 1 2 3 4 5 6 7 8 9 A B C D E F
--+--------------------------------
0 | - - - # - ...
...
```
`#` = ACK, `-` = no device.

### `echo`
Echoes received bytes back until it sees `0x03`. (Useful for round-trip/latency tests.)

### `sleep`
`sleep [<n>[ms|s|m|h]]` (default unit s). Interruptible by 0x03.

### `sysctl`
`sysctl debug <0|1>` (enable/disable Debug flag → `Debug enabled.`/`Debug disabled.`), `sysctl heap_track <none|main[|tree|all]>`. **Not ParallelSafe.**

### `power`
`power_cli`. Usage block:
```
power off        - shutdown power
power reboot     - reboot
power reboot2dfu - reboot to dfu bootloader
power 5v <0|1>   - enable/disable 5V on pin 1
power 3v3 <0|1>  - (Debug only) enable/disable ext 3v3
```
- `power off` → prints `It's now safe to disconnect USB from your flipper`, waits 666 ms, powers off.
- `power reboot` → reboots to normal firmware (no output; USB drops).
- `power reboot2dfu` → reboots into **DFU bootloader** (no output; re-enumerates as STM32 DFU).
- **There is no `power info`.** `power info` falls through to the usage block. Battery info = **`info power`**.

### `loader`
```
loader list                 - list apps  ->  "Apps:\r\n\t<name>\r\n..." then "Settings:\r\n\t<name>..."
loader open "<App Name>"     - start app  ->  on error prints the error string; on success no text (backlight blink)
loader info                  - "Application \"<name>\" is running" | "No application is running"
loader close                 - "Application \"<name>\" was closed" | "...has to be closed manually" | "No application is running"
loader signal <dec> [hex]    - "Signal <n> with argument 0x<p> was handled|ignored" | "No application is running" | "Signal must be a decimal number"
```

### `bt`
`bt hci_info` → dumps HCI/BLE state. Debug + test-capable only: `bt tx_carrier <ch 0-39> <power 0-6>`, `bt rx_carrier <ch>`, `bt tx_packet <ch> <pattern 0-5> <datarate 1-2>`, `bt rx_packet <ch> <datarate>`. The `*_carrier`/`*_packet` commands stream until **0x03** (rx variants print live `RSSI: ...\r`). **Not ParallelSafe.** Re-enables advertising on exit.

### `subghz` (external plugin; **not ParallelSafe**)
`subghz <cmd> <args>`:
- `subghz rx <freq_Hz> <device:0=int,1=ext>` — decodes known protocols; prints `Listening at frequency: <f> device: <d>. Press CTRL+C to stop`, then each decoded packet's info; on exit `\r\nPackets received <n>`. **Streams forever → 0x03 to stop.**
- `subghz rx_raw <freq_Hz>` — raw `+<dur> -<dur> …` timing stream, 0x03 to stop.
- `subghz tx <3-byte key hex> <freq_Hz> <te_us> <repeat> <device>` — transmits a Princeton key; prints `Transmitting at ...`, `.` progress; 0x03 aborts.
- `subghz tx_from_file <path.sub> <repeat> <device>` — TX a `.sub` file; validates header/freq/preset/protocol (many `Error ...` messages), prints `Listening at <path>. Frequency=..., Protocol=...`, `.` progress; 0x03 aborts.
- `subghz decode_raw <path.sub>` — decode a RAW capture file; `Listening at <file>.` … `Packets received <n>`; 0x03 to stop.
- `subghz chat <freq_Hz> <device>` — interactive Sub-GHz chat; `Press CTRL+C to stop`; your keystrokes are TX'd on CR; 0x03 exits → `Exit chat`.
- Debug only: `tx_carrier <freq>`, `rx_carrier <freq>` (live `RSSI:`), `encrypt_keeloq`, `encrypt_raw`.
- Valid freq ranges (from error text): `299999755…348000000 or 386999938…464000000 or 778999847…928000000`.

### `nfc` (external plugin) — **nested sub-shell**
`nfc` does **not** run one command and return. It **spawns a second CLI shell** with its own registry, its own MOTD ("Welcome to NFC Command Line Interface!"), and a **custom prompt `[nfc]>: `** (the `nfc` is green: bytes `[`,`\e[32m`,`nfc`,`\e[0m`,`]`,`>: `). Inside it you run NFC subcommands and `help`/`?`; type **`exit`** to leave and return to the main `>: ` prompt. It refuses to start if the on-device NFC app is open: `NFC app is running, unable to run NFC CLI at the same time!`. Design your client to detect the `[nfc]>: ` prompt and switch modes.

### `rfid` (lfrfid, external; **not ParallelSafe**)
```
rfid read [normal|indala | ask|psk]        - streams until Ctrl+C; on read prints "<Proto> <HEXDATA>\r\n" + rendered info, then "Reading stopped"
rfid <write|emulate> <key_type> <key_data> - write/emulate; Ctrl+C to abort; "Written!" / "Emulation stopped" etc.
rfid raw_read <ask|psk> <filename>         - capture raw to file; Ctrl+C
rfid raw_emulate <filename>                - emulate raw; Ctrl+C
rfid raw_analyze <filename>                - dump + decode raw
```
Unknown protocol prints the full protocol list with byte sizes.

### `ir` (infrared, external; **not ParallelSafe**)
```
ir rx [raw]                                   - receive; decoded lines "<Proto>, A:0x.., C:0x..[ R]" or "RAW, N samples:" + timings; Ctrl+C to stop
ir tx <protocol> <address_hex> <command_hex>  - send one message
ir tx RAW F:<freq> DC:<duty> <s0> <s1> ...    - send raw (max 512 samples)
ir decode <input_file> [<output_file>]
ir universal <remote_name> <signal_name>      - brute-force; "\r<pct>% complete."; Ctrl+C
ir universal list <remote_name>
```
Usage prints the live list of available protocols and universal remotes.

### `start_rpc_session`
Switches the channel from text CLI into **binary Protobuf RPC mode** (`rpc_cli_command_start_session`, ParallelSafe). It calls `furi_hal_usb_lock()` and hands the pipe to the RPC session. After you send `start_rpc_session\r`:
- The command echoes + `\r\n` as usual, then **no text prompt is printed** — every subsequent byte is length-delimited `PB_Main` protobuf (varint length prefix, nanopb `PB_ENCODE_DELIMITED`). Responses come back the same way.
- On start error: `Session start error`.
- End the session by sending a `stopSession` RPC command or breaking the pipe (drop DTR / close port). Only then does the text CLI resume. Design note: once you issue this, **stop parsing for `>: `** and switch your reader to protobuf framing.

### Extras
`buzzer <freq>` (tone, Ctrl+C), `neofetch` (art + system summary), `hello_world`, `subshell_demo` (demo of the sub-shell mechanism), `js <script.js>`, `factory_reset` (prompts `All data will be lost! Are you sure (y/n)?` → `y` → `Data will be wiped after reboot.` and reboots; else `Safe choice.`).

---

## 3. Binary-safe file transfer over the CLI

All four commands live in `storage_cli.c`. Paths must start with `/int`, `/ext`, or `/any`.

### `storage read <path>` — dump whole file
Firmware:
```c
printf("Size: %lu\r\n", (uint32_t)file_size);
do { read 128B; for each byte printf("%c", b); } while(read>0);
printf("\r\n");
```
Byte flow:
```
host→dev: storage read /ext/foo.bin\r
dev→host: "Size: <N>\r\n"          // N = decimal uint32 file size
dev→host: <exactly N raw bytes>     // raw, NUL-safe (printf("%c") of each byte)
dev→host: "\r\n"
dev→host: "\r\n>: "                 // prompt = done
```
Reading is binary-safe **if you parse `Size: N`, then read exactly N bytes**, then consume the trailing `\r\n`. There is no per-chunk flow control — the whole file is pushed as fast as the pipe drains. Use `read_chunks` for large files / flow control.

### `storage read_chunks <path> <chunk_size>` — flow-controlled read
`chunk_size` is decimal (documented range 1–512; larger works but see buffer note). Firmware:
```c
if(parse(chunk_size) fails) print_usage;
printf("Size: %llu\r\n", file_size);          // uint64 decimal
while(file_size > 0) {
    printf("\r\nReady?\r\n");
    getchar();                                // waits for ANY one byte from host
    read up to chunk_size bytes; putchar each; // raw
    file_size -= read_size;
}
printf("\r\n");
```
Byte flow (handshake **per chunk**):
```
host→dev: storage read_chunks /ext/foo.bin 512\r
dev→host: "Size: <N>\r\n"
repeat until N bytes consumed:
    dev→host: "\r\nReady?\r\n"
    host→dev: <1 byte>            // any byte; it's the "send next chunk" trigger
    dev→host: <min(chunk_size, remaining) raw bytes>
dev→host: "\r\n"
dev→host: "\r\n>: "
```
Notes: the `getchar()` **consumes exactly one host byte** before each chunk — send one (e.g. `\n` or space) each time you see `Ready?`. The last chunk is the remainder (`< chunk_size`). Fully binary-safe. If `chunk_size == 0`, it prints `Size:` then just `\r\n` (no data loop).

### `storage write <path>` — interactive text append (Ctrl+C terminated)
Opens in **append** mode. Firmware:
```c
printf("Just write your text data. New line by Ctrl+Enter, exit by Ctrl+C.\r\n");
buffer_size = 512;
while(true) {
    symbol = getchar();
    if(symbol == 0x03 /*ETX*/) {
        write_size = read_index % 512;
        if(write_size > 0) { flush partial; break; }   // <-- only breaks if something is buffered
    }
    buffer[read_index % 512] = symbol;      // otherwise ETX is stored as DATA
    printf("%c", symbol); fflush(stdout);   // every byte echoed
    read_index++;
    if(read_index % 512 == 0) flush full 512;
}
printf("\r\n");
```
Byte flow:
```
host→dev: storage write /ext/note.txt\r
dev→host: "Just write your text data. New line by Ctrl+Enter, exit by Ctrl+C.\r\n"
host→dev: <your bytes...>        // each is echoed back
host→dev: 0x03                   // Ctrl+C to finish
dev→host: "\r\n"
dev→host: "\r\n>: "
```
**Gotchas (important, this is a real edge behavior):**
- Every input byte is **echoed**. Data is flushed to the file every 512 bytes.
- The `0x03` terminator is only honored when there are **unflushed buffered bytes** (`read_index % 512 > 0`). Consequences:
  - Sending `0x03` as the **very first byte** (`read_index==0`) does **not** exit — it gets written to the file as a literal `0x03` byte.
  - If you've sent an **exact multiple of 512 bytes**, the next `0x03` is also written as data, not treated as exit; you'd need to send ≥1 more byte and then `0x03`.
- Because `0x03` is the terminator, you **cannot store a `0x03` byte reliably** — so this command is for **text**, not arbitrary binary. **For binary, use `write_chunk`.**

### `storage write_chunk <path> <size>` — binary append (the correct binary uploader)
`size` = decimal byte count. Opens in **append** mode. Firmware:
```c
if(parse(size) fails) print_usage;
printf("Ready\r\n");
buffer_size = 1024;
while(need_to_read) {
    to_read = MIN(1024, need_to_read);
    got = pipe_receive(pipe, buffer, to_read);   // raw pipe read, NO echo, NO getchar
    if(got != to_read) break;                    // pipe closed early -> abort
    wrote = storage_file_write(file, buffer, got);
    if(wrote != got) { print "Storage error: ..."; break; }
    need_to_read -= got;
}
```
Byte flow:
```
host→dev: storage write_chunk /ext/foo.bin 4096\r
dev→host: "Ready\r\n"
host→dev: <exactly 4096 raw bytes>     // no echo, fully binary-safe, incl. 0x03/0x00
dev→host: (nothing on success)
dev→host: "\r\n>: "                    // prompt returns == upload complete
```
Notes:
- **No echo**, **no per-chunk handshake** — after `Ready\r\n`, stream exactly `size` bytes. The device reads them in ≤1024-byte gulps internally; you don't need to chunk your writes to match.
- Completion signal = the prompt `\r\n>: ` reappears (no success text). On write failure: `Storage error: <desc>` then prompt.
- Append semantics → for a **large file**, loop: create/truncate once (e.g. `storage remove` then) and call `write_chunk` repeatedly with successive slices; each call appends. Keep each `size` moderate (a few KiB) so a stalled transfer is easy to recover.
- The `size` you pass is authoritative; if you send fewer bytes the command **blocks** waiting for the rest (until pipe breaks). Always send exactly `size` bytes.

### Other `storage` subcommands (exact outputs)
- `storage info /int` → `Label: <name>\r\nType: Virtual\r\n<K>KiB total\r\n<K>KiB free\r\n`; `storage info /ext` → SD label/type/size + `<mfr><oem> <product> v<maj>.<min>\r\nSN:<serial> <mm>/<yy>\r\n`.
- `storage list <path>` → for `/`: three lines `\t[D] int`, `\t[D] ext`, `\t[D] any`. Else per entry `\t[D] <name>` or `\t[F] <name> <size>b`; empty dir → `\tEmpty`. (Error → `Storage error: <desc>`.)
- `storage tree <path>` → recursive form of `list` (for `/` walks `/int` then `/ext`).
- `storage stat <path>` → `Storage` (for `/`), `Storage, <K>KiB total, <K>KiB free` (for a root), `Directory`, or `File, size: <n>b`.
- `storage md5 <path>` → `<32-hex md5>\r\n` or error.
- `storage timestamp <path>` → `Timestamp <n>\r\n` or `Invalid arguments\r\n`.
- `storage remove <path>` → silent on success; error → `Storage error: <desc>`.
- `storage mkdir <path>` → silent on success; error otherwise.
- `storage copy <src> <dst>` / `storage rename <src> <dst>` → `<dst>` parsed as a (optionally quoted) string; silent on success.
- `storage extract <archive> <dest>` → tar unpack, prints `\tD/F <name>` per entry then `Decompression success|failed in <n> ticks`.
- `storage format /ext` → prompts `Formatting SD card, All data will be lost! Are you sure (y/n)?` → one `getchar()` → `y/Y`: `Formatting, please wait...` then `SD card was successfully formatted.`/error; else `Cancelled.` `storage format /int` → `Storage error: not implemented`.
- Bad/empty subcommand → the usage block: `Usage:\r\nstorage <cmd> <path> <args>\r\nThe path must start with /int or /ext\r\nCmd list:` + one line per command.

---

## 4. Gotchas / control-flow you must handle

**The abort byte is `0x03` (ETX / Ctrl+C).** Nearly every long-running command polls `cli_is_pipe_broken_or_is_etx_next_char(pipe)`, which consumes ≤1 pipe byte and returns true if it's `0x03` (or the pipe broke). Send a single `\x03` to stop.

**Commands that stream forever (send `0x03` to stop):**
- `log`, `top` (unless arg `0`), `sleep`, `echo`
- `input dump`
- `subghz rx`, `subghz rx_raw`, `subghz tx`, `subghz tx_from_file`, `subghz decode_raw`, `subghz chat`, `subghz tx_carrier`, `subghz rx_carrier`
- `ir rx`, `ir universal` (brute force)
- `rfid read`, `rfid write`, `rfid emulate`, `rfid raw_read`, `rfid raw_emulate`
- `bt tx_carrier`, `bt rx_carrier`, `bt tx_packet`, `bt rx_packet`

**Commands that block on a single `getchar()` (send the expected byte or they hang):**
- `storage format` and `factory_reset` — expect `y`/`Y` (anything else cancels).
- `gpio mode`/`gpio set` on a **debug pin** — expect `y`/`Y` confirmation.
- `storage read_chunks` — expects **one byte per chunk** after each `\r\nReady?\r\n`.
- `storage write` — reads bytes until `0x03` (with the boundary caveat in §3).
- `storage write_chunk` — reads exactly `size` bytes (blocks until it has them all).

**Prompt-return = completion.** For request/response commands, treat the reappearance of `\r\n>: ` as "done". Don't confuse it with data; parse the echoed command line first, then read output until the prompt.

**`0x03` at the idle prompt** cancels the current input line (prints `^C` + fresh prompt) — harmless; use it to reset your line state after errors.

**Sub-shell (`nfc`)** takes over the session with prompt `[nfc]>: ` and its own command set. It won't return to `>: ` until you send `exit`. Detect the changed prompt.

**`start_rpc_session`** turns the stream binary and **locks USB**; there is no more `>: `. Switch your reader to protobuf framing; end via RPC stop or by dropping the port.

**External-plugin availability.** `subghz`/`nfc`/`rfid`/`ir` are `.fal` files under `/ext/apps_data/cli/plugins/`. No SD card (or plugin missing) → they don't appear in `help` and invoking one yields `failed to load external command`. On SD mount/unmount the shell auto-reloads/removes them; `reload_ext_cmds` forces a rescan.

**Debug-gated subcommands.** Many entries (`power 3v3`, `sysctl heap_track tree/all`, all `bt` test cmds, `subghz *_carrier`/`encrypt_*`, extra `gpio` pins) only exist when on-device **Debug** is enabled. Enable via `sysctl debug 1`.

**ParallelSafe vs. app-open.** If a GUI app is running on the Flipper, non-ParallelSafe commands (`subghz`, `ir`, `rfid`, `bt`, `vibro`, `led`, `gpio`, `i2c`, `sysctl`, `buzzer`, …) refuse with `this command cannot be run while an application is open`. ParallelSafe ones (`storage`, `power`, `loader`, `info`/`device_info`, `uptime`, `date`, `log`, `top`, `free`, `input`, `start_rpc_session`) run anyway.

**Design tips for a robust Python driver:**
1. Open with DTR asserted; wait ~100 ms; drain the MOTD up to the first `\r\n>: `.
2. To run a command: write `cmd + "\r"`, then read until you see `\r\n>: ` (or a known sub-prompt). Optionally discard the echoed `cmd` line.
3. Strip ANSI CSI (`\x1b\[[0-9;]*[ -/]*[@-~]`) from human-readable output.
4. For binary **download**: prefer `read_chunks` (Size + per-chunk `Ready?` handshake, read exact byte counts).
5. For binary **upload**: use `write_chunk PATH N`, wait for `Ready\r\n`, send exactly N raw bytes, wait for `\r\n>: `. Never use `storage write` for binary.
6. Universal stop: send `\x03` and then re-sync on the next `\r\n>: `.

**Sources:** [Flipper CLI docs](https://docs.flipper.net/zero/development/cli); firmware `dev` branch — [cli_shell.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/lib/toolbox/cli/shell/cli_shell.c), [cli_shell_line.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/lib/toolbox/cli/shell/cli_shell_line.c), [cli_ansi.h](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/lib/toolbox/cli/cli_ansi.h), [cli_vcp.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/cli/cli_vcp.c), [cli_main_commands.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/cli/cli_main_commands.c), [storage_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/storage/storage_cli.c), [power_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/power/power_cli.c), [loader_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/loader/loader_cli.c), [input_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/input/input_cli.c), [bt_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/bt/bt_cli.c), [rpc.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/rpc/rpc.c)/[rpc_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/rpc/rpc_cli.c), [subghz_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/main/subghz/subghz_cli.c), [nfc_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/main/nfc/cli/nfc_cli.c), [lfrfid_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/main/lfrfid/lfrfid_cli.c), [infrared_cli.c](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/main/infrared/infrared_cli.c).