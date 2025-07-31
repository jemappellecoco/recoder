# encoder_utils.py
import socket
import json
import os
from utils import resource_path,log
# ➤ 設定連線參數
# HOST = "192.168.30.228"
# PORT = 32108
ENCODER_CONFIG_PATH = "encoders.json"
# ➤ 全域持久 socket 變數（模擬 Telnet 模式）
persistent_sock = None
# ➤ 載入 encoder IP/Port 設定
def load_encoder_config():
    if not os.path.exists(ENCODER_CONFIG_PATH):
        log(f"❌ 找不到設定檔 {ENCODER_CONFIG_PATH}")
        return {}
    with open(resource_path("encoders.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

encoder_config = load_encoder_config()
def init_socket():
    """
    初始化持久 socket，如果已連線就重複使用。
    """
    global persistent_sock
    if persistent_sock is None:
        persistent_sock = connect_socket()
    return persistent_sock

def close_socket():
    """
    結束連線：關閉持久 socket。
    """
    global persistent_sock
    if persistent_sock:
        try:
            persistent_sock.close()
        except:
            pass
        persistent_sock = None

def send_persistent_command(cmd):
    """
    使用持久 socket 發送命令。
    若尚未連線會先建立。
    """
    global persistent_sock
    if persistent_sock is None:
        persistent_sock = connect_socket()
    try:
        return send_command(persistent_sock, cmd)
    except Exception as e:
        log("⚠️ 可能連線已失效，重試一次：", e)
        close_socket()
        persistent_sock = connect_socket()
        if persistent_sock:
            return send_command(persistent_sock, cmd)
        else:
            return "❌ 無法重新建立連線"
    
# ➤ 建立 socket 連線（依 encoder_name 找 IP/Port）
def connect_socket(encoder_name):
    info = encoder_config.get(encoder_name)
    if not info:
        log(f"❌ 無法找到 encoder 設定: {encoder_name}")
        return None
    host, port = info.get("host"), info.get("port")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((host, port))
        log(f"✅ 連線成功 {encoder_name} ({host}:{port})")
        return s
    except Exception as e:
        log(f"❌ {encoder_name} 連線失敗: {e}")
        return None

def send_command(sock, cmd):
    """
    發送命令並接收回傳資料（一次性或持久 socket 都能用）。
    """
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
        log("⬅️ Response:\n", response)
        return response.strip()
    except (ConnectionResetError, BrokenPipeError, OSError) as e:
        log("❌ 指令傳送失敗（連線中斷）:", e)
        raise  # ➜ 讓外層 handle 重連
    except Exception as e:
        log("❌ 指令傳送失敗（其他）:", e)
        return ""

def list_encoders():
    """
    查詢目前支援的 encoder 清單（仍使用臨時連線）。
    """
    sock = connect_socket()
    if not sock:
        return []
    response = send_command(sock, "List")
    sock.close()

    encoders = []
    for line in response.splitlines():
        if "Mode:" in line:
            enc_name = line.split("Mode:")[0].strip()
            encoders.append(enc_name)
    if not encoders:
        log("⚠️ 沒有從 socket 抓到 encoder")
    return encoders
