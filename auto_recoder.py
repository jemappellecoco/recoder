import tkinter as tk
import socket
import os
from datetime import datetime
HOST = "192.168.30.228"   # 改成你的 Ingest IP
PORT = 32108             # 改成你的 Port

def send_command(cmd):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            # 使用 cp950（Big5）編碼，支援中文檔名
            encoded_cmd = (cmd + "\r\n").encode("cp950", errors="strict")
            s.sendall(encoded_cmd)
            response = s.recv(1024).decode("cp950", errors="replace")
            print("✔️ Sent:", cmd)
            print("⬅️ Response:", response.strip())
            return response.strip()
    except UnicodeEncodeError as e:
        print(f"❌ 編碼失敗，可能含有不能轉成 Big5 的字元：{e}")
        return "ENCODING ERROR"
    except Exception as e:
        print("❌ 連線或傳送錯誤：", e)
        return f"ERROR: {e}"



def start_encoder(encoder_name, entry):
    filename = entry.get().strip()
    if filename == "":
        print(f"⚠️ {encoder_name} 檔名不可空白")
        return
    # 日期資訊
    date_folder = datetime.today().strftime("%m.%d.%Y")  # 用於建立資料夾
    date_prefix = datetime.today().strftime("%m%d")      # 加在檔名前
    send_command(f'Setfile "{encoder_name}" 1 {date_folder}\{date_prefix}_{filename}')
    send_command(f'Start "{encoder_name}" 1')

def stop_encoder(encoder_name):
    send_command(f'Stop "{encoder_name}" 1')

# GUI 介面
root = tk.Tk()
root.title("🎬 Ingest 控制面板（兩台 encoder + 手動檔名）")

# Encoder1 控制區
tk.Label(root, text="Encoder1 檔名：").grid(row=0, column=0, padx=10, pady=5, sticky="e")
entry1 = tk.Entry(root, width=30)
entry1.grid(row=0, column=1, padx=5)
tk.Button(root, text="▶️ 開始錄影", command=lambda: start_encoder("Bak4-1", entry1)).grid(row=1, column=0, padx=10, pady=5)
tk.Button(root, text="⏹ 停止錄影", command=lambda: stop_encoder("Bak4-1")).grid(row=1, column=1, padx=10, pady=5)

# Encoder2 控制區
tk.Label(root, text="Encoder2 檔名：").grid(row=2, column=0, padx=10, pady=5, sticky="e")
entry2 = tk.Entry(root, width=30)
entry2.grid(row=2, column=1, padx=5)
tk.Button(root, text="▶️ 開始錄影", command=lambda: start_encoder("Bak4-2", entry2)).grid(row=3, column=0, padx=10, pady=5)
tk.Button(root, text="⏹ 停止錄影", command=lambda: stop_encoder("Bak4-2")).grid(row=3, column=1, padx=10, pady=5)

root.mainloop()
