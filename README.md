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

The gateway runs on a Raspberry Pi 3 and communicates with the Pico through
UART0 at 115200 baud. Connect the UART signals as follows:

| Raspberry Pi 3 | Direction | Raspberry Pi Pico |
| --- | --- | --- |
| Physical pin 8 (`UART0_TXD`, GPIO14) | → | Physical pin 2 (`UART0_RX`, GP1) |
| Physical pin 10 (`UART0_RXD`, GPIO15) | ← | Physical pin 1 (`UART0_TX`, GP0) |
| Physical pin 14 (`GND`) | ↔ | Physical pin 3 (`GND`) |

The TX and RX signals must be crossed as shown above, and both boards must share
a common ground. Other GND pins may be used instead of the example pins in the
table. The UART pins use 3.3 V logic; do not apply 5 V to them.

The gateway opens the Raspberry Pi UART as `/dev/serial0`. Enable the serial
hardware and disable the serial login shell in `raspi-config` before starting
the service.

Edit `User`, `Group`, `WorkingDirectory`, and `CONTROL_ALLOWED_NETWORKS` in
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

Run the control client from the repository directory. The default gateway URI
is `ws://127.0.0.1:8765`; use `--uri` when the gateway is on another host:

```bash
python3 websocket_client/sw_control.py --help
python3 websocket_client/sw_control.py --uri ws://swm:8765 ping
```

The client accepts linear pin numbers from 0 to 255 and matrix labels from
`A00` to `P15`. It also accepts comma-separated pins, inclusive numeric ranges,
complete rows, and complete columns:

```text
17
A00
3,5,7
10-20
row A
col 9
```

Turn on one or more channels with `on`:

```bash
python3 websocket_client/sw_control.py --uri ws://swm:8765 on A00
python3 websocket_client/sw_control.py --uri ws://swm:8765 on A00 D09 57
python3 websocket_client/sw_control.py --uri ws://swm:8765 on row A
python3 websocket_client/sw_control.py --uri ws://swm:8765 on col 9
```

Turn off selected channels or every channel with `off` and `alloff`:

```bash
python3 websocket_client/sw_control.py --uri ws://swm:8765 off A00 D09
python3 websocket_client/sw_control.py --uri ws://swm:8765 off all
python3 websocket_client/sw_control.py --uri ws://swm:8765 alloff
```

Use `route` for exclusive selection. It turns off every channel before turning
on exactly one target:

```bash
python3 websocket_client/sw_control.py --uri ws://swm:8765 route A00
```

Query the complete matrix, active channels, an individual PCF8575, or PCF8575
presence status with:

```bash
python3 websocket_client/sw_control.py --uri ws://swm:8765 pinstat
python3 websocket_client/sw_control.py --uri ws://swm:8765 pinstat active
python3 websocket_client/sw_control.py --uri ws://swm:8765 pinstat 0
python3 websocket_client/sw_control.py --uri ws://swm:8765 pcfstat
python3 websocket_client/sw_control.py --uri ws://swm:8765 pcfstat 0
```

The remaining diagnostic commands are:

```bash
# Print the matrix label-to-pin map through the monitor port.
python3 websocket_client/sw_control.py --uri ws://swm:8765 map

# Poll the matrix through the control port every second.
python3 websocket_client/sw_control.py --uri ws://swm:8765 watch --interval 1

# Subscribe to event-driven updates through the monitor port.
python3 websocket_client/sw_control.py --uri ws://swm:8765 follow
```

`watch` requires access to the restricted control port. `follow` and `map`
automatically use the read-only monitor port at 8766.

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

When binding to `0.0.0.0`, use a firewall to allow TCP port 8000 only from
trusted networks. Do not expose this development server directly to the public
internet because it does not provide authentication or TLS.

See `web_monitor/README.md` for configuration and URL override details.

## Direct UART debugging

These tools bypass the WebSocket gateway service and communicate with the Pico
directly over UART. They are normally run on the Raspberry Pi 3 gateway host,
where the Pico is available as `/dev/serial0`.

The gateway service normally owns this serial port. Stop the service before
running a direct UART diagnostic so that two processes do not access the Pico
at the same time:

```bash
sudo systemctl stop ws-gateway
cd pico_uart
python3 ping.py
python3 pinstat.py ALL
```

Use `sw_uart.py` for interactive control through the UART connection:

```bash
python3 sw_uart.py ping
python3 sw_uart.py on A00
python3 sw_uart.py pinstat
python3 sw_uart.py off all
```

Run the firmware test suite when a complete protocol check is needed. The test
changes switch states, so disconnect sensitive equipment or verify that the
connected hardware is in a safe state first:

```bash
python3 test_full.py
```

After debugging, restart the gateway service:

```bash
sudo systemctl start ws-gateway
```

## Acknowledgements

Development of this project was assisted by OpenAI Codex.
