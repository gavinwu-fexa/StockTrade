# StockTrade Docker setup

Run `Start-StockTrade.cmd`. It starts Docker Desktop if needed, builds both
containers, opens the app, and leaves the containers running in the background.

- App on this PC: http://localhost:5173
- Backend on this PC: http://localhost:8000
- App on your local network: http://YOUR-WINDOWS-IP:5173

Use `Stop-StockTrade.cmd` to stop the app and `Logs-StockTrade.cmd` to inspect
startup or connection errors.

## IBKR Gateway

IB Gateway runs on Windows and the backend container reaches it through
`host.docker.internal`. In Gateway, select paper trading and enable socket API
clients. The expected Gateway paper port is `4002`. If the trusted-IP option is
enabled, permit Docker's local VM/network address, or disable the localhost-only
restriction so the container can connect.

The app starts in simulation mode. After Gateway is signed in and listening,
switch the app to paper mode. Live ports (`7496` and `4001`) remain read-only in
the application unless LIVE mode is explicitly unlocked.

## Live trading

LIVE mode connects to Gateway port `4001` (or TWS port `7496`) and can submit
real-money orders. The backend prints a new `LIVE TRADING UNLOCK CODE` each time
it starts. Run `Logs-StockTrade.cmd`, locate that code, then select LIVE in the
app and enter both the code and the requested confirmation phrase.

The resulting session token is kept only in browser memory. Reloading the page
requires entering the startup code again before manual live mutations are
accepted. Auto-trading resets to off on every mode change; once explicitly
enabled, it runs in the backend until you turn it off or switch modes. Switching
back to SIM or PAPER invalidates the live session token.

The backend image includes Python timezone data because IBKR historical bars can
use identifiers such as `US/Eastern`. Gateway error 162 stating that an API
scanner subscription was cancelled is expected when a temporary scanner request
finishes; it is not a connection failure by itself.

Remote access is exposed on all Windows network interfaces. Windows Firewall may
ask whether Docker may accept connections; allow only the network profiles you
intend to use. Do not expose ports 5173 or 8000 directly to the public internet.
