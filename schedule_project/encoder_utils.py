# encoder_utils.py
import socket

HOST = "192.168.30.228"
PORT = 32108

def connect_socket():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((HOST, PORT))
        print("✅ 已建立 socket 連線")
        return s
    except Exception as e:
        print("❌ 連線失敗:", e)
        return None

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
        print("❌ 指令傳送失敗:", e)
        return ""

def list_encoders():
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
        print("⚠️ 沒有從 socket 抓到 encoder")
    return encoders
