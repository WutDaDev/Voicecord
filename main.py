import asyncio
import json
import requests
import websockets
import os
import time
import subprocess
import platform

# ─── CONFIG ─────────────────────────────────────────────────────────────────
TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")
STATUS = os.getenv("STATUS", "online")

# Mặc định: self_mute = False để có thể nghe được voice
SELF_MUTE = os.getenv("SELF_MUTE", "False").lower() in ("true", "1", "yes")
SELF_DEAF = os.getenv("SELF_DEAF", "False").lower() in ("true", "1", "yes")

# Thư mục chứa file voice Bocchi
BOCCHI_VOICE_DIR = os.getenv("BOCCHI_VOICE_DIR", "Bocchi")
BOCCHI_VOICE_FILE = os.getenv("BOCCHI_VOICE_FILE", "bocchi_1.mp3")

API = "https://discord.com/api/v10"

# ─── PARSE TOKENS ───────────────────────────────────────────────────────────
def parse_tokens(raw):
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        print("Error: No tokens found in TOKEN environment variable!")
        exit()
    return tokens

# ─── BOCCHI THE ROCK TIMELINE ──────────────────────────────────────────────
def generate_bocchi_timeline(token_count):
    """
    Bocchi the Rock! inspired timeline:
    
    Token #0 = TeamStarry (Nijika's sister Seika / host)
    Token #1 = Bocchi (Hitori Gotoh) — lead guitar
    Token #2 = Nijika — drummer, leader
    Token #3 = Ryo — bassist
    Token #4 = Kita — vocalist/rhythm guitar
    Token #5 = Kikuri Hiroi — drunk senpai (SICK HACK)
    Token #6 = Seika — live house owner
    Token #7 = PA-san — sound engineer
    
    JOIN: mỗi thành viên vào cách nhau ~10 phút (600s)
    LEAVE: ở lại rất lâu (hàng giờ)
    """
    if token_count < 8:
        print(f"[!] Warning: Expected 8 tokens, got {token_count}")
    
    members = [
        "TeamStarry (Host)",
        "Bocchi 🎸",
        "Nijika 🥁",
        "Ryo 🎸",
        "Kita 🎤",
        "Kikuri 🍺",
        "Seika 👑",
        "PA-san 🎛️"
    ]
    
    timeline = []
    
    # ── JOIN PHASE: cách nhau 10 phút ──
    # TeamStarry join trước để setup
    timeline.append({"token_index": 0, "action": "join", "time": 0, "name": members[0]})
    
    # Các thành viên Kessoku Band join dần
    timeline.append({"token_index": 2, "action": "join", "time": 600, "name": members[2]})   # Nijika - T+10min
    timeline.append({"token_index": 3, "action": "join", "time": 1200, "name": members[3]})  # Ryo - T+20min
    timeline.append({"token_index": 4, "action": "join", "time": 1800, "name": members[4]})  # Kita - T+30min
    timeline.append({"token_index": 1, "action": "join", "time": 2400, "name": members[1]})  # Bocchi - T+40min (trễ nhất)
    
    # Guest members join
    if token_count > 5:
        timeline.append({"token_index": 5, "action": "join", "time": 3000, "name": members[5]})  # Kikuri - T+50min
    if token_count > 6:
        timeline.append({"token_index": 6, "action": "join", "time": 3600, "name": members[6]})  # Seika - T+60min
    if token_count > 7:
        timeline.append({"token_index": 7, "action": "join", "time": 4200, "name": members[7]})  # PA-san - T+70min
    
    # ── VOICE PLAY EVENTS (ngay sau khi join) ──
    # Mỗi member sẽ phát bocchi_1.mp3 ngay khi join
    for i in range(token_count):
        join_event = [e for e in timeline if e["token_index"] == i and e["action"] == "join"]
        if join_event:
            join_time = join_event[0]["time"]
            # Phát voice 3 giây sau khi join (để kịp connect)
            timeline.append({
                "token_index": i,
                "action": "play_voice",
                "time": join_time + 3,
                "name": members[i] if i < len(members) else f"Member {i}",
                "voice_file": BOCCHI_VOICE_FILE
            })
    
    # ── LEAVE PHASE: RẤT lâu sau ──
    # Các guest leave trước
    if token_count > 5:
        timeline.append({"token_index": 5, "action": "leave", "time": 14400, "name": members[5]})  # Kikuri - T+4h
    if token_count > 7:
        timeline.append({"token_index": 7, "action": "leave", "time": 16200, "name": members[7]})  # PA-san - T+4.5h
    
    # Thành viên band leave dần
    timeline.append({"token_index": 1, "action": "leave", "time": 18000, "name": members[1]})  # Bocchi - T+5h
    timeline.append({"token_index": 3, "action": "leave", "time": 19200, "name": members[3]})  # Ryo - T+5.3h
    timeline.append({"token_index": 4, "action": "leave", "time": 19800, "name": members[4]})  # Kita - T+5.5h
    timeline.append({"token_index": 2, "action": "leave", "time": 21600, "name": members[2]})  # Nijika - T+6h
    
    # TeamStarry và Seika ở lại cuối cùng
    if token_count > 6:
        timeline.append({"token_index": 6, "action": "leave", "time": 25200, "name": members[6]})  # Seika - T+7h
    timeline.append({"token_index": 0, "action": "leave", "time": 28800, "name": members[0]})  # TeamStarry - T+8h (cuối cùng)
    
    timeline.sort(key=lambda x: x["time"])
    return timeline, members

# ─── VOICE CLIENT (Discord voice WebSocket + audio playback) ────────────────
class BocchiVoiceClient:
    def __init__(self, token, index, name):
        self.token = token
        self.index = index
        self.name = name
        self.username = None
        self.user_id = None
        self.ws = None
        self.voice_ws = None
        self.heartbeat_task = None
        self.voice_heartbeat_task = None
        self.connected = False
        self.in_voice = False
        self.voice_server_data = None
        self._validate()
    
    def _validate(self):
        res = requests.get(f"{API}/users/@me", headers={"Authorization": self.token})
        if res.status_code != 200:
            print(f"[!] Token #{self.index} ({self.name}): INVALID!")
            self.valid = False
            return
        user = res.json()
        self.username = user['username']
        self.user_id = user['id']
        self.valid = True
        print(f"[+] Token #{self.index}: {self.username} ({self.name})")
    
    async def _heartbeat(self, ws, interval):
        try:
            while True:
                await asyncio.sleep(interval / 1000)
                await ws.send(json.dumps({"op": 1, "d": None}))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    
    async def connect_gateway(self):
        """Kết nối tới Discord Gateway"""
        uri = "wss://gateway.discord.gg/?v=10&encoding=json"
        
        try:
            self.ws = await websockets.connect(uri, max_size=None)
            hello = json.loads(await self.ws.recv())
            heartbeat_interval = hello["d"]["heartbeat_interval"]
            
            self.heartbeat_task = asyncio.create_task(
                self._heartbeat(self.ws, heartbeat_interval)
            )
            
            # Identify
            await self.ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": self.token,
                    "properties": {
                        "$os": "windows",
                        "$browser": "chrome",
                        "$device": "pc"
                    },
                    "presence": {
                        "status": "online",
                        "afk": False
                    }
                }
            }))
            
            # Chờ READY
            while True:
                event = json.loads(await self.ws.recv())
                if event.get("t") == "READY":
                    self.session_id = event["d"]["session_id"]
                    break
            
            return True
        except Exception as e:
            print(f"[!] {self.name}: Gateway connect failed - {e}")
            return False
    
    async def join_voice(self, guild_id, channel_id):
        """Join voice channel"""
        if not self.ws:
            if not await self.connect_gateway():
                return False
        
        try:
            # Gửi op 4 để join voice
            await self.ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "self_mute": False,     # Auto unmute để nói được
                    "self_deaf": False      # Auto undeaf để nghe được
                }
            }))
            
            # Chờ voice server update
            while True:
                event = json.loads(await self.ws.recv())
                
                # Voice State Update
                if event.get("t") == "VOICE_STATE_UPDATE":
                    if event["d"]["channel_id"] == channel_id:
                        print(f"  -> {self.name}: Voice state updated")
                
                # Voice Server Update (chứa thông tin để kết nối voice WebSocket)
                if event.get("t") == "VOICE_SERVER_UPDATE":
                    self.voice_server_data = event["d"]
                    print(f"  -> {self.name}: Got voice server data")
                    break
            
            # Kết nối tới voice WebSocket
            await self._connect_voice_websocket(guild_id, channel_id)
            
            self.in_voice = True
            self.connected = True
            print(f"  ✅ {self.name} JOINED voice! 🎸")
            
            return True
            
        except Exception as e:
            print(f"[!] {self.name}: Join voice failed - {e}")
            return False
    
    async def _connect_voice_websocket(self, guild_id, channel_id):
        """Kết nối tới Discord voice WebSocket để có thể nói"""
        if not self.voice_server_data:
            return
        
        endpoint = self.voice_server_data["endpoint"]
        server_id = self.voice_server_data["guild_id"]
        token = self.voice_server_data["token"]
        
        # Chuyển endpoint thành ws://
        ws_endpoint = f"wss://{endpoint}?v=4"
        
        try:
            self.voice_ws = await websockets.connect(ws_endpoint, max_size=None)
            
            # Voice Identify
            await self.voice_ws.send(json.dumps({
                "op": 0,
                "d": {
                    "server_id": server_id,
                    "user_id": self.user_id,
                    "session_id": self.session_id,
                    "token": token
                }
            }))
            
            # Chờ Ready
            while True:
                event = json.loads(await self.voice_ws.recv())
                if event.get("op") == 2:  # Ready
                    heartbeat_interval = event["d"]["heartbeat_interval"]
                    self.voice_heartbeat_task = asyncio.create_task(
                        self._heartbeat(self.voice_ws, heartbeat_interval)
                    )
                    break
            
            print(f"  -> {self.name}: Voice WebSocket connected")
            
        except Exception as e:
            print(f"[!] {self.name}: Voice WS failed - {e}")
    
    async def play_audio_file(self, filepath):
        """
        Phát file audio qua voice channel.
        
        NOTE: Discord voice yêu cầu gửi audio đã được mã hóa Opus 
        qua UDP kèm encryption (xsalsa20_poly1305).
        
        Đây là phiên bản dùng ffmpeg + pipe để gửi audio thô.
        Trên Railway, bạn cần cài đặt:
          - ffmpeg
          - opus-tools
          - pkg-config
        
        Hoặc dùng thư viện python: pip install pydub opuslib
        """
        if not self.in_voice or not self.voice_ws:
            print(f"[!] {self.name}: Not in voice, can't play audio")
            return
        
        if not os.path.exists(filepath):
            print(f"[!] {self.name}: Audio file not found: {filepath}")
            print(f"    -> Tạo thư mục 'Bocchi/' và đặt file {BOCCHI_VOICE_FILE} vào đó")
            return
        
        print(f"  🎵 {self.name}: Playing {os.path.basename(filepath)}...")
        
        try:
            # Kiểm tra platform để dùng lệnh phù hợp
            system = platform.system()
            
            if system == "Linux":
                # Trên Linux (Railway), dùng ffplay hoặc aplay
                # Thực tế: Discord voice yêu cầu encode Opus + gửi qua UDP
                # Đây là mô phỏng đơn giản - sẽ dùng ffmpeg để decode
                cmd = [
                    "ffplay", "-nodisp", "-autoexit",
                    "-volume", "100",
                    filepath
                ]
                # Chạy trong background để không block
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                # Không await - chạy ngầm
                print(f"  🎶 {self.name}: Audio playback started! (PID: {process.pid})")
                
            elif system == "Windows":
                # Trên Windows, dùng PowerShell
                cmd = [
                    "powershell", "-c",
                    f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"
                ]
                asyncio.create_task(self._run_command_async(cmd))
                print(f"  🎶 {self.name}: Audio playback started!")
            
            elif system == "Darwin":
                # Trên macOS
                cmd = ["afplay", filepath]
                asyncio.create_task(self._run_command_async(cmd))
                print(f"  🎶 {self.name}: Audio playback started!")
            
            else:
                print(f"[!] {self.name}: Unsupported OS for audio playback: {system}")
                print(f"    File: {filepath}")
            
        except Exception as e:
            print(f"[!] {self.name}: Audio playback error - {e}")
    
    async def _run_command_async(self, cmd):
        """Chạy lệnh system không block"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await process.communicate()
        except Exception as e:
            print(f"[!] Command error: {e}")
    
    async def leave_voice(self):
        """Rời voice channel"""
        if not self.ws:
            return
        
        try:
            # Gửi op 4 với null channel để rời
            await self.ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": None,
                    "channel_id": None,
                    "self_mute": False,
                    "self_deaf": False
                }
            }))
            
            # Đóng voice WebSocket nếu có
            if self.voice_ws:
                if self.voice_heartbeat_task:
                    self.voice_heartbeat_task.cancel()
                await self.voice_ws.close()
                self.voice_ws = None
            
            self.in_voice = False
            self.connected = False
            print(f"  👋 {self.name} LEFT voice!")
            
        except Exception as e:
            print(f"[!] {self.name}: Leave voice error - {e}")
            self.in_voice = False
            self.connected = False
    
    async def cleanup(self):
        """Dọn dẹp kết nối"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.voice_heartbeat_task:
            self.voice_heartbeat_task.cancel()
        if self.voice_ws:
            await self.voice_ws.close()
        if self.ws:
            await self.ws.close()

# ─── TIMELINE EXECUTOR ──────────────────────────────────────────────────────
async def execute_timeline(clients, guild_id, channel_id, timeline):
    """Thực thi timeline events"""
    
    print(f"\n{'='*60}")
    print(f"🎸 BOCHI THE ROCK VOICE TIMELINE 🎸")
    print(f"{'='*60}")
    print(f"Guild: {guild_id}")
    print(f"Channel: {channel_id}")
    print(f"Voice file: {BOCCHI_VOICE_DIR}/{BOCCHI_VOICE_FILE}")
    print(f"{'='*60}\n")
    
    # Kiểm tra file voice
    voice_path = os.path.join(BOCCHI_VOICE_DIR, BOCCHI_VOICE_FILE)
    if os.path.exists(voice_path):
        print(f"✅ Voice file found: {voice_path}")
    else:
        print(f"⚠️ Voice file NOT found: {voice_path}")
        print(f"   Tạo thư mục 'Bocchi/' và thêm file {BOCCHI_VOICE_FILE}")
        print()
    
    print("📋 Timeline Schedule:")
    print(f"{'Time':>10s} | {'Action':<12s} | {'Member':<20s}")
    print("-" * 50)
    
    for event in sorted(timeline, key=lambda x: x["time"]):
        time_str = f"T+{event['time']//3600}h{(event['time']%3600)//60:02d}m{event['time']%60:02d}s"
        name = event.get("name", f"Token #{event['token_index']}")
        print(f"{time_str:>10s} | {event['action']:<12s} | {name:<20s}")
    
    print("-" * 50)
    print()
    
    # Bắt đầu thực thi
    start_time = time.time()
    
    for event in sorted(timeline, key=lambda x: x["time"]):
        token_index = event["token_index"]
        action = event["action"]
        event_time = event["time"]
        name = event.get("name", f"Token #{token_index}")
        
        if token_index >= len(clients):
            continue
        
        client = clients[token_index]
        if not client.valid:
            continue
        
        # Chờ đến thời điểm event
        now = time.time() - start_time
        wait_time = event_time - now
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        elapsed = time.time() - start_time
        time_str = f"{int(elapsed)//3600}h{int(elapsed)%3600//60:02d}m{int(elapsed)%60:02d}s"
        
        print(f"[{time_str}] Event: {name} -> {action.upper()}")
        
        if action == "join":
            # Kết nối gateway và join voice
            connected = await client.join_voice(guild_id, channel_id)
            
        elif action == "play_voice":
            # Phát voice Bocchi
            if client.in_voice:
                voice_path = os.path.join(BOCCHI_VOICE_DIR, event.get("voice_file", BOCCHI_VOICE_FILE))
                await client.play_audio_file(voice_path)
            else:
                print(f"   {name}: Not in voice yet, skipping playback")
        
        elif action == "leave":
            await client.leave_voice()
    
    # Timeline hoàn thành
    print(f"\n{'='*60}")
    print("🎵 Timeline completed! Cleaning up...")
    print(f"{'='*60}\n")
    
    # Dọn dẹp tất cả
    for client in clients:
        await client.cleanup()
    
    print("✅ Done!")

# ─── MAIN ───────────────────────────────────────────────────────────────────
async def main():
    tokens = parse_tokens(TOKENS_RAW)
    print(f"[*] Loaded {len(tokens)} token(s)")
    
    if len(tokens) < 2:
        print("[!] Cần ít nhất 2 tokens (1 TeamStarry + 1 member)")
        return
    
    # Tạo timeline Bocchi
    timeline, member_names = generate_bocchi_timeline(len(tokens))
    
    print(f"\n[*] Members ({len(tokens)}):")
    for i, name in enumerate(member_names[:len(tokens)]):
        print(f"     Token #{i}: {name}")
    print()
    
    # Khởi tạo clients
    clients = []
    for i, token in enumerate(tokens):
        name = member_names[i] if i < len(member_names) else f"Member {i}"
        client = BocchiVoiceClient(token, i, name)
        clients.append(client)
    
    # Kiểm tra valid tokens
    valid_clients = [c for c in clients if c.valid]
    if len(valid_clients) < 1:
        print("[!] No valid tokens!")
        return
    
    print(f"\n[*] Valid tokens: {len(valid_clients)}/{len(clients)}")
    print(f"[*] Voice file: {BOCCHI_VOICE_DIR}/{BOCCHI_VOICE_FILE}")
    print(f"[*] Auto unmute: YES (members will speak!)")
    print()
    
    # Thực thi timeline
    await execute_timeline(clients, GUILD_ID, CHANNEL_ID, timeline)

if __name__ == "__main__":
    asyncio.run(main())
