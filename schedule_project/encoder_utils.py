# encoder_utils.py
import socket
import json
import os

ENCODER_CONFIG_PATH = "encoders.json"

# ➤ 載入 encoder IP/Port 設定
def load_encoder_config():
    if not os.path.exists(ENCODER_CONFIG_PATH):
        print(f"❌ 找不到設定檔 {ENCODER_CONFIG_PATH}")
        return {}
    with open(ENCODER_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

encoder_config = load_encoder_config()

# ➤ 建立 socket 連線（依 encoder_name 找 IP/Port）
def connect_socket(encoder_name):
    info = encoder_config.get(encoder_name)
    if not info:
        print(f"❌ 無法找到 encoder 設定: {encoder_name}")
        return None
    host, port = info.get("host"), info.get("port")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((host, port))
        print(f"✅ 連線成功 {encoder_name} ({host}:{port})")
        return s
    except Exception as e:
        print(f"❌ {encoder_name} 連線失敗: {e}")
        return None

# ➤ 傳送命令並接收回應
def send_command(sock, cmd):
    try:
        encoded = (cmd + "\r\n").encode("cp950")
        sock.sendall(encoded)
        sock.settimeout(2)
        data = b""
        while True:
            try:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
        response = data.decode("cp950", errors="replace")
        print("⬅️ Response:\n", response)
        return response.strip()
    except Exception as e:
        print(f"❌ 指令傳送失敗: {e}")
        return ""

# ➤ 發送一次性命令（自動連線 ➜ 發送 ➜ 關閉）
def send_encoder_command(encoder_name, cmd):
    sock = connect_socket(encoder_name)
    if not sock:
        return "❌ 無法連線"
    response = send_command(sock, cmd)
    sock.close()
    return response

# ➤ Encoder 列表（直接從設定檔讀取）
def list_encoders():
    return list(encoder_config.keys())