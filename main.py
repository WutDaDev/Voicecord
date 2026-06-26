import asyncio
import json
import requests
import os
import random
from conversations import SCENARIOS

# Lấy cấu hình từ môi trường
TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")

TARGET_CHANNEL_NAME = "# 5 • 👥 Team Starry's Channel"
API = "https://discord.com/api/v10"

MEMBER_NAMES = ["Kikuri", "Nijika", "Ryo", "Kita", "PA-san", "Seika", "Hitori", "TeamStarry"]

# Hitori là nhân vật chính (index 6)
TALKER_INDEX = 6 
TOKEN_JOIN_DELAYS = [ (i * (i + 1) // 2) * 60 for i in range(8) ]

class TokenClient:
    def __init__(self, token, index, name, guild_id, channel_id):
        self.token = token
        self.name = name
        self.guild_id = guild_id
        self.channel_id = channel_id

    async def join_voice(self):
        try:
            requests.patch(f"{API}/channels/{self.channel_id}", 
                           headers={"Authorization": self.token}, 
                           json={"name": TARGET_CHANNEL_NAME})
        except: pass
        print(f"[*] {self.name} đã vào voice.")

    async def chat_loop(self):
        s_idx = 0
        while True:
            scenario = SCENARIOS[s_idx]
            for speaker, content in scenario:
                if speaker == self.name:
                    # Logic Typing thật: Tốc độ ~5 ký tự/giây + sai số ngẫu nhiên
                    typing_duration = len(content) / 5
                    typing_delay = typing_duration + random.uniform(1, 3)
                    
                    # 1. Gửi tín hiệu "Đang gõ..."
                    try:
                        requests.post(f"{API}/channels/{self.channel_id}/typing", 
                                      headers={"Authorization": self.token})
                    except: pass
                    
                    # 2. Đợi đúng thời gian "gõ"
                    await asyncio.sleep(typing_delay)
                    
                    # 3. Gửi tin nhắn
                    headers = {"Authorization": self.token, "Content-Type": "application/json"}
                    requests.post(f"{API}/channels/{self.channel_id}/messages", 
                                  headers=headers, json={"content": content})
                    
                    print(f"[{self.name}] Đã nhắn ({len(content)} ký tự) - Typing mất {typing_delay:.1f}s")
                    
                    # 4. Khoảng nghỉ sau khi nhắn để người khác kịp đọc
                    await asyncio.sleep(random.uniform(5, 12))
            
            # 5. Nghỉ giữa các kịch bản (80-100 phút)
            rest_time = random.randint(4800, 6000)
            print(f"[*] {self.name} hoàn thành kịch bản {s_idx+1}, nghỉ {rest_time//60} phút.")
            await asyncio.sleep(rest_time)
            
            s_idx = (s_idx + 1) % len(SCENARIOS)

async def run_token(token, i, gid, cid):
    client = TokenClient(token, i, MEMBER_NAMES[i], gid, cid)
    
    # Delay join lần đầu
    await asyncio.sleep(TOKEN_JOIN_DELAYS[i])
    
    await asyncio.gather(
        client.join_voice(),
        client.chat_loop()
    )

async def main():
    tokens = [t.strip() for t in TOKENS_RAW.split(",") if t.strip()]
    if not tokens: 
        print("[-] Không tìm thấy Token trong file .env!")
        return
    
    tasks = [asyncio.create_task(run_token(tokens[i], i, GUILD_ID, CHANNEL_ID)) 
             for i in range(min(len(tokens), len(MEMBER_NAMES)))]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
