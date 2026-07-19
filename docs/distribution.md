# Distribution & promotion kit

Ready-to-use steps and copy to get `flipper-mcp` in front of people and earn stars.
Run these **after** the repo is public and (ideally) after the PyPI upload.

## One-line pitch (reuse everywhere)

> **flipper-mcp** — control your Flipper Zero from Claude over USB. No COM port needed,
> screenshots, RF/NFC/IR/GPIO, and you can even build & deploy your own FAPs — all over USB.
> Works on macOS, Linux and Windows. https://github.com/yairhdz24/flipper-mcp

## 1. Publish to PyPI (Yair runs this — needs your PyPI token)

```bash
cd /Users/mac/Desktop/flipper-mcp
# Build fresh artifacts (already built into dist/ during setup):
./.venv/bin/python -m build
# Upload (you'll be prompted for your PyPI API token, user "__token__"):
./.venv/bin/python -m twine upload dist/*
```

Get a token at https://pypi.org/manage/account/token/ (scope it to the project after the
first upload). Then verify from a clean shell:

```bash
uvx flipper-mcp   # should start the server (Ctrl+C to stop)
```

Once live, the PyPI badge in the README turns green automatically.

## 2. MCP registries & directories

| Where | How | Action |
|---|---|---|
| **awesome-mcp-servers** (`punkpeye/awesome-mcp-servers`) | GitHub PR | Add a bullet under the hardware/IoT section (entry below) |
| **glama.ai/mcp/servers** | Auto-indexes public GitHub repos tagged `mcp` | Already tagged — submit/refresh at https://glama.ai/mcp/servers |
| **smithery.ai** | Sign in with GitHub, "Add server" | Point at the repo; add the `.mcp.json` command `flipper-mcp` |
| **mcp.so** | Submit form | Submit repo URL + the one-line pitch |
| **PulseMCP** (pulsemcp.com) | Submit form | Submit repo URL + pitch |

**awesome-mcp-servers PR entry (paste into the list):**

```markdown
- [flipper-mcp](https://github.com/yairhdz24/flipper-mcp) 🐍 🏠 — Control a Flipper Zero over USB from Claude: screenshots, RF/NFC/IR/GPIO, and build+deploy your own FAPs. Works with no COM port. Cross-platform.
```

## 3. Flipper community

**r/flipperzero post (title + body):**

- Title: `I built an MCP server to control the Flipper Zero from Claude (open source, cross-platform)`
- Body:
  > I made **flipper-mcp**, an open-source MCP server that lets Claude (or any MCP client)
  > drive a Flipper Zero over USB — screenshots, storage, Sub-GHz/NFC/IR/GPIO, and it can
  > even scaffold, build and deploy your own FAPs over USB (no COM port needed). Works on
  > macOS, Linux and Windows. Feedback and PRs welcome!
  > Repo: https://github.com/yairhdz24/flipper-mcp

**Flipper Discord** (`#projects` / `#community-apps`): same short pitch + repo link + the demo GIF.

**awesome-flipperzero lists** (`djsime1/awesome-flipperzero`): open a PR adding the repo under
"Tools / companion apps" with the one-line pitch.

## 4. Hacker News / X (optional, higher variance)

- HN "Show HN": `Show HN: flipper-mcp – control a Flipper Zero from Claude over USB`, link the repo, first comment explains the no-COM-port + FAP-deploy angle.
- X/Twitter: short thread with the demo GIF; tag the MCP + Flipper communities.

## Checklist

- [ ] PyPI upload done, `uvx flipper-mcp` verified
- [ ] awesome-mcp-servers PR opened
- [ ] glama.ai / smithery.ai / mcp.so / PulseMCP submitted
- [ ] r/flipperzero post
- [ ] Flipper Discord post
- [ ] awesome-flipperzero PR
- [ ] (optional) Show HN / X thread
