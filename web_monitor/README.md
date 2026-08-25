# Web monitor

Create the local runtime configuration and update `wsUrl` for the gateway:

```bash
cd web_monitor
cp config.js_example config.js
```

Start the monitor with the bundled Python server:

```bash
python3 start_monitor.py
```

The default address is `127.0.0.1:8000`. To accept connections from other
computers or select another port:

```bash
python3 start_monitor.py --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000> in a browser. The WebSocket URI can also be
overridden without editing `config.js`:

```text
http://127.0.0.1:8000/?ws=ws://swm:8766
```
