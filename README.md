# KCMS switching matrix control software

Control, gateway, and monitoring tools for the KCMS switching matrix.

## Dependencies

Install the host-side Python packages:

```bash
python3 -m pip install -r requirements.txt
```

## Raspberry Pi Pico setup

Install MicroPython on the Pico using the
[official RPI_PICO2 image](https://micropython.org/download/RPI_PICO2/). Then
upload the files listed in `pico_micropython/UPLOADLIST`:

```bash
cd pico_micropython
bash upload.sh
mpremote reset
```

## WebSocket gateway

Connect the gateway computer to the Pico through UART. Edit `User`, `Group`,
`WorkingDirectory`, and `CONTROL_ALLOWED_NETWORKS` in
`websocket_server/ws-gateway.service_example`, then install and start the
service:

```bash
sudo cp websocket_server/ws-gateway.service_example \
    /etc/systemd/system/ws-gateway.service
sudo systemctl daemon-reload
sudo systemctl enable --now ws-gateway
```

View the gateway log with:

```bash
journalctl -u ws-gateway -f
```

The gateway uses separate ports:

- `ws://<gateway-host>:8765` for control
- `ws://<gateway-host>:8766` for read-only monitoring

## Command-line control

Run the control client from the repository directory:

```bash
python3 websocket_client/sw_control.py --help
```

## Web monitor

Create the local runtime configuration and start the monitor:

```bash
cd web_monitor
cp config.js_example config.js
python3 start_monitor.py
```

The default HTTP address is `127.0.0.1:8000`. To accept connections from other
computers:

```bash
python3 start_monitor.py --host 0.0.0.0 --port 8000
```

See `web_monitor/README.md` for configuration and URL override details.

## UART debugging

Use `pico_uart/pico_uart_client.py` to communicate with the Pico directly.
