import asyncio
import json
import requests
import websockets
import os

# Đọc token từ TOKEN env, cách nhau bằng dấu phẩy
TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")
STATUS = os.getenv("STATUS", "online")
SELF_MUTE = os.getenv("SELF_MUTE", "False").lower() in ("true", "1", "yes")
SELF_DEAF = os.getenv("SELF_DEAF", "False").lower() in ("true", "1", "yes")
JOIN_DELAY = int(os.getenv("JOIN_DELAY", "30"))  # Delay giữa các token (giây)

API = "https://discord.com/api/v10"

# Parse tokens từ chuỗi TOKEN (cách nhau bằng dấu phẩy)
def parse_tokens(raw):
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        print("Error: No tokens found in TOKEN environment variable!")
        exit()
    return tokens

if not GUILD_ID or not CHANNEL_ID:
    print("Error: Missing SERVER_ID or CHANNEL_ID environment variables!")
    exit()

async def heartbeat(ws, interval):
    while True:
        await asyncio.sleep(interval / 1000)
        await ws.send(json.dumps({"op": 1, "d": None}))

async def connect_token(token, guild_id, channel_id, status, self_mute, self_deaf, delay=0):
    # Delay trước khi join (nếu có)
    if delay > 0:
        print(f"  Waiting {delay}s before connecting...")
        await asyncio.sleep(delay)

    # Kiểm tra token
    res = requests.get(f"{API}/users/@me", headers={"Authorization": token})
    if res.status_code != 200:
        print(f"[!] Invalid token: {token[:25]}...")
        return
    user = res.json()
    print(f"[+] Logged in as {user['username']} ({user['id']})")

    uri = "wss://gateway.discord.gg/?v=10&encoding=json"

    async with websockets.connect(uri, max_size=None) as ws:
        hello = json.loads(await ws.recv())
        heartbeat_interval = hello["d"]["heartbeat_interval"]

        asyncio.create_task(heartbeat(ws, heartbeat_interval))

        # Identify
        await ws.send(json.dumps({
            "op": 2,
            "d": {
                "token": token,
                "properties": {
                    "$os": "windows",
                    "$browser": "chrome",
                    "$device": "pc"
                },
                "presence": {
                    "status": status,
                    "afk": False
                }
            }
        }))

        # Chờ READY
        while True:
            event = json.loads(await ws.recv())
            if event.get("t") == "READY":
                break

        # Join voice channel
        await ws.send(json.dumps({
            "op": 4,
            "d": {
                "guild_id": guild_id,
                "channel_id": channel_id,
                "self_mute": self_mute,
                "self_deaf": self_deaf
            }
        }))

        print(f"  -> Joined voice! (Mute: {self_mute}, Deaf: {self_deaf})")

        # Giữ kết nối
        while True:
            try:
                await ws.recv()
            except:
                print(f"[!] {user['username']} disconnected, reconnecting...")
                break

async def run_token(token, delay=0):
    while True:
        try:
            await connect_token(
                token=token,
                guild_id=GUILD_ID,
                channel_id=CHANNEL_ID,
                status=STATUS,
                self_mute=SELF_MUTE,
                self_deaf=SELF_DEAF,
                delay=delay
            )
        except Exception as e:
            print(f"[!] Error with token {token[:25]}...: {e}")
            await asyncio.sleep(5)

async def main():
    tokens = parse_tokens(TOKENS_RAW)
    print(f"[*] Loaded {len(tokens)} token(s)")
    print(f"[*] Guild: {GUILD_ID}")
    print(f"[*] Channel: {CHANNEL_ID}")
    print(f"[*] Join delay: {JOIN_DELAY}s between tokens")
    print()

    # Chạy từng token với delay 30s giữa các lần connect
    tasks = []
    for i, token in enumerate(tokens):
        delay = i * JOIN_DELAY  # Token đầu join ngay, token sau cách nhau 30s
        tasks.append(run_token(token, delay=delay))
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
