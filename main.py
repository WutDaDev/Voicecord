import asyncio
import json
import requests
import websockets
import os
import time

# ─── CONFIG ─────────────────────────────────────────────────────────────────
TOKENS_RAW = os.getenv("TOKEN", "")
GUILD_ID = os.getenv("SERVER_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")
STATUS = os.getenv("STATUS", "online")

# Tự unmute khi join
SELF_MUTE = False
SELF_DEAF = False

BOCCHI_VOICE_DIR = os.getenv("BOCCHI_VOICE_DIR", "Bocchi")
BOCCHI_VOICE_FILE = os.getenv("BOCCHI_VOICE_FILE", "bocchi_1.mp3")

# Mỗi token có delay riêng khi join (giây)
TOKEN_JOIN_DELAYS = [0, 600, 1200, 1800, 2400, 3000, 3600, 4200]
# Thời gian leave (giây)
TOKEN_LEAVE_TIMES = [28800, 18000, 21600, 19200, 19800, 14400, 25200, 16200]

API = "https://discord.com/api/v10"

# ─── PARSE TOKENS ───────────────────────────────────────────────────────────
def parse_tokens(raw):
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        print("Error: No tokens found in TOKEN environment variable!")
        exit()
    return tokens

# ─── TOKEN MANAGER ──────────────────────────────────────────────────────────
class TokenManager:
    def __init__(self, token, index, name, guild_id, channel_id):
        self.token = token
        self.index = index
        self.name = name
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.username = None
        self.user_id = None
        self.ws = None
        self.heartbeat_task = None
        self.in_voice = False
        self.valid = False
        self._validate()
    
    def _validate(self):
        try:
            res = requests.get(f"{API}/users/@me", headers={"Authorization": self.token})
            if res.status_code != 200:
                print(f"[!] Token #{self.index} ({self.name}): INVALID!")
                return
            user = res.json()
            self.username = user['username']
            self.user_id = user['id']
            self.valid = True
            print(f"[+] Token #{self.index}: {self.username} ({self.name})")
        except Exception as e:
            print(f"[!] Token #{self.index}: Validation error - {e}")
    
    async def _heartbeat(self, interval):
        try:
            while True:
                await asyncio.sleep(interval / 1000)
                if self.ws:
                    await self.ws.send(json.dumps({"op": 1, "d": None}))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    
    async def connect_gateway(self):
        """Kết nối tới Discord Gateway (chỉ gateway, KHÔNG voice WS)"""
        if self.ws:
            return True
            
        uri = "wss://gateway.discord.gg/?v=10&encoding=json"
        
        try:
            self.ws = await websockets.connect(uri, max_size=None)
            hello = json.loads(await self.ws.recv())
            heartbeat_interval = hello["d"]["heartbeat_interval"]
            
            self.heartbeat_task = asyncio.create_task(
                self._heartbeat(heartbeat_interval)
            )
            
            # Identify
            await self.ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": self.token,
                    "properties": {
                        "$os": "linux",
                        "$browser": "chrome",
                        "$device": "pc"
                    },
                    "presence": {
                        "status": STATUS,
                        "afk": False
                    }
                }
            }))
            
            # Chờ READY
            while True:
                msg = await self.ws.recv()
                event = json.loads(msg)
                if event.get("t") == "READY":
                    self.session_id = event["d"]["session_id"]
                    break
            
            return True
            
        except Exception as e:
            print(f"[!] {self.name}: Gateway connect failed - {e}")
            return False
    
    async def join_voice(self):
        """Join voice channel - chỉ gửi op 4, KHÔNG cần voice WS"""
        if not self.ws and not await self.connect_gateway():
            return False
        
        try:
            # Gửi op 4 để join voice (Discord tự xử lý phần còn lại)
            await self.ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": self.guild_id,
                    "channel_id": self.channel_id,
                    "self_mute": False,     # Auto unmute
                    "self_deaf": False      # Auto undeaf
                }
            }))
            
            # Đọc vài event để xác nhận voice state
            timeout = time.time() + 10  # 10s timeout
            joined = False
            
            while time.time() < timeout:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=2)
                    event = json.loads(msg)
                    
                    if event.get("t") == "VOICE_STATE_UPDATE":
                        d = event["d"]
                        if d.get("channel_id") == self.channel_id and d.get("user_id") == self.user_id:
                            joined = True
                            break
                except asyncio.TimeoutError:
                    break
                except Exception:
                    break
            
            self.in_voice = True
            status = "UNMUTED" if not SELF_MUTE else "MUTED"
            print(f"  ✅ {self.name} JOINED voice! 🎸 ({status})")
            
            # Phát thông báo voice (giả lập - chỉ log)
            await self._play_voice_notification()
            
            return True
            
        except Exception as e:
            print(f"[!] {self.name}: Join voice failed - {e}")
            return False
    
    async def _play_voice_notification(self):
        """
        Phát file voice Bocchi.
        
        Trên Railway/server: không có sound card, chỉ log.
        Trên máy local: dùng ffplay nếu có.
        """
        voice_path = os.path.join(BOCCHI_VOICE_DIR, BOCCHI_VOICE_FILE)
        
        if not os.path.exists(voice_path):
            print(f"  🎵 {self.name}: Voice file not found: {voice_path}")
            print(f"     (Tạo thư mục 'Bocchi/' và thêm file {BOCCHI_VOICE_FILE})")
            return
        
        print(f"  🎵 {self.name}: Playing '{BOCCHI_VOICE_FILE}'...")
        
        try:
            # Thử dùng ffplay (local), nếu không có thì log
            import subprocess
            import shutil
            
            if shutil.which("ffplay"):
                # Chạy background, không block
                subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", voice_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"     🎶 Audio playing via ffplay!")
            else:
                print(f"     📄 File ready: {voice_path} ({os.path.getsize(voice_path)} bytes)")
                print(f"     💡 Install ffmpeg locally to hear audio: apt install ffmpeg")
                
        except Exception as e:
            print(f"     ⚠️ Audio play error (non-critical): {e}")
    
    async def leave_voice(self):
        """Rời voice channel"""
        if not self.ws:
            return
        
        try:
            # Gửi op 4 với null channel
            await self.ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": None,
                    "channel_id": None,
                    "self_mute": False,
                    "self_deaf": False
                }
            }))
            
            self.in_voice = False
            print(f"  👋 {self.name} LEFT voice!")
            
        except Exception as e:
            print(f"[!] {self.name}: Leave voice error - {e}")
    
    async def keep_alive(self):
        """Giữ kết nối cho đến khi có lệnh leave"""
        try:
            while self.ws and self.in_voice:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=30)
                    # Xử lý event nếu cần
                    event = json.loads(msg)
                    if event.get("op") == 9:  # Invalid session
                        print(f"[!] {self.name}: Invalid session, reconnecting...")
                        break
                except asyncio.TimeoutError:
                    # Timeout là bình thường, heartbeat vẫn chạy
                    pass
        except Exception as e:
            print(f"[!] {self.name}: Keep alive error - {e}")
        finally:
            if self.in_voice:
                print(f"[!] {self.name}: Disconnected unexpectedly")
    
    async def cleanup(self):
        """Dọn dẹp"""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.ws:
            await self.ws.close()
            self.ws = None

# ─── MEMBER CONFIG ──────────────────────────────────────────────────────────
MEMBER_NAMES = [
    "TeamStarry (Host)",  # Token #0
    "Bocchi 🎸",          # Token #1
    "Nijika 🥁",          # Token #2
    "Ryo 🎸",             # Token #3
    "Kita 🎤",            # Token #4
    "Kikuri 🍺",          # Token #5
    "Seika 👑",           # Token #6
    "PA-san 🎛️"           # Token #7
]

# ─── RUN SINGLE TOKEN ──────────────────────────────────────────────────────
async def run_token_lifecycle(token, index, guild_id, channel_id):
    """Quản lý vòng đời của 1 token (join -> ở lại -> leave)"""
    
    name = MEMBER_NAMES[index] if index < len(MEMBER_NAMES) else f"Token #{index}"
    join_delay = TOKEN_JOIN_DELAYS[index] if index < len(TOKEN_JOIN_DELAYS) else (index * 600)
    leave_time = TOKEN_LEAVE_TIMES[index] if index < len(TOKEN_LEAVE_TIMES) else (28800)
    
    manager = TokenManager(token, index, name, guild_id, channel_id)
    
    if not manager.valid:
        return
    
    # Đợi đến lúc join
    if join_delay > 0:
        print(f"  ⏳ {name}: Will join in T+{join_delay//3600}h{(join_delay%3600)//60:02d}m{join_delay%60:02d}s")
        await asyncio.sleep(join_delay)
    
    # Connect gateway và join voice
    connected = await manager.join_voice()
    if not connected:
        print(f"[!] {name}: Failed to join voice, retrying in 10s...")
        await asyncio.sleep(10)
        connected = await manager.join_voice()
        if not connected:
            print(f"[!] {name}: Giving up")
            return
    
    # Tính thời gian cần ở lại
    import time as time_module
    start_time = time_module.time()
    remaining = leave_time - join_delay
    
    if remaining > 0:
        print(f"  💤 {name}: Staying for {remaining//3600}h{(remaining%3600)//60:02d}m")
        
        # Chia nhỏ thời gian chờ để tránh bị timeout
        # Vừa keep alive vừa đợi
        try:
            await asyncio.wait_for(
                manager.keep_alive(),
                timeout=remaining
            )
        except asyncio.TimeoutError:
            # Hết thời gian => leave
            pass
        except Exception as e:
            print(f"[!] {name}: Error during stay - {e}")
    else:
        # Nếu join trễ hơn thời gian leave, ở lại ít nhất 5 phút
        await asyncio.sleep(300)
    
    # Leave voice
    await manager.leave_voice()
    await manager.cleanup()

# ─── MAIN ───────────────────────────────────────────────────────────────────
async def main():
    print("🎸 BOCCHI THE ROCK - DISCORD VOICE TIMELINE 🎸")
    print("=" * 50)
    
    tokens = parse_tokens(TOKENS_RAW)
    print(f"[*] Loaded {len(tokens)} token(s)\n")
    
    if len(tokens) < 2:
        print("[!] Cần ít nhất 2 tokens!")
        return
    
    if not GUILD_ID or not CHANNEL_ID:
        print("[!] Missing SERVER_ID or CHANNEL_ID!")
        return
    
    # Kiểm tra voice file
    voice_path = os.path.join(BOCCHI_VOICE_DIR, BOCCHI_VOICE_FILE)
    if os.path.exists(voice_path):
        print(f"[*] Voice file: {voice_path} ({os.path.getsize(voice_path)} bytes)")
    else:
        print(f"[*] Voice file NOT FOUND: {voice_path}")
        print(f"    (Sẽ tạo thư mục nếu chưa có, đặt file {BOCCHI_VOICE_FILE} vào đó)")
        # Tạo thư mục
        os.makedirs(BOCCHI_VOICE_DIR, exist_ok=True)
    
    print()
    
    # In timeline
    print("📋 TIMELINE SCHEDULE:")
    print(f"{'#':>3s} | {'Name':<20s} | {'Join':>14s} | {'Leave':>14s}")
    print("-" * 55)
    
    for i in range(len(tokens)):
        name = MEMBER_NAMES[i] if i < len(MEMBER_NAMES) else f"Token #{i}"
        join_delay = TOKEN_JOIN_DELAYS[i] if i < len(TOKEN_JOIN_DELAYS) else (i * 600)
        leave_time = TOKEN_LEAVE_TIMES[i] if i < len(TOKEN_LEAVE_TIMES) else (28800)
        
        join_str = f"T+{join_delay//3600}h{join_delay%3600//60:02d}m" if join_delay > 0 else "Now"
        leave_str = f"T+{leave_time//3600}h{leave_time%3600//60:02d}m"
        
        print(f"{i:3d} | {name:<20s} | {join_str:>14s} | {leave_str:>14s}")
    
    print("-" * 55)
    print()
    
    # Chạy TẤT CẢ token SONG SONG (mỗi token 1 task riêng)
    tasks = []
    for i, token in enumerate(tokens):
        task = asyncio.create_task(
            run_token_lifecycle(token, i, GUILD_ID, CHANNEL_ID)
        )
        tasks.append(task)
    
    print(f"[*] Starting {len(tasks)} parallel token tasks...")
    print(f"[*] All tokens will join/leave independently!")
    print(f"[*] Auto UNMUTE: YES\n")
    print("=" * 50)
    print()
    
    # Chờ tất cả hoàn thành
    await asyncio.gather(*tasks)
    
    print("\n✅ All tokens finished!")

if __name__ == "__main__":
    asyncio.run(main())
