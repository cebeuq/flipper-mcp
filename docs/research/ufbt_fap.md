All facts verified against the local SDK and a real build. Here is the complete research report.

---

# ufbt & FAP Development Guide (Windows, ufbt 0.2.6, SDK f7 / firmware 1.4.3, API 87.1)

Everything below was **verified against the locally deployed SDK** at `C:\Users\yairh\.ufbt\current\` (manifest fields read from `scripts\fbt\appmanifest.py`, API signatures from `sdk_headers\f7_sdk\`), and the example app was **actually scaffolded and compiled** with the installed ufbt 0.2.6 (`APPCHK ... Target: 7, API: 87.1`).

Local environment (from `ufbt status`):

| Item | Value |
|---|---|
| uFBT version | 0.2.6 |
| State dir | `C:\Users\yairh\.ufbt` |
| SDK dir | `C:\Users\yairh\.ufbt\current` |
| Toolchain dir | `C:\Users\yairh\.ufbt\toolchain` |
| Target / Channel / Version | f7 / release / 1.4.3 (API 87.1) |

---

## 1. Scaffolding a new app: `ufbt create APPID=my_app`

Run it in an **empty folder** (the folder name does not need to match the appid, but conventionally does):

```powershell
mkdir my_app; cd my_app
ufbt create APPID=my_app
```

Files generated (verified by running it):

```
my_app/
├── application.fam              # app manifest
├── my_app.c                     # entry-point stub (logs "Hello world")
├── my_app.png                   # 10x10 icon (placeholder, embedded in the .fap)
├── images/                      # empty dir (.gitkeep) for fap_icon_assets
│   └── .gitkeep
└── .github/
    └── workflows/build.yml      # GitHub Actions CI (flipperdevices/flipperzero-ufbt-action)
```

The generated `application.fam`:

```python
App(
    appid="my_app",  # Must be unique
    name="App my_app",  # Displayed in menus
    apptype=FlipperAppType.EXTERNAL,
    entry_point="my_app_app",
    stack_size=2 * 1024,
    fap_category="Examples",
    # Optional values
    # fap_version="0.1",
    fap_icon="my_app.png",  # 10x10 1-bit PNG
    # fap_description="A simple app",
    # fap_author="J. Doe",
    # fap_weburl="https://github.com/user/my_app",
    fap_icon_assets="images",  # Image assets to compile for this application
)
```

### Full `application.fam` field reference

`application.fam` is a **Python file** executed by the build system; it must contain one or more `App(...)` calls. Field list verified against `FlipperApplication` dataclass in `scripts/fbt/appmanifest.py` of SDK 1.4.3:

**Core fields (all app types):**

| Field | Type / default | Meaning |
|---|---|---|
| `appid` | str, **required** | Unique build-system ID. Must match regex `^[a-z0-9_]+$` (lowercase letters, digits, underscore only — no dashes, no uppercase). Also becomes the `.fap` filename. |
| `apptype` | `FlipperAppType`, **required** | For SD-card apps use `FlipperAppType.EXTERNAL`. (There is no `FAP` enum value — a "FAP" is what an `EXTERNAL` app builds into.) Full enum: `SERVICE`, `SYSTEM`, `APP`, `DEBUG`, `ARCHIVE`, `SETTINGS`, `STARTUP`, `EXTERNAL`, `MENUEXTERNAL`, `METAPACKAGE`, `PLUGIN`. `MENUEXTERNAL` = FAP listed in the main menu but not auto-deployed; `PLUGIN` = `.fal` library loaded by a host app. |
| `name` | str, `""` | Human-readable name shown in the Apps menu on the device. |
| `entry_point` | str, `None` (required for EXTERNAL) | Name of the C function used as the entry point. Signature must be `int32_t fn(void* p)`. For C++, declare it `extern "C"`. |
| `stack_size` | int, `2048` | Bytes of stack for the app's thread. Too small → crash (furi_check / stack overflow); too big → wastes RAM. `2 * 1024` is a common starting point; GUI-heavy apps often need `4 * 1024`. |
| `sources` | list, `["*.c*"]` | Glob masks for source files, relative to the app folder (recursive). Prefix a mask with `!` to exclude (e.g. `["*.c*", "!test/*"]`). |
| `requires` | list, `[]` | App IDs this app depends on (for FAPs, mainly used by `PLUGIN` apps to name their host app). |
| `conflicts` | list, `[]` | App IDs that cannot be built together with this one. |
| `provides` | list, `[]` | Additional app IDs to pull into the build (functionally like `requires`). |
| `targets` | list, `["all"]` | Hardware targets the app supports, e.g. `["f7"]`. |
| `cdefines` | list, `[]` | Global C preprocessor definitions. |
| `sdk_headers` | list, `[]` | Headers to export into the SDK API (used by apps that expose plugin APIs). |
| `icon` | str, `None` | Built-in animated icon name — **firmware-internal apps only**, not for FAPs (use `fap_icon`). |
| `order` | int, `0` | Sort order within the menu group. |
| `flags` | list, `["Default"]` | Internal firmware flags; not for FAPs. |
| `resources` | str, `None` | SD-card resources folder — **forbidden for EXTERNAL apps** (build error); use `fap_file_assets` instead. |

**FAP-specific fields (EXTERNAL / MENUEXTERNAL / PLUGIN only):**

| Field | Type / default | Meaning |
|---|---|---|
| `fap_version` | str `"0.1"` or tuple `(0, 1)` | App version, must be at least `"major.minor"` (parse error otherwise). |
| `fap_icon` | str, `None` | Path to a **10x10 pixel, 1-bit PNG** shown next to the app in the Apps menu. |
| `fap_category` | str, `""` | Menu category and SD-card subfolder: the FAP installs to `/ext/apps/<fap_category>/<appid>.fap`. Standard categories: `Bluetooth`, `Games`, `GPIO`, `Infrared`, `iButton`, `Media`, `NFC`, `RFID`, `Sub-GHz`, `Tools`, `USB`, `Examples`. |
| `fap_description` | str, `""` | Short description (shown in catalogs/loaders). |
| `fap_author` | str, `""` | Author name. |
| `fap_weburl` | str, `""` | Project URL. |
| `fap_icon_assets` | str, `None` | Folder of PNGs compiled into the app; generates `<appid>_icons.h` with `const Icon I_<filename>` symbols (animated folders become `A_<name>`). |
| `fap_icon_assets_symbol` | str, `None` | Overrides the `<appid>` prefix of the generated icons header/symbols. |
| `fap_libs` | list, `[]` | Extra SDK libraries to link (e.g. `["assets"]`, `["mbedtls"]`). |
| `fap_private_libs` | list of `Lib(...)`, `[]` | Private libraries built from sources bundled with the app: `Lib(name="...", fap_include_paths=["."], sources=["*.c*"], cflags=[], cdefines=[], cincludes=[])` — sources live in `lib/<name>/` inside the app folder. |
| `fap_extbuild` | list of `ExtFile(...)`, `[]` | Files produced by an external command before build: `ExtFile(path="...", command="...")`. |
| `fap_file_assets` | str, `None` | Folder of arbitrary files packed into the FAP and unpacked to `/ext/apps_assets/<appid>/` on first run. |
| `fal_embedded` | bool, `False` | PLUGIN-only: embed the `.fal` inside the host app's `.fap`. |

Validation rules enforced by the SDK (will hard-fail the build):
- `appid` must match `^[a-z0-9_]+$`.
- `fap_version` must have at least 2 numeric components.
- EXTERNAL apps may **not** use `resources`; non-FAP apps may **not** use `fap_extbuild`, `fap_private_libs`, `fap_icon_assets`.
- PLUGIN apps may not set `stack_size` and must set `requires`.

---

## 2. Directory layout of a FAP project

Source files go **directly in the app folder** (any `.c`/`.cpp` matching `sources` masks, searched recursively). Typical grown-up layout:

```
my_app/                      # project root == app folder (application.fam lives here)
├── application.fam          # manifest (required, this defines the app)
├── my_app.c                 # source — any *.c* here is compiled by default
├── scenes/                  # more sources — subdirs are included by the default glob
│   └── ...
├── lib/                     # fap_private_libs sources (lib/<libname>/...)
├── images/                  # fap_icon_assets → compiled into <appid>_icons.h
│   └── my_icon.png
├── files/                   # fap_file_assets (optional, any name)
├── my_app.png               # fap_icon (10x10 1-bit)
├── dist/                    # BUILD OUTPUT (created by ufbt)
│   ├── my_app.fap           #   the installable package
│   └── debug/
│       └── my_app_d.elf     #   ELF with debug symbols for gdb
├── .vscode/                 # created by `ufbt vscode_dist`
└── .github/workflows/       # CI from `ufbt create`
```

Intermediate build objects go to `C:\Users\yairh\.ufbt\build\`; the finished `.fap` is installed into the project's `dist\` folder. One folder can contain multiple `App(...)` entries (e.g. a main app plus PLUGINs), and `ufbt APPID=<id>` selects which one to work with.

---

## 3. Minimal "hello world" FAP — complete and compile-verified

Entry point signature: `int32_t app_main(void* p)` — the name is whatever `entry_point` says; `p` is an optional argument string from the loader (usually `NULL`). Return `0` for success.

The canonical minimal GUI pattern is: **ViewPort + draw callback + input callback → FuriMessageQueue → main loop → cleanup**. Both callbacks run on the **GUI thread**, so the input callback only forwards events into a queue that the app thread consumes.

**This exact pair of files was built successfully against SDK 1.4.3 / API 87.1 on this machine** (plus the scaffolded `my_app.png` icon).

### `application.fam`

```python
App(
    appid="my_app",
    name="My App",
    apptype=FlipperAppType.EXTERNAL,
    entry_point="my_app_app",
    stack_size=2 * 1024,
    fap_category="Examples",
    fap_version="0.1",
    fap_icon="my_app.png",  # 10x10 1-bit PNG in the app folder
    fap_description="Minimal hello-world FAP",
    fap_author="You",
)
```

(Note: `fap_icon_assets="images"` was removed since this example uses no image assets; keep it if you keep the `images/` folder.)

### `my_app.c`

```c
#include <furi.h>
#include <gui/gui.h>
#include <gui/view_port.h>
#include <input/input.h>

/* Draw callback: runs in the GUI thread every time the viewport is redrawn. */
static void my_app_draw_callback(Canvas* canvas, void* context) {
    UNUSED(context);
    canvas_clear(canvas);
    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str(canvas, 4, 22, "Hello, Flipper!");
    canvas_set_font(canvas, FontSecondary);
    canvas_draw_str(canvas, 4, 36, "Press Back to exit");
}

/* Input callback: runs in the GUI thread; just forward events to our queue. */
static void my_app_input_callback(InputEvent* input_event, void* context) {
    FuriMessageQueue* event_queue = context;
    furi_message_queue_put(event_queue, input_event, FuriWaitForever);
}

/* Entry point: must match entry_point in application.fam. */
int32_t my_app_app(void* p) {
    UNUSED(p);

    /* Queue for input events coming from the GUI thread. */
    FuriMessageQueue* event_queue = furi_message_queue_alloc(8, sizeof(InputEvent));

    /* ViewPort: our drawing surface + input receiver. */
    ViewPort* view_port = view_port_alloc();
    view_port_draw_callback_set(view_port, my_app_draw_callback, NULL);
    view_port_input_callback_set(view_port, my_app_input_callback, event_queue);

    /* Attach the viewport to the GUI system, fullscreen. */
    Gui* gui = furi_record_open(RECORD_GUI);
    gui_add_view_port(gui, view_port, GuiLayerFullscreen);

    /* Main loop: block on the queue until Back is pressed. */
    InputEvent event;
    bool running = true;
    while(running) {
        if(furi_message_queue_get(event_queue, &event, FuriWaitForever) == FuriStatusOk) {
            if(event.type == InputTypeShort && event.key == InputKeyBack) {
                running = false;
            }
        }
        view_port_update(view_port);
    }

    /* Cleanup, in reverse order of allocation. */
    gui_remove_view_port(gui, view_port);
    furi_record_close(RECORD_GUI);
    view_port_free(view_port);
    furi_message_queue_free(event_queue);

    return 0;
}
```

API facts verified in the local SDK headers (beware of tutorials using older names):
- Allocator is **`view_port_alloc(void)`** — there is no `view_port_create`.
- `ViewPortDrawCallback` = `void (*)(Canvas*, void*)`; `ViewPortInputCallback` = `void (*)(InputEvent*, void*)`.
- `gui_add_view_port(Gui*, ViewPort*, GuiLayer)` with `GuiLayerFullscreen`; GUI record name is the macro `RECORD_GUI` (`"gui"`).
- `furi_message_queue_alloc(msg_count, msg_size)` / `_get` / `_put` / `_free`; `furi_message_queue_get` returns `FuriStatus` (`FuriStatusOk`).
- `InputEvent` has `.key` (`InputKeyBack`, `InputKeyOk`, ...) and `.type` (`InputTypePress`, `InputTypeShort`, `InputTypeLong`, `InputTypeRepeat`, `InputTypeRelease`).
- `canvas_draw_str(Canvas*, int32_t x, int32_t y, const char*)` — y is the text **baseline**; screen is 128x64, 1-bit.
- `UNUSED(x)` macro silences unused-parameter errors (builds use `-Werror`).

---

## 4. Build and deploy commands

All commands run **from the app folder** (where `application.fam` is):

| Command | What it does |
|---|---|
| `ufbt` | Default target: builds the app; output installed to `dist\<appid>.fap` (+ `dist\debug\<appid>_d.elf`). Ends with `APPCHK ... Target: 7, API: 87.1` (the API your FAP was built against). |
| `ufbt launch` | Builds, then deploys to a USB-connected Flipper and starts the app. Mechanics (from `runfap.py` in the SDK): opens the serial CLI, uploads `dist\<appid>.fap` to **`/ext/apps/<fap_category>/<appid>.fap`** via the storage protocol, closes any running app (`loader close`), then starts it with `loader open`. Port autodetects; override with `ufbt launch FLIP_PORT=COM5`. qFlipper/lab.flipper.net must be disconnected (they hold the serial port). |
| `ufbt cli` | Opens an interactive serial CLI session to the device (log viewing with `log`, storage commands, etc.). |
| `ufbt flash` | Flashes the **full firmware** (the SDK's copy, 1.4.3) via an SWD probe (ST-Link/J-Link/Blackmagic). Not needed for app development. |
| `ufbt flash_usb` | Flashes full firmware over USB (DFU-style update package). |
| `ufbt update` | (Bootstrap subcommand) Re-downloads/updates the SDK. Channel selection: `ufbt update --channel=release` (also `rc`, `dev`), specific version/branch: `ufbt update --branch=1.4.3`, custom source: `--url=...`, `--index-url=...`, `--local=<path>`, target: `--hw-target=f7`. |
| `ufbt status` | Shows SDK state (version, channel, dirs). |
| `ufbt clean` | Removes build artifacts; `ufbt clean --purge` removes the whole SDK state. |
| `ufbt create APPID=<id>` | Scaffolds an app (section 1). |
| `ufbt vscode_dist` | Generates VS Code config (section 6). |
| `ufbt debug` / `ufbt debug_other` | Attach gdb via SWD probe (FAP debug symbols auto-loaded). |
| `ufbt lint` / `ufbt format` | clang-format check / apply, using the project's `.clang-format`. |
| `ufbt dotenv_create` | Creates a `.env` for a per-project SDK (pin different SDK versions per project). |
| `ufbt -h` | Full option list, including `VERBOSE=1`, `APPID=`, `FORCE=1`, `OTHER_ELF=`, SWD options. |

Where things land:
- Built package: `<project>\dist\<appid>.fap` (debug ELF in `dist\debug\`).
- On the device SD card: `/ext/apps/<fap_category>/<appid>.fap` (e.g. `/ext/apps/Examples/my_app.fap`). `ufbt launch` puts it there automatically; you can also copy the `.fap` there manually with qFlipper or the SD card, then run it from **Apps** on the device.

---

## 5. The app icon (`fap_icon`)

- Must be a **10x10 pixel PNG with 1-bit color depth** (pure black/white — no grayscale, no alpha). It is embedded in the `.fap` binary and shown next to the app name in the device menu.
- `ufbt create` supplies a valid placeholder (`my_app.png`) — edit it, keeping it 10x10 black/white.
- Referenced by filename in the manifest: `fap_icon="my_app.png"` (path relative to the app folder).
- Wrong dimensions/depth fail at build time in the icon-processing step.
- Separate concept: `fap_icon_assets="images"` compiles every PNG in `images\` into C data — include `<my_app_icons.h>` and draw them with `canvas_draw_icon(canvas, x, y, &I_<filename>)`. These in-app images must also be 1-bit black/white PNGs (any size up to 128x64).

---

## 6. VS Code integration: `ufbt vscode_dist`

Run once in the app folder:

```powershell
ufbt vscode_dist
```

Verified from the SDK's SConstruct, it installs into the project:
- `.vscode\` — `c_cpp_properties.json`, `settings.json`, `tasks.json` (Build/Launch tasks), `launch.json` (gdb attach configs for ST-Link/J-Link/Blackmagic with firmware + FAP symbols), `extensions.json` — with absolute paths to the ufbt-managed `arm-none-eabi-gcc`, `gdb-py3`, `openocd`, and `clangd` substituted in.
- Helper dotfiles: `.clang-format`, `.clangd`, `.editorconfig`, `.gitignore`.
- A clangd compilation database for the app, so IntelliSense/clangd resolves all SDK headers.

Then open the folder in VS Code: Ctrl+Shift+B builds; the Run/Debug panel can launch the app on the device and attach the debugger (SWD probe required for actual debugging; `launch` alone works over plain USB).

---

## 7. Common build errors and fixes

| Error | Cause and fix |
|---|---|
| `fbt: warning: App folder ...: missing manifest (application.fam)` | You ran `ufbt` outside an app folder. `cd` into the folder containing `application.fam`. |
| `Invalid appid 'My-App'. Must match regex '^[a-z0-9_]+$'` | appid has uppercase/dashes/spaces. Use lowercase + underscores only. |
| `undefined reference to ...` for your entry point / app does nothing | `entry_point` in `application.fam` doesn't match the C function name exactly (or the C++ function isn't `extern "C"`). |
| `error: unused parameter 'p' [-Werror=unused-parameter]` | Builds use `-Werror`. Wrap unused params: `UNUSED(p);`. Same for any warning — all warnings are errors. |
| `implicit declaration of function 'view_port_create'` | Old tutorial API names. Current SDK: `view_port_alloc()`. Generally, missing `#include` or renamed API — check `~\.ufbt\current\sdk_headers\f7_sdk\`. |
| `fatal error: my_app_icons.h: No such file or directory` | You include the generated icons header but `fap_icon_assets` is not set (or folder name mismatch). Either add `fap_icon_assets="images"` or delete the `#include`. |
| Icon build failure / imglint complaint | `fap_icon` PNG isn't 10x10 or isn't 1-bit black/white. Re-export as monochrome PNG, exactly 10x10. |
| `API version mismatch` on device (app refuses to load), or app shown as incompatible | The `.fap` was built against a different firmware API than the device runs (yours must match API 87.1 ↔ firmware 1.4.3 release). Fix: `ufbt update --channel=release` (or the channel your device firmware is from: `dev`/`rc`), rebuild — or update the device firmware to match. This is the single most common beginner problem. |
| App crashes on start with `furi_check failed` / random crash mid-run | Usually stack overflow — increase `stack_size` (e.g. `4 * 1024`) and rebuild. Also check you don't call GUI functions from the wrong thread. |
| Device freezes/reboots after app exit | Cleanup order wrong: you must `gui_remove_view_port()` **before** `view_port_free()`, and close every record you opened (`furi_record_close(RECORD_GUI)`). |
| `ufbt launch` can't find the device / times out | qFlipper or lab.flipper.net web CLI is holding the serial port — close them. Device must be at the desktop (not inside a running app). Force a port with `ufbt launch FLIP_PORT=COMx`. |
| `App ... cannot have 'resources' in manifest` | EXTERNAL apps can't use `resources`; use `fap_file_assets` instead. |
| `Invalid version '1'. Must be in the form 'major.minor'` | `fap_version` needs at least two components: `"1.0"`. |
| Weird/stale build behavior after SDK update | `ufbt clean` (per-project artifacts), or `ufbt clean --purge` + `ufbt update` to redeploy the SDK from scratch. |
| Toolchain download/unpack errors on Windows | Antivirus or OneDrive interfering with `%USERPROFILE%\.ufbt\toolchain`; also avoid paths with spaces/non-ASCII for the project. |

---

### Quick-start recap

```powershell
mkdir my_app; cd my_app
ufbt create APPID=my_app     # scaffold
# edit my_app.c / application.fam (example above)
ufbt                         # build -> dist\my_app.fap
ufbt launch                  # build + copy to /ext/apps/Examples/ + run on device
ufbt cli                     # serial CLI ("log" to watch FURI_LOG_* output)
ufbt vscode_dist             # VS Code config
```

Sources: local SDK ground truth (`C:\Users\yairh\.ufbt\current\scripts\fbt\appmanifest.py`, `scripts\ufbt\SConstruct`, `scripts\fbt_tools\fbt_extapps.py`, `scripts\runfap.py`, `sdk_headers\f7_sdk\applications\services\gui\{gui,view_port,canvas}.h`, `...\input\input.h`, `...\furi\core\{message_queue,record}.h`), verified builds in `C:\Users\yairh\AppData\Local\Temp\faptest\my_app\`, plus [flipperzero-ufbt README](https://github.com/flipperdevices/flipperzero-ufbt) and the [Flipper App Manifests documentation](https://developer.flipper.net/flipperzero/doxygen/app_manifests.html).