# Web monitor

Create the local runtime configuration and update `wsUrl` for the gateway:

```bash
cd web_monitor
cp config.js_example config.js
```

Serve the files from the `web_monitor` directory:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Open <http://127.0.0.1:8000> in a browser. The WebSocket URI can also be
overridden without editing `config.js`:

```text
http://127.0.0.1:8000/?ws=ws://swm:8766
```
