import asyncio
import os
import random
import aiohttp

# Get configuration from environment
TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")

MEMBER_NAMES = ["Kikuri", "Nijika", "Ryo", "Kita", "PA-san", "Seika", "Hitori", "TeamStarry"]

# Explicitly mapping canonical Bocchi the Rock! games/activities to each character
CHARACTER_GAMES = {
    "Kikuri": "Drinking Board Games with Hiroi",          # Her chaotic lifestyle
    "Nijika": "Fat副社长 (Fat Vice President) Mobile Gacha", # The mobile game she plays in Ch. 62
    "Ryo": "Retro Fighting Games at the Arcade",       # Her solo arcade runs
    "Kita": "Guitar Hero Online",                       # Grinding to catch up to Bocchi
    "PA-san": "Mahjong (with the STARRY staff)",          # Her notorious gaming hobby
    "Seika": "STARRY Management Simulator",               # Keeping the live house running
    "Hitori": "Stay in the Closet Simulator",              # Her ultimate comfort zone
    "TeamStarry": "BTR - Owner"     # General promotional/group game
}

TOKEN_JOIN_DELAYS = [ (i * (i + 1) // 2) * 5 for i in range(8) ] 

class TokenClient:
    def __init__(self, token, index, name, guild_id, channel_id):
        self.token = token
        self.index = index
        self.name = name
        # Look up the specific game assigned to this character name
        self.game = CHARACTER_GAMES.get(name, "Bocchi the Rock!")
        self.guild_id = guild_id
        self.channel_id = channel_id

    async def keep_alive(self):
        uri = "wss://gateway.discord.gg/?v=10&encoding=json"
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(uri) as ws:
                print(f"[*] {self.name} is connecting to Discord Gateway...")
                
                hello_msg = await ws.receive_json()
                heartbeat_interval = hello_msg['d']['heartbeat_interval'] / 1000
                
                async def heartbeat():
                    while True:
                        await asyncio.sleep(heartbeat_interval)
                        await ws.send_json({"op": 1, "d": None})
                
                hb_task = asyncio.create_task(heartbeat())
                
                identify_payload = {
                    "op": 2,
                    "d": {
                        "token": self.token,
                        "properties": {
                            "os": "windows",
                            "browser": "chrome",
                            "device": ""
                        },
                        "presence": {
                            "activities": [{
                                "name": self.game,
                                "type": 0  # Type 0 = "Playing"
                            }],
                            "status": "dnd",
                            "since": 0,
                            "afk": True
                        }
                    }
                }
                await ws.send_json(identify_payload)
                print(f"[+] {self.name} is now online and playing: \"{self.game}\"")
                
                voice_payload = {
                    "op": 4,
                    "d": {
                        "guild_id": self.guild_id,
                        "channel_id": self.channel_id,
                        "self_mute": True,
                        "self_deafen": True
                    }
                }
                await ws.send_json(voice_payload)
                print(f"[Voice] {self.name} joined voice channel (Muted & Deafened) -> AFK State Engaged.")
                
                try:
                    async for msg in ws:
                        pass 
                except asyncio.CancelledError:
                    hb_task.cancel()

async def run_token(token, i, gid, cid):
    # Pass the character name based on token array position
    member_name = MEMBER_NAMES[i] if i < len(MEMBER_NAMES) else f"Bot-{i}"
    client = TokenClient(token, i, member_name, gid, cid)
    
    await asyncio.sleep(TOKEN_JOIN_DELAYS[i])
    await client.keep_alive()

async def main():
    tokens = [t.strip() for t in TOKENS_RAW.split(",") if t.strip()]
    if not tokens: 
        print("[-] No tokens found in environment configuration!")
        return
    
    tasks = [asyncio.create_task(run_token(tokens[i], i, GUILD_ID, CHANNEL_ID)) 
             for i in range(min(len(tokens), len(MEMBER_NAMES)))]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
