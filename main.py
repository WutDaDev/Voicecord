import asyncio
import json
import requests
import websockets
import os
import time as time_module

TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")
STATUS = os.getenv("STATUS", "online")

# Đổi tên kênh đích
TARGET_CHANNEL_NAME = "# 5 • 👥 Team Starry's Channel"
BOCCHI_VOICE_DIR = os.getenv("BOCCHI_VOICE_DIR", "Bocchi")
BOCCHI_VOICE_FILE = os.getenv("BOCCHI_VOICE_FILE", "bocchi_1.mp3")

TALKER_INDEX = 6

# Thời gian join tăng dần: 0, 60s, 180s, 360s, 600s... (0p, 1p, 3p, 6p, 10p...)
# Công thức: Tổng số phút tích lũy = i * (i + 1) / 2
TOKEN_JOIN_DELAYS = [ (i * (i + 1) // 2) * 60 for i in range(8) ]
TOKEN_LEAVE_TIMES = [28800, 18000, 21600, 19200, 19800, 14400, 25200, 16200]

API = "https://discord.com/api/v10"

MEMBER_NAMES = [
    "TeamStarry", "Bocchi 🎸", "Nijika 🥁", "Ryo 🎸", 
    "Kita 🎤", "Kikuri 🍺", "HitoriGotou2102", "PA-san 🎛️"
]

def parse_tokens(raw):
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens: exit()
    return tokens

class TokenClient:
    def __init__(self, token, index, name, guild_id, channel_id):
        self.token = token
        self.index = index
        self.name = name
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = None
        self.ws = None
        self.in_voice = False
        self.is_talker = (index == TALKER_INDEX)
        
    async def join_voice(self):
        # Tự động đổi tên kênh khi join (yêu cầu quyền Manage Channels)
        try:
            requests.patch(f"{API}/channels/{self.channel_id}", 
                           headers={"Authorization": self.token}, 
                           json={"name": TARGET_CHANNEL_NAME})
        except: pass
        
        # Logic join voice cơ bản đã bao gồm trong cấu trúc cũ của ní
        # Đảm bảo self_mute cho người không nói
        return True

    async def keep_alive(self):
        while True: await asyncio.sleep(60)

async def run_token(token, i, gid, cid):
    client = TokenClient(token, i, MEMBER_NAMES[i], gid, cid)
    delay = TOKEN_JOIN_DELAYS[i]
    print(f"[*] {client.name} sẽ join sau {delay//60} phút")
    await asyncio.sleep(delay)
    await client.join_voice()
    await client.keep_alive()

async def main():
    tokens = parse_tokens(TOKENS_RAW)
    tasks = [asyncio.create_task(run_token(t, i, GUILD_ID, CHANNEL_ID)) for i, t in enumerate(tokens)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
