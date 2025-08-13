# encoder_utils.py
import socket
import json
import os

from utils import resource_path, log
import threading
_persistent_socks: dict[str, socket.socket] = {}
_sock_lock = threading.Lock()

ENCODER_CONFIG_PATH = "encoders.json"

# ➤ 載入 encoder IP/Port 設定
def get_local_encoder_config_path():
    return os.path.join(os.getcwd(), "encoders.json")

ENCODER_CONFIG_PATH = get_local_encoder_config_path()

def load_encoder_config():
    path = ENCODER_CONFIG_PATH

    if not os.path.exists(path):
        # ➜ 初次執行，複製一份 default（打包內的 encoders.json）
        default_path = resource_path("encoders.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    default_data = json.load(f)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=2, ensure_ascii=False)
                log(f"📄 已複製預設 encoders.json 到本地 ➜ {path}")
            except Exception as e:
                log(f"❌ 初始化 encoders.json 失敗: {e}")
                return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"❌ 載入 encoders.json 失敗: {e}")
        return {}

encoder_config = load_encoder_config()

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

# ➤ 傳送命令並接收回應
def send_command(sock, cmd):
    try:
        encoded = (cmd + "\r\n").encode("utf-8")
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
        response = data.decode("utf-8", errors="replace")
        log(f"⬅️ Response:\n {response}")
        return response.strip()
    except Exception as e:
        log(f"❌ 指令傳送失敗: {e}")
        return ""

# ➤ 發送一次性命令（自動連線 ➜ 發送 ➜ 關閉）
def send_encoder_command(encoder_name, cmd):
    sock = connect_socket(encoder_name)
    if not sock:
        return "❌ 無法連線"
    response = send_command(sock, cmd)
    sock.close()
    return response
def _get_persistent_sock(encoder_name: str):
    """取得某台 encoder 的持久連線；若沒有就建立並快取。"""
    if not encoder_name:
        # 仍保留相容行為：未指定就拿設定檔中的第一台
        encoder_name = next(iter(encoder_config), None)
    if not encoder_name:
        return None

    with _sock_lock:
        s = _persistent_socks.get(encoder_name)
        if s is None:
            s = connect_socket(encoder_name)
            if s:
                # 可選：開啟 TCP keepalive（不同 OS 可再細調）
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except Exception:
                    pass
                _persistent_socks[encoder_name] = s
        return s

def close_socket(encoder_name: str | None = None):
    """關閉單台或全部 encoder 的持久連線。"""
    with _sock_lock:
        if encoder_name:
            s = _persistent_socks.pop(encoder_name, None)
            if s:
                try: s.close()
                except Exception: pass
        else:
            # 關掉所有
            for name, s in list(_persistent_socks.items()):
                try: s.close()
                except Exception: pass
                _persistent_socks.pop(name, None)

def send_persistent_command(cmd: str, encoder_name: str | None = None) -> str:
    """
    用『該台』encoder 的持久 socket 送指令。
    - 第一次會建立連線並快取
    - 送失敗會針對『該台』重連一次
    """
    target = encoder_name if encoder_name else next(iter(encoder_config), None)
    if not target:
        return "❌ 無可用的 encoder"

    # 第一次（或已存在）的連線
    sock = _get_persistent_sock(target)
    if not sock:
        return f"❌ {target} 無法連線"

    try:
        return send_command(sock, cmd)
    except Exception as e:
        log(f"⚠️ {target} 可能連線失效，嘗試重連：{e}")
        # 關閉該台，重建連線再送一次
        close_socket(target)
        sock = _get_persistent_sock(target)
        if not sock:
            return f"❌ {target} 無法重新建立連線"
        try:
            return send_command(sock, cmd)
        except Exception as e2:
            log(f"❌ {target} 重新送指令仍失敗：{e2}")
            return f"❌ 指令送出失敗：{e2}"
# ➤ 結束連線：關閉持久 socket
# def close_socket():
#     global persistent_sock
#     if persistent_sock:
#         try:
#             persistent_sock.close()
#         except Exception:
#             pass
#         persistent_sock = None

# ➤ 使用持久 socket 發送命令
# def send_persistent_command(cmd, encoder_name=None):
#     """Send command using a persistent socket connection."""
#     global persistent_sock
#     if persistent_sock is None:
#         target = encoder_name if encoder_name else next(iter(encoder_config), None)
#         if target is None:
#             return "❌ 無可用的 encoder"
#         persistent_sock = connect_socket(target)
#     try:
#         return send_command(persistent_sock, cmd)
#     except Exception as e:
#         log(f"⚠️ 可能連線已失效，重試一次：{e}")
#         close_socket()
#         target = encoder_name if encoder_name else next(iter(encoder_config), None)
#         if target is None:
#             return "❌ 無可用的 encoder"
#         persistent_sock = connect_socket(target)
#         if persistent_sock:
#             return send_command(persistent_sock, cmd)
#         else:
#             return "❌ 無法重新建立連線"
# ➤ Encoder 列表（直接從設定檔讀取）
# def list_encoders():
#     return list(encoder_config.keys())
def list_encoders():
    return list(load_encoder_config().keys())


def list_encoders_with_alias():
    """Return list of (key, display_name) tuples."""
    config = load_encoder_config()
    return [(name, info.get("display_name", name)) for name, info in config.items()]


def get_encoder_display_name(name: str) -> str:
    """Return display name (alias) for the given encoder key."""
    info = encoder_config.get(name, {})
    return info.get("display_name", name)


def set_encoder_display_name(name: str, display_name: str):
    """Update display name for an encoder and persist the change."""
    config = load_encoder_config()
    if name in config:
        config[name]["display_name"] = display_name
        save_encoder_config(config)
        reload_encoder_config()


def save_encoder_config(data: dict):
    path = ENCODER_CONFIG_PATH
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log(f"💾 encoder 設定已儲存到 {path}")
    except Exception as e:
        log(f"❌ 儲存 encoder 設定失敗: {e}")

def reload_encoder_config():
    global encoder_config
    encoder_config = load_encoder_config()
def connect_socket_direct(ip: str, port: int):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((ip, port))
        log(f"✅ 已建立 socket 連線：{ip}:{port}")
        return s
    except Exception as e:
        log(f"❌ 無法連線 {ip}:{port} - {e}")
        return None


def discover_encoders(ip: str, port: int):
    """掃描指定 IP/Port 並回傳偵測到的 encoder 名稱列表"""
    sock = connect_socket_direct(ip, port)
    if not sock:
        return []
    response = send_command(sock, "LIST")
    sock.close()

    names = []
    for line in response.splitlines():
        if "Mode:" in line:
            name = line.split("Mode:")[0].strip()
            if name and name not in names:
                names.append(name)

    if not names:
        log("⚠️ 沒有找到任何 encoder 名稱")
    return names


def save_selected_encoders(names, ip, port):
    path = ENCODER_CONFIG_PATH
    config = load_encoder_config()

    added_names = []
    for name in names:
        if name in config:
            log(f"⚠️ 裝置 {name} 已存在，跳過新增")
            continue
        config[name] = {"host": ip, "port": port, "display_name": name}
        added_names.append(name)

    if not added_names:
        log("ℹ️ 沒有新的 encoder 需要新增")
        return

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        log(f"✅ 已將 {len(added_names)} 個 encoder 寫入 ➜ {path}")
        global encoder_config
        encoder_config = config
    except Exception as e:
        log(f"❌ 寫入 encoder 設定失敗: {e}")