import asyncio
import os
import aiohttp

# Configuration
TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")

MEMBER_NAMES = ["Kikuri", "Nijika", "Ryo", "Kita", "PA-san", "Seika", "Hitori", "TeamStarry"]

CHARACTER_GAMES = {
    "Kikuri": "Drinking Board Games with Hiroi",
    "Nijika": "Fat副社长 (Fat Vice President) Mobile Gacha",
    "Ryo": "Retro Fighting Games at the Arcade",
    "Kita": "Guitar Hero Online",
    "PA-san": "Mahjong (with the STARRY staff)",
    "Seika": "STARRY Management Simulator",
    "Hitori": "Stay in the Closet Simulator",
    "TeamStarry": "Bocchi the Rock! Gitadore / Arcade"
}

class TokenClient:
    def __init__(self, token, name, guild_id, channel_id):
        self.token = token
        self.name = name
        self.game = CHARACTER_GAMES.get(name, "Bocchi the Rock!")
        self.guild_id = guild_id
        self.channel_id = channel_id

    async def keep_alive(self):
        uri = "wss://gateway.discord.gg/?v=10&encoding=json"
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(uri) as ws:
                # 1. Handle initial connection
                hello_msg = await ws.receive_json()
                heartbeat_interval = hello_msg['d']['heartbeat_interval'] / 1000
                
                # 2. Define robust heartbeat
                async def heartbeat():
                    try:
                        while not ws.closed:
                            await asyncio.sleep(heartbeat_interval)
                            await ws.send_json({"op": 1, "d": None})
                    except Exception:
                        pass # Silently handle connection drops

                hb_task = asyncio.create_task(heartbeat())
                
                # 3. Identify & Set Presence
                await ws.send_json({
                    "op": 2,
                    "d": {
                        "token": self.token,
                        "properties": {"os": "windows", "browser": "chrome", "device": ""},
                        "presence": {
                            "activities": [{"name": self.game, "type": 0}],
                            "status": "idle",
                            "afk": True
                        }
                    }
                })
                
                # 4. Join Voice
                await ws.send_json({
                    "op": 4,
                    "d": {
                        "guild_id": self.guild_id,
                        "channel_id": self.channel_id,
                        "self_mute": True,
                        "self_deafen": True
                    }
                })
                print(f"[+] {self.name} is in voice as AFK, playing: {self.game}")
                
                # 5. Keep alive until closed
                try:
                    async for msg in ws:
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                finally:
                    hb_task.cancel()

async def run_token(token, i, gid, cid):
    name = MEMBER_NAMES[i] if i < len(MEMBER_NAMES) else f"User-{i}"
    client = TokenClient(token, name, gid, cid)
    await asyncio.sleep(i * 2) # Staggered connection
    await client.keep_alive()

async def main():
    tokens = [t.strip() for t in TOKENS_RAW.split(",") if t.strip()]
    tasks = [asyncio.create_task(run_token(tokens[i], i, GUILD_ID, CHANNEL_ID)) 
             for i in range(min(len(tokens), len(MEMBER_NAMES)))]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
