import socket
from encoder_utils import load_encoder_config

conf = load_encoder_config()

for name, info in conf.items():
    host = info['host']
    port = info['port']
    print(f"➡️ 測試 {name} @ {host}:{port}")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        print(f"✅ 連線成功 {name}")
        s.close()
    except Exception as e:
        print(f"❌ 連線失敗: {e}")
