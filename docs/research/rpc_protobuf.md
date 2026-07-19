I have everything I need — confirmed against the actual `.proto` files, the firmware `rpc.c`/`rpc_gui.c` source, the reference Python client, and PyPI. Here is the exhaustive report.

---

# Flipper Zero Protobuf RPC — Complete Implementation Reference

Everything below is verified against the current firmware source (`flipperdevices/flipperzero-firmware`, `dev` branch), the protobuf schema repo (`flipperdevices/flipperzero-protobuf`, `dev` branch), and the reference Python client (`flipperdevices/flipperzero_protobuf_py`).

> **Branch note:** The protobuf repo's default branch is **`dev`**, not `main`/`master`. The raw URLs below use `/dev/` and are the current ones. `.../main/...` and `.../master/...` will 404 for this repo.

---

## 1. Entering RPC mode

The Flipper exposes a serial CLI at **115200 baud, 8N1** on its USB CDC ACM port (`/dev/ttyACM0`, `/dev/cu.usbmodemflip_*`, or `COMx`). On connect it prints a banner and the prompt `>: `.

RPC is entered with the CLI command **`start_rpc_session`**. It is registered in firmware in `applications/services/rpc/rpc.c`:

```c
cli_registry_add_command(
    registry, "start_rpc_session", CliCommandFlagParallelSafe,
    rpc_cli_command_start_session, rpc);
```

**Exact entry handshake** (from the reference client `flipper_base.py`):

```python
def start_rpc_session(self):
    self._serial.read_until(b">: ")          # drain banner + prompt
    self._serial.write(b"start_rpc_session\r")  # NOTE: bare \r, NOT \r\n
    self._serial.read_until(b"\n")           # consume the command echo line
    self._in_session = True
```

**What happens to the stream afterward:**
- The CLI hands the serial byte-stream over to the RPC session worker. From that moment the stream is **raw length-delimited protobuf** — there is **no more `>: ` text prompt, no line echo, no ANSI, no text at all**. Every byte is protobuf framing.
- The only way back to the text CLI is to end the RPC session: send a `Main{ stop_session }` (see §4), after which the firmware returns an `Empty/OK` and the transport reverts to text CLI. Physically disconnecting/reconnecting also resets it.
- Gotcha: write `start_rpc_session\r` (carriage return only). Sending `\r\n` can leave a stray `\n` that the CLI treats as an empty command; the reference client deliberately uses `\r`.
- Over BLE (the Serial GATT service) there is no text prompt at all — the RPC session is implicitly active on the RX/TX characteristics. Everything below about framing/messages is identical; only the CLI handshake is USB/UART-specific.

---

## 2. The `flipperzero-protobuf` repo, files, URLs, and `Main`

Schema is **proto3**. Top-level file is `flipper.proto` (package `PB`); each subsystem is its own file with its own package (`PB_Storage`, `PB_System`, `PB_App`, `PB_Gui`, `PB_Gpio`, `PB_Property`, `PB_Desktop`). The `*.options` files are **nanopb** field-size hints used only by the firmware C build — **you do not need them for Python**; ignore them.

### Raw download URLs (current, `dev` branch)

```
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/flipper.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/storage.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/system.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/application.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/gui.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/gpio.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/property.proto
https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/desktop.proto
```

One-liner to grab them all:

```bash
for f in flipper storage system application gui gpio property desktop; do
  curl -sO "https://raw.githubusercontent.com/flipperdevices/flipperzero-protobuf/dev/$f.proto"
done
```

Full file inventory in the repo: `flipper.proto`, `storage.proto`, `system.proto`, `application.proto`, `gui.proto`, `gpio.proto`, `property.proto`, `desktop.proto`, plus the matching `.options` files, `Changelog`, and `.gitignore`. **There is no `region.proto` and no README** in the repo. "Region" is not a separate file or an RPC command — it is a plain message defined at the bottom of `flipper.proto` (used by the SubGHz region-provisioning tooling), never referenced in the `Main` oneof:

```protobuf
message Region {
    message Band { uint32 start = 1; uint32 end = 2; int32 power_limit = 3; uint32 duty_cycle = 4; }
    bytes country_code = 1;
    repeated Band bands = 2;
}
```

### Package name

`package PB;` (top level). Java option `com.flipperdevices.protobuf`. Sub-files use `PB_Storage`, `PB_System`, `PB_App`, `PB_Gui`, `PB_Gpio`, `PB_Property`, `PB_Desktop`. In Python after compilation the envelope is `flipper_pb2.Main`, and content messages are `storage_pb2.ListRequest`, `system_pb2.PingRequest`, etc.

### The `Main` envelope (verbatim structure)

Every message on the wire — request or response, in both directions — is a `PB.Main`:

```protobuf
message Main {
    uint32 command_id = 1;          // client-chosen correlation id, echoed by device
    CommandStatus command_status = 2; // OK=0 or an error code (see enum below)
    bool has_next = 3;              // true => more Main messages belong to this command_id
    oneof content {                 // exactly one payload; tag number identifies the command
        Empty empty = 4;
        StopSession stop_session = 19;
        .PB_System.PingRequest        system_ping_request = 5;
        .PB_System.PingResponse       system_ping_response = 6;
        .PB_System.RebootRequest      system_reboot_request = 31;
        .PB_System.DeviceInfoRequest  system_device_info_request = 32;
        .PB_System.DeviceInfoResponse system_device_info_response = 33;
        // ... factory_reset, get/set_datetime, protobuf_version, update, power_info ...
        .PB_Storage.ListRequest       storage_list_request = 7;
        .PB_Storage.ListResponse      storage_list_response = 8;
        .PB_Storage.ReadRequest       storage_read_request = 9;
        .PB_Storage.ReadResponse      storage_read_response = 10;
        .PB_Storage.WriteRequest      storage_write_request = 11;
        .PB_Storage.DeleteRequest     storage_delete_request = 12;
        .PB_Storage.MkdirRequest      storage_mkdir_request = 13;
        .PB_Storage.Md5sumRequest     storage_md5sum_request = 14;
        .PB_Storage.Md5sumResponse    storage_md5sum_response = 15;
        .PB_Storage.StatRequest       storage_stat_request = 24;
        .PB_Storage.StatResponse      storage_stat_response = 25;
        // ... info, timestamp, rename, backup_create/restore, tar_extract ...
        .PB_App.StartRequest          app_start_request = 16;
        .PB_App.LockStatusRequest     app_lock_status_request = 17;
        .PB_App.LockStatusResponse    app_lock_status_response = 18;
        .PB_App.AppExitRequest        app_exit_request = 47;
        .PB_App.AppLoadFileRequest    app_load_file_request = 48;
        .PB_App.AppButtonPressRequest app_button_press_request = 49;
        .PB_App.AppButtonReleaseRequest app_button_release_request = 50;
        // ... app_state_response, get_error, data_exchange ...
        .PB_Gui.StartScreenStreamRequest gui_start_screen_stream_request = 20;
        .PB_Gui.StopScreenStreamRequest  gui_stop_screen_stream_request = 21;
        .PB_Gui.ScreenFrame              gui_screen_frame = 22;
        .PB_Gui.SendInputEventRequest    gui_send_input_event_request = 23;
        // ... virtual display, gpio, property, desktop ...
    }
}
```

`CommandStatus` (from `flipper.proto`) — the important ones:

| Value | Name | Meaning |
|---|---|---|
| 0 | `OK` | success |
| 1 | `ERROR` | generic |
| 2 | `ERROR_DECODE` | frame could not be decoded — **session is torn down** (see §3) |
| 3 | `ERROR_NOT_IMPLEMENTED` | command decoded but unsupported |
| 4 | `ERROR_BUSY` | global lock held |
| 14 | `ERROR_CONTINUOUS_COMMAND_INTERRUPTED` | expected `has_next` chunk never arrived |
| 15 | `ERROR_INVALID_PARAMETERS` | |
| 5–13,18 | `ERROR_STORAGE_*` | FS errors (`NOT_READY`, `EXIST`, `NOT_EXIST`, `DENIED`, `INVALID_NAME`, `DIR_NOT_EMPTY`, …) |
| 16,17,21,22 | `ERROR_APP_*` | `CANT_START`, `SYSTEM_LOCKED`, `NOT_RUNNING`, `CMD_ERROR` |
| 19,20 | `ERROR_VIRTUAL_DISPLAY_*` | |
| 58,59 | `ERROR_GPIO_*` | |

`Empty` and `StopSession` are empty marker messages. `Empty` exists because a proto3 `oneof` must always carry exactly one member, so "no body" responses (write ack, mkdir ack, etc.) use `empty`.

---

## 3. Wire framing (length-delimited varint)

The firmware uses **nanopb's `PB_ENCODE_DELIMITED` / `PB_DECODE_DELIMITED`**, which is byte-for-byte identical to Java protobuf's `writeDelimitedTo()` / `parseDelimitedFrom()` and Python's `_VarintBytes(msg.ByteSize()) + msg.SerializeToString()`.

From firmware `rpc.c`:

```c
// send:
pb_encode_ex(&ostream, &PB_Main_msg, message, PB_ENCODE_DELIMITED);
// receive:
pb_decode_ex(&istream, &PB_Main_msg, session->decoded_message, PB_DECODE_DELIMITED);
```

### Exact frame layout

```
┌────────────────────────┬─────────────────────────────────┐
│ varint(length)         │ serialized PB.Main  (length bytes) │
│ base-128, LSB-first,   │                                   │
│ high bit = "more"      │                                   │
└────────────────────────┴─────────────────────────────────┘
```

- The length prefix is a standard protobuf **base-128 varint**: 7 data bits per byte, low byte first, continuation bit (0x80) set on every byte except the last. In practice a `Main` is well under 16 KB so the prefix is 1–2 bytes, but you must implement a full varint reader.
- **There are no magic bytes, no CRC, no message-type byte outside the protobuf.** The only demux keys are inside the decoded `Main`: `command_id`, `command_status`, `has_next`, and the `which_content` oneof tag.

### Reading and writing (verified against `flipper_base.py`)

```python
# read one Main from the serial stream
def read_varint32(read1):            # read1() -> one byte
    result = shift = 0
    while True:
        b = read1()[0]
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result & 0xFFFFFFFF
        shift += 7

length = read_varint32(lambda: ser.read(1))
main   = flipper_pb2.Main()
main.ParseFromString(ser.read(length))

# write one Main
from google.protobuf.internal.encoder import _VarintBytes
payload = main.SerializeToString()
ser.write(_VarintBytes(len(payload)) + payload)
```

### `command_id` correlation

- The **client** picks `command_id` (typically a monotonically increasing counter, non-zero). The **device echoes the same `command_id`** in every `Main` it emits in response. This is how you pair replies with requests and how you can pipeline multiple in-flight commands.
- **`command_id == 0` = unsolicited/async traffic from the device**, not tied to a request: screen-stream frames (`gui_screen_frame`) and virtual-display input echoes both go out with `command_id = 0`. A decode-error notification is also sent with `command_id = 0`. Your read loop must handle id 0 separately from your request/response matching.

### `has_next` — multi-part responses

`has_next` chains several `Main` messages under one `command_id`:

- **Single-shot commands** (ping, stat, mkdir, delete, md5, write-ack): one reply `Main` with `has_next = false`.
- **Streamed/chunked responses**: the device sends N messages sharing the `command_id`, each with `has_next = true`, and the **final message carries `has_next = false`**. The client rule is simply: *keep reading messages for this `command_id`, accumulating the payload, until you receive one with `has_next == false` (that last one is inclusive — it still carries data unless it's `empty`).*
  - **`DeviceInfoResponse` / `PowerInfoResponse`**: one key/value pair per message; every pair except the last has `has_next = true`; the last real pair has `has_next = false`. (There is no trailing empty terminator for these — the last data message is the terminator.)
  - **`StorageListResponse`**: directory entries delivered in batches (each `ListResponse` has a `repeated File`); intermediate batches `has_next = true`, final batch `has_next = false` (final batch may have an empty `file` list).
  - **`StorageReadResponse`**: file delivered as chunks of `File.data`; each chunk `has_next = true` except the last (`has_next = false`).
- **Chunked uploads (client → device)**: for `StorageWriteRequest` the *client* sets `has_next` — send multiple `Main{ storage_write_request }` all sharing one `command_id`, `has_next = true` on every chunk except the final, `has_next = false` on the last. The device stays silent until it sees `has_next = false`, then replies once with `Main{ empty, OK }`. If the device stops receiving the expected continuation it returns `ERROR_CONTINUOUS_COMMAND_INTERRUPTED (14)`.
- **"Empty/last message signals completion":** the completion signal is **`has_next == false`**, *not* an empty payload. Some flows happen to end on an `empty` body (acks), but the authoritative end-of-stream flag is `has_next`. Do not rely on an empty `oneof` to detect completion.

### Decode-error behavior (important for robustness)

Because protobuf itself has no frame delimiters, a single desync is unrecoverable. If the firmware fails to decode a frame it: resets its RX buffer, sends `Main{ command_id=0, command_status=ERROR_DECODE }`, then **closes the whole session** (and on BLE, drops the link). So if you ever see `ERROR_DECODE`, assume the session is dead and re-open it. Keep your varint/length handling exact.

---

## 4. Key RPC commands (request / response messages)

Field numbers below are the proto field tags inside each sub-message. Content-oneof tag numbers (in `Main`) are in parentheses.

### Session / System (`system.proto`, package `PB_System`)

| Command | Request (→) | Response (←) | Notes |
|---|---|---|---|
| **Stop session** | `Main.stop_session` (19) | `Main.empty`, OK | Ends RPC, returns to text CLI. |
| **Ping** | `PingRequest{ bytes data=1 }` (5) | `PingResponse{ bytes data=1 }` (6) | Echo; device returns identical `data`. Round-trip liveness check. |
| **Device info** | `DeviceInfoRequest{}` (32) | `DeviceInfoResponse{ string key=1; string value=2 }` (33), **streamed** | One key/value per message, `has_next=true` until last (hardware version, firmware, target, radio stack, uptime, etc.). |
| **Reboot** | `RebootRequest{ RebootMode mode=1 }` (31) | *(none — device reboots)* | `RebootMode`: `OS=0`, `DFU=1`, `UPDATE=2`. |
| Power info | `PowerInfoRequest{}` (44) | `PowerInfoResponse{key,value}` (45), streamed | Battery/charge telemetry, same key/value streaming pattern. |
| Get/Set datetime | `GetDateTimeRequest{}` (35) / `SetDateTimeRequest{DateTime}` (37) | `GetDateTimeResponse{DateTime}` (36) / `empty` | `DateTime{hour,minute,second,day,month,year,weekday}`. |
| Protobuf version | `ProtobufVersionRequest{}` (39) | `ProtobufVersionResponse{major,minor}` (40) | Negotiate schema compatibility. |
| Factory reset | `FactoryResetRequest{}` (34) | *(device wipes)* | |
| Play alert | `PlayAudiovisualAlertRequest{}` (38) | `empty` | "find my flipper" beep/vibrate. |

### Storage (`storage.proto`, package `PB_Storage`)

Shared type:
```protobuf
message File { enum FileType { FILE=0; DIR=1; } FileType type=1; string name=2; uint32 size=3; bytes data=4; string md5sum=5; }
```

| Command | Request (→) | Response (←) | Notes |
|---|---|---|---|
| **List** | `ListRequest{ string path=1; bool include_md5=2; uint32 filter_max_size=3 }` (7) | `ListResponse{ repeated File file=1 }` (8), **streamed** via `has_next` | `path` uses `/int` (internal flash) or `/ext` (SD card). `File.data` empty for listings. |
| **Stat** | `StatRequest{ string path=1 }` (24) | `StatResponse{ File file=1 }` (25) | Single. `file.type` tells file vs dir; `file.size` in bytes. |
| **Read** | `ReadRequest{ string path=1 }` (9) | `ReadResponse{ File file=1 }` (10), **chunked** via `has_next` | Concatenate `file.data` across chunks until `has_next=false`. Chunk ≈ 512 B. |
| **Write** | `WriteRequest{ string path=1; File file=2 }` (11), **client-chunked** via `has_next` | single `empty`, OK after last chunk | Split payload into `file.data` chunks (~512 B); same `command_id`; `has_next=true` on all but last. |
| **Mkdir** | `MkdirRequest{ string path=1 }` (13) | `empty`, OK | `ERROR_STORAGE_EXIST` if present. |
| **Delete** | `DeleteRequest{ string path=1; bool recursive=2 }` (12) | `empty`, OK | `recursive=true` to remove non-empty dirs (else `ERROR_STORAGE_DIR_NOT_EMPTY`). |
| **Md5sum** | `Md5sumRequest{ string path=1 }` (14) | `Md5sumResponse{ string md5sum=1 }` (15) | Server-side hash; compare after upload. |
| Info | `InfoRequest{path}` (28) | `InfoResponse{uint64 total_space; uint64 free_space}` (29) | Filesystem capacity for `/int` or `/ext`. |
| Rename/move | `RenameRequest{old_path,new_path}` (30) | `empty` | |
| Timestamp | `TimestampRequest{path}` (59) | `TimestampResponse{uint32 timestamp}` (60) | mtime. |
| Tar extract / Backup | `TarExtractRequest{tar_path,out_path}` (71) / `BackupCreate/RestoreRequest{archive_path}` (42/43) | `empty` | Used by qFlipper backup. |

### GUI (`gui.proto`, package `PB_Gui`)

| Command | Request (→) | Response (←) | Notes |
|---|---|---|---|
| **Start screen stream** | `StartScreenStreamRequest{}` (20) | ack `empty` OK, then continuous `ScreenFrame` (22) with `command_id=0` | Device pushes a frame on every display update until stopped. See §5. |
| **Stop screen stream** | `StopScreenStreamRequest{}` (21) | `empty`, OK | |
| **Screen frame** | *(inbound)* `ScreenFrame{ bytes data=1; ScreenOrientation orientation=2 }` (22) | — | `data` = 1024-byte framebuffer. `orientation`: `HORIZONTAL=0`, `HORIZONTAL_FLIP=1`, `VERTICAL=2`, `VERTICAL_FLIP=3`. |
| **Send input** | `SendInputEventRequest{ InputKey key=1; InputType type=2 }` (23) | `empty`, OK | Virtual button press. Enums below. |
| Virtual display | `StartVirtualDisplayRequest{ ScreenFrame first_frame=1; bool send_input=2 }` (26) / `StopVirtualDisplayRequest{}` (27) | `empty` | You *push* frames to the device screen; the client-supplied buffer here is **XBM-packed** (different layout from the outbound stream — see §5). |

**`InputKey`:** `UP=0`, `DOWN=1`, `RIGHT=2`, `LEFT=3`, `OK=4`, `BACK=5` (note RIGHT precedes LEFT).
**`InputType`:** `PRESS=0`, `RELEASE=1`, `SHORT=2`, `LONG=3`, `REPEAT=4`.

Behavioral note from firmware `rpc_gui.c`: the device tracks a press/release sequence counter per key. To emulate a normal tap the simplest reliable pattern is send `SHORT` (which the UI treats as a completed short-press). To emulate a physical hold, send `PRESS` then later `RELEASE` for the same key (the firmware pairs them by sequence). Sending `RELEASE` without a prior `PRESS` logs an "out of sequence" warning but is tolerated.

### Application / loader (`application.proto`, package `PB_App`)

| Command | Request (→) | Response (←) | Notes |
|---|---|---|---|
| **App start** | `StartRequest{ string name=1; string args=2 }` (16) | `empty`, OK or `ERROR_APP_*` | `name` is an app/loader target, e.g. `"Sub-GHz"`, `"NFC"`, or `"Storage"`. `args` is optional (e.g. a file path). `ERROR_APP_SYSTEM_LOCKED (17)` if another app is running. |
| **App load file** | `AppLoadFileRequest{ string path=1 }` (48) | `empty`, OK | Tell the *currently running* app to open a file (e.g. load a `.sub`/`.nfc`). App must already be started and RPC-aware. |
| **App button press** | `AppButtonPressRequest{ string args=1; int32 index=2 }` (49) | `empty`, OK | Trigger an in-app "button" (e.g. SubGHz TX). `ERROR_APP_NOT_RUNNING (21)` if the app isn't RPC-controllable. |
| App button release | `AppButtonReleaseRequest{}` (50) | `empty` | Release the held app button. |
| App button press+release | `AppButtonPressReleaseRequest{ string args=1; int32 index=2 }` (75) | `empty` | Combined convenience (newer firmware). |
| App exit | `AppExitRequest{}` (47) | `empty` | Ask running app to quit. |
| Lock status | `LockStatusRequest{}` (17) | `LockStatusResponse{ bool locked=1 }` (18) | Whether an app currently holds the system lock. |
| App state | *(inbound)* `AppStateResponse{ AppState state=1 }` (58) | — | Async: `APP_CLOSED=0`, `APP_STARTED=1`. |
| Get error / Data exchange | `GetErrorRequest{}` (63) / `DataExchangeRequest{ bytes data=1 }` (65) | `GetErrorResponse{code,text}` (64) | Generic app<->host channel. |

Also available: **GPIO** (`gpio.proto` — `SetPinMode`, `SetInputPull`, `GetPinMode`, `ReadPin`, `WritePin`, `Get/SetOtgMode`; pins `PC0,PC1,PC3,PB2,PB3,PA4,PA6,PA7`), **Property** (`property_get_request` → device property tree), and **Desktop** (`is_locked`, `unlock`, `status_subscribe`/`unsubscribe`, async `Status{locked}`).

---

## 5. Screen framebuffer decoding (1024 bytes → 128×64) — the exact format

**This is the single most error-prone part, so precisely:** the outbound `ScreenFrame.data` is a **raw copy of the Flipper's u8g2/u8x8 canvas buffer** — the firmware literally `memcpy`s `canvas_get_buffer()` into the message (`rpc_gui.c`, `rpc_system_gui_screen_stream_frame_callback`). That buffer is **column-major, vertically page-packed** (the classic SSD1306/ST756x "GDDRAM page" layout), **not** row-major and **not** XBM.

### Layout

- Display: **128 columns (x) × 64 rows (y)**, 1 bit per pixel (1 = pixel on/black).
- Buffer length: `128 * 64 / 8 = 1024` bytes.
- The 64 rows are divided into **8 horizontal "pages" of 8 rows each** (`page = y // 8`, `page` 0 at the top).
- Byte layout is **page-major, then column**:
  `byteIndex = page * 128 + x = (y // 8) * 128 + x`
- Within each byte, the 8 vertical pixels of that page/column are packed **LSB = topmost row**:
  `bit = y % 8`, and `bit 0` is the top pixel of the page.

### The formula

```
pixel(x, y) = (data[(y >> 3) * 128 + x] >> (y & 7)) & 1
```

where `x ∈ [0,127]`, `y ∈ [0,63]`, and `y >> 3 == y // 8`, `y & 7 == y % 8`.

This matches the reference client's `_dump_screen()` (it walks `i = 0..1023`, reverses each byte's bits so the LSB comes first, writes 8 consecutive rows down a column, and advances the page base by 8 every 128 bytes).

### Drop-in Python decoders

Fast, dependency-light with NumPy (returns a `(64,128)` array of 0/1, `1` = lit pixel):

```python
import numpy as np

W, H = 128, 64

def decode_framebuffer(data: bytes) -> np.ndarray:
    """data: 1024 bytes from ScreenFrame.data -> (64,128) uint8, 1=pixel on."""
    assert len(data) == 1024, len(data)
    buf = np.frombuffer(data, dtype=np.uint8).reshape(8, 128)  # [page, x]
    img = np.zeros((H, W), dtype=np.uint8)
    for bit in range(8):                      # bit 0 = top row of each page
        rows = (buf >> bit) & 1               # (8,128)
        img[bit::8, :] = rows                 # page p, bit b -> row p*8 + b
    return img

def to_pillow(data: bytes):
    """1-bit PIL image, 128x64, black pixels where lit (like the real screen)."""
    from PIL import Image
    img = decode_framebuffer(data)
    # 1 (on) -> 0 (black); 0 (off) -> 255 (white)
    return Image.fromarray(((1 - img) * 255).astype(np.uint8), mode="L").convert("1")
```

Pure-stdlib inner loop (no NumPy), same result:

```python
def get_pixel(data, x, y):
    return (data[(y >> 3) * 128 + x] >> (y & 7)) & 1

def to_xbm_rows(data):
    return [[get_pixel(data, x, y) for x in range(128)] for y in range(64)]
```

ASCII preview (handy for debugging):

```python
def ascii_screen(data):
    out = []
    for y in range(64):
        out.append("".join("#" if get_pixel(data, x, y) else " " for x in range(128)))
    return "\n".join(out)
```

To write a real PNG: `to_pillow(frame.data).resize((512,256), Image.NEAREST).save("screen.png")`.

### Two important gotchas

1. **Orientation.** Read `ScreenFrame.orientation`. For most models/screens it is `HORIZONTAL (0)` and the formula above is correct as-is. If a device/app reports `VERTICAL`/`*_FLIP`, rotate/flip the decoded image accordingly (0°/180°/90°/270°). Don't assume horizontal blindly.
2. **The virtual-display buffer is a DIFFERENT format.** When you *send* frames to the device via `StartVirtualDisplayRequest.first_frame` / `gui_screen_frame`, the firmware treats that buffer as **XBM** (row-major, horizontal bit packing, LSB = leftmost pixel) because it draws it with `canvas_draw_xbm`. The firmware code even comments that the outbound canvas buffer and the inbound XBM buffer "are like comparing apples and oranges / glad they both are 1024 for now." **So: decode inbound screenshots with the vertical-page formula above; encode outbound virtual-display frames as XBM.** Do not reuse one codec for both directions.

---

## 6. Existing Python libraries — evaluation

| Library | pip name | Repo | Bundles compiled protos? | Actually uses protobuf RPC? | Maintained? | Verdict |
|---|---|---|---|---|---|---|
| **flipperzero-protobuf** (official-ish) | `pip install flipperzero-protobuf` | `flipperdevices/flipperzero_protobuf_py` (and fork `oltenxyz/flipperzero_protobuf_py`) | **Yes** — ships `flipperzero_protobuf_compiled/*_pb2.py` | **Yes** — this is the real protobuf RPC client (`FlipperProto`, `start_rpc_session`, storage/gui/etc.) | **Marginal.** Latest PyPI `0.1.20221108`, uploaded **2024-03-05**; upstream repo effectively stale. | Best *reference*, risky as a *dependency* — see the protobuf-version problem below. |
| **flipperzero_protobuf_py** (source) | (same package) | `flipperdevices/flipperzero_protobuf_py` | Yes | Yes | Low activity | Read it; borrow `flipper_base.py` framing + `_dump_screen`. |
| **flipperzero_protobuf_py** (origin) | — (git only) | `evilpete/flipperzero_protobuf_py` (Peter Shipley) | Yes | Yes | The upstream author's tree; sporadic | Same code lineage; useful history. |
| **pyFlipper** | `pip install pyflipper` | `wh00hw/pyFlipper` | **No** | **No — this is a TEXT CLI wrapper, not protobuf.** It scripts `>: ` CLI commands (`storage`, `nfc`, `subghz`, `info device`) over serial/WebSocket/TCP. | Active — latest `0.22`, **2026-07-17** | Great if you just want to drive the *text* CLI. **Wrong tool** for protobuf RPC / screen streaming. |
| "flipperzero-protobuf-py" | — | (name people use for the repo above) | — | — | — | Not a distinct PyPI package; it's the repo slug for `flipperzero-protobuf`. |

**The blocker for your setup:** the official `flipperzero-protobuf` wheel pins `protobuf==3.20.2` (alongside `numpy==1.22.3`, `pyserial`). Its bundled `*_pb2.py` were generated by an old `protoc` and, combined with that pin, **will fight your installed protobuf 5.x**. protobuf 3.x-generated modules can raise `TypeError: Descriptors cannot be created directly` / builder-API errors under the 4.x/5.x runtime, and the hard `==3.20.2` pin means `pip install flipperzero-protobuf` may downgrade or conflict in your env.

### Recommendation

**Roll your own thin client, but steal the two hard parts from the reference repo.** Given you already have protobuf 5.x and `grpcio-tools`, this is a couple hours of work and avoids the version conflict entirely:

1. Download the 8 `.proto` files (§2) into one directory.
2. Generate Python modules with your own toolchain (produces `flipper_pb2.py`, `storage_pb2.py`, … that match your protobuf 5.x runtime):
   ```bash
   python -m grpc_tools.protoc -I. --python_out=. \
     flipper.proto storage.proto system.proto application.proto \
     gui.proto gpio.proto property.proto desktop.proto
   ```
   (Only `--python_out` — there is **no gRPC service** in this schema, just messages, so you don't need `--grpc_python_out`. The generated `flipper_pb2` cross-imports the others, so compile them together and keep them importable as a package.)
3. Implement transport = pyserial + the varint framing from §3 + the RPC handshake from §1. Copy the `has_next` accumulation loop for streamed responses and the `_dump_screen` decode from §5.

Use the official `flipperzero_protobuf_py` repo purely as a **reference implementation** (its `flipper_base.py`, `flipper_gui.py`, `flipper_storage.py`, and `cli_helpers._dump_screen` are the canonical, correct logic), and use **pyFlipper only if** you decide the plain text CLI is enough and you don't need protobuf features like screen streaming or chunked binary transfer.

---

## Sources

- flipper.proto / storage.proto / system.proto / gui.proto / application.proto / gpio.proto / property.proto / desktop.proto — https://github.com/flipperdevices/flipperzero-protobuf (branch `dev`)
- Firmware RPC core (framing, `start_rpc_session`, `PB_ENCODE_DELIMITED`) — https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/rpc/rpc.c
- Firmware RPC GUI (screen stream `memcpy` of canvas buffer, input sequence logic, XBM virtual display) — https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/services/rpc/rpc_gui.c
- Reference Python client (handshake, varint, `_dump_screen` framebuffer decode) — https://github.com/flipperdevices/flipperzero_protobuf_py
- PyPI `flipperzero-protobuf` (0.1.20221108, 2024-03-05, pins protobuf 3.20.2) — https://pypi.org/project/flipperzero-protobuf/
- PyPI `pyflipper` (0.22, 2026-07-17, text-CLI wrapper) — https://pypi.org/project/pyflipper/ and https://github.com/wh00hw/pyFlipper
- Flipper CLI docs — https://docs.flipper.net/zero/development/cli

Local paths: no files were written; all findings are in this response.