# flipper-mcp — Standalone, star-optimized MCP server (design spec)

**Fecha:** 2026-07-19
**Autor:** Yair Hernández (`yairhdz24` / yairhdz107@gmail.com)
**Estado:** Aprobado en brainstorming — pendiente de revisión del spec

---

## 1. Objetivo

Convertir el MCP existente (`flipper-mcp`, hoy en `/Users/mac/Desktop/flipper-zero-Utils/flipper-mcp/`, construido en Windows y sin git) en un **repositorio público standalone, pulido al máximo, cuyo fin explícito es acumular estrellas en GitHub** y volverse el servidor MCP de referencia para Flipper Zero.

**Métrica de éxito:** superar al líder actual de la categoría (`busse/flipperzero-mcp`, 27★). El nicho está prácticamente vacío (líder real con 27★; el resto entre 0 y 13★), así que es un objetivo alcanzable con ejecución de calidad.

### Diferenciadores validados (features que la competencia NO anuncia)
1. **Funciona sin puerto COM** — transporte raw WinUSB/libusb vía `pyusb` cuando no existe un `COMx` (útil en Windows con driver ADB/WinUSB).
2. **Build & deploy de FAPs por USB** — scaffold → `ufbt` build → subida por RPC + launch, sin necesitar COM port. **Feature asesina, nadie más la tiene.**
3. **Screenshots** del framebuffer 128×64 → PNG, botones virtuales fiables, 35 tools en total, auto-selección de transporte (serial → USB).

---

## 2. Alcance de ESTA sesión

Playbook completo:
- Separar el MCP a un repo nuevo, limpio y profesional.
- Verificarlo **en vivo en macOS** contra el Flipper conectado (`/dev/tty.usbmodemflip_Ali5aree1`).
- Grabar un **GIF demo real** desde el device.
- README asesino + metadata PyPI + CI.
- **Publicar público** en `github.com/yairhdz24/flipper-mcp`.
- Dejar preparada la distribución (registries/comunidad) como segundo round.

### Fuera de alcance (explícito)
- ❌ No se incluyen payloads propios ni el repo de terceros (`D4rkDr4gon/flipper-zero-Utils`). Eso vive en un repo aparte (`flipper-lab`), posterior. Mantener el MCP limpio es una decisión de posicionamiento.
- ❌ No se agregan transportes BLE/WiFi (YAGNI; la historia USB ya es fuerte).
- ❌ El **upload final a PyPI** no se ejecuta automáticamente: requiere la cuenta/token PyPI de Yair. Se deja todo listo (build sdist+wheel verificado) y Yair corre `uv publish`/`twine upload`.

---

## 3. Estructura del repositorio

```
flipper-mcp/
├── README.md                    hero + GIF + features + install + tabla tools + safety
├── LICENSE                      MIT © 2026 Yair Hernández
├── CONTRIBUTING.md
├── CHANGELOG.md                 empieza en 0.1.0
├── pyproject.toml               metadata completa PyPI, entry-point, uvx-ready
├── requirements.txt             (se mantiene para instalación manual)
├── .gitignore                   .venv, __pycache__, *.pyc, dist/, build/, *.egg-info, .DS_Store
├── .mcp.json                    registro del server para quien clone (project scope)
├── .github/
│   └── workflows/ci.yml         lint (ruff) + smoke import en Py 3.10–3.13, matriz mac/linux/win
├── flipper_mcp/                 código core (movido tal cual + pulido multiplataforma menor)
│   ├── server.py  device.py  cli.py  fap.py  __main__.py  __init__.py
│   ├── transport/  (base, usb, serialport, discovery)
│   └── rpc/        (framing, session, proto/*_pb2.py)
├── proto/                       *.proto fuente
├── scripts/                     probes, compile_protos, (fix-flipper-driver.ps1 se conserva: útil en Windows)
├── examples/
│   └── mcp_demo/                app FAP de ejemplo (counter) como showcase
├── docs/
│   ├── setup.md                 instalación mac/linux/windows + registro en Claude
│   ├── superpowers/specs/       este spec + futuros
│   └── research/                notas de protocolo (señal de confianza)
└── assets/
    └── demo.gif                 hero, capturado del device real
```

Notas:
- El código Python NO cambia de estructura interna (evitar romper lo que ya funciona). Solo se mueve de `flipper-mcp/` a la raíz del repo nuevo y se aplica pulido multiplataforma mínimo.
- `apps/mcp_demo/` del original se renombra a `examples/mcp_demo/` para leerse como "ejemplo/showcase" y no como app del usuario.

---

## 4. Trabajo por fases

### Fase A — Separar y verificar en macOS
1. Copiar (no mover) el contenido de `flipper-mcp/` al repo nuevo, reorganizando `apps/` → `examples/`.
2. Recrear el `.venv` en Mac: `python3 -m venv .venv` + `pip install -r requirements.txt`. (El `.venv` original es de Windows: layout `Scripts/`, inservible en Mac. No se copia; queda en `.gitignore`.)
3. Verificación en vivo contra el Flipper conectado:
   - `python -m flipper_mcp` arranca sin error (import + registro de tools).
   - Llamada real de `device_info` y `screenshot` por el transporte serial (`/dev/tty.usbmodemflip_Ali5aree1`).
   - Evidencia guardada (salida real + PNG de screenshot). Si el device no respondiera, se documenta y se ajusta el transporte antes de seguir.

**Criterio de aceptación A:** el MCP responde device info real y captura un screenshot en macOS.

### Fase B — GIF demo real
1. Capturar una secuencia de screenshots del framebuffer 128×64 mientras se navega el menú / se presionan botones (y, si es viable, se compila+lanza el FAP demo).
2. Escalar cada frame (nearest-neighbor, sin blur) y unirlos en un GIF animado con Pillow → `assets/demo.gif`.
3. El GIF debe verse legible y mostrar interacción real, no un mockup.

**Criterio de aceptación B:** existe `assets/demo.gif` construido a partir de screenshots reales del device.

### Fase C — README asesino + docs
1. README con: hero de una línea, GIF hasta arriba, badges (PyPI, Python versions, License, CI), lista de features destacando los 3 diferenciadores, install de 30 segundos (`uvx flipper-mcp` / pip), snippet de registro en Claude para **mac/linux/windows**, tabla de 35 tools, showcase "haz tu propia FAP", y **nota legal RF** (transmitir solo en frecuencias/hardware autorizados).
2. `docs/setup.md` multiplataforma. Reemplazar todas las rutas `C:\Users\yairh\...` por rutas relativas/mac.
3. `CONTRIBUTING.md` y `CHANGELOG.md` (0.1.0).

**Criterio de aceptación C:** el README no contiene rutas Windows-only ni referencias a que "solo funciona en esta máquina"; el registro en Claude está documentado para las 3 plataformas.

### Fase D — Empaquetado PyPI + CI
1. `pyproject.toml` con metadata completa: `authors`, `license`, `keywords` (flipper-zero, mcp, model-context-protocol, claude), `classifiers`, `project.urls` (Homepage/Repository/Issues), `readme = "README.md"`.
2. `python -m build` genera sdist + wheel sin warnings; verificar que `uvx --from ./dist/....whl flipper-mcp` (o equivalente local) arranca.
3. `.github/workflows/ci.yml`: instala, corre `ruff check` y un smoke test que importa `flipper_mcp.server` y valida que registra las 35 tools (sin device).
4. **Upload a PyPI:** documentado como paso manual de Yair (`uv publish` con su token). No se ejecuta en la sesión.

**Criterio de aceptación D:** el paquete construye limpio y el smoke test pasa localmente; el CI está definido.

### Fase E — Publicar público
1. **Escaneo de secretos** antes de cualquier commit que se vaya a pushear: buscar tokens (`gho_`, `ghp_`, `sk-`, `AKIA`, PyPI `pypi-`), claves privadas, `.env`. El MCP no maneja secretos (es control USB), se espera limpio; se verifica igual.
2. Confirmar `.gitignore` deja fuera `.venv/`, `dist/`, `__pycache__/`, `.DS_Store`.
3. Commits limpios y ordenados por fase.
4. `gh repo create yairhdz24/flipper-mcp --public --source . --description "<hero>" --push`.
5. Añadir topics vía `gh repo edit`: `flipper-zero mcp model-context-protocol claude anthropic usb protobuf ufbt`.

**Criterio de aceptación E:** el repo público existe en `github.com/yairhdz24/flipper-mcp` con README+GIF renderizando, sin secretos, con topics.

### Fase F — Distribución (entregable, no ejecución automática)
Lista lista-para-pegar de: awesome-mcp-servers (PR), glama.ai, smithery.ai, mcp.so, PulseMCP, y posts para r/flipperzero y Discord de Flipper. Con textos redactados.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El device no responde en Mac (permisos serial, firmware) | Fase A es gate: si falla, se depura el transporte serial antes de seguir; hay device conectado para probar. |
| `pyusb`/`libusb-package` falla al instalar en Mac | En Mac se usa el transporte serial (pyserial), que no necesita libusb; si libusb-package falla, se marca opcional. |
| Publicar público expone algo sensible | Escaneo de secretos obligatorio (Fase E) + `.gitignore` verificado antes del push. |
| PyPI upload requiere credenciales de Yair | Se deja todo construido; el upload es paso manual documentado. |
| El nombre `flipper-mcp` colisiona en PyPI | Verificar disponibilidad del nombre en PyPI en Fase D; si está tomado, usar `flipper-zero-mcp` como fallback en `pyproject` (el repo GitHub sigue siendo `flipper-mcp`). |

---

## 6. No destructivo

Todo se construye en `/Users/mac/Desktop/flipper-mcp/` (carpeta nueva). Las carpetas originales (`/Users/mac/Desktop/flipper-zero-Utils/flipper-mcp/` y el repo descargado) quedan intactas hasta que Yair confirme que puede limpiarlas.
