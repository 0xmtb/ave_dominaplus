# VS Code development on Windows (WSL)

This guide explains how to run and debug this integration from VS Code on Windows.

## Prerequisites

- Visual Studio Code on Windows
- WSL2 installed and working
- A container runtime available from WSL (required by Dev Containers)
- VS Code extensions:
  - `Remote - WSL`
  - `Dev Containers`

## Clone and open in WSL

1. Open a WSL terminal.
2. Clone the repository:

   ```bash
   git clone https://github.com/emmeoerre/ave_dominaplus.git
   cd ave_dominaplus
   ```

3. Open the folder in VS Code from WSL:

   ```bash
   code .
   ```

## Start the devcontainer

1. In VS Code, run **Dev Containers: Reopen in Container**.
2. Wait for the container build to finish.
   - `postCreateCommand` runs `scripts/setup`, which installs Python requirements.

## Run and debug Home Assistant (F5)

1. Open the **Run and Debug** view.
2. Select the launch profile **Home Assistant**.
3. Press **F5**.

This starts Home Assistant using the local `config/` folder. The custom integration in this repository is already available in the running setup, so you can debug it directly from breakpoints in `custom_components/ave_dominaplus/`.

The Home Assistant UI is available at `http://localhost:18125`.

## Zeroconf autodiscovery debugging

For mDNS/Zeroconf debugging from Windows + WSL, use the alternate devcontainer file `_zeroconf_.devcontainer.json`.

### 1) Configure WSL networking

Create or update `%UserProfile%\\.wslconfig` on Windows:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
firewall=false
autoProxy=true
ignoredPorts=18125
```

After saving, restart WSL:

```powershell
wsl --shutdown
```

### 2) Use the Zeroconf devcontainer definition

The `_zeroconf_.devcontainer.json` profile adds:

- `"runArgs": ["--network=host"]`
- forwarding/labeling for Home Assistant port `18125`

To use it, temporarily replace `.devcontainer.json` with the content of `_zeroconf_.devcontainer.json`, then rebuild/reopen the container.

### 3) add VS Code port settings

If port forwarding interferes with discovery tests in your environment, temporarily add this block to `.vscode/settings.json` while debugging Zeroconf:

```jsonc
"remote.autoForwardPorts": false,
"remote.portsAttributes": {
   "18125": {
      "onAutoForward": "ignore"
   }
},
```

Remove the block again when you finish Zeroconf debugging.

When done with autodiscovery debugging, switch back to the default `.devcontainer.json` profile.