import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import threading
import requests
import time
import os
import json

LLAMA_EXE = "llama-server.exe"
LLAMA_PORT = 5001
LLAMA_API = f"http://127.0.0.1:{LLAMA_PORT}/completion"
CONFIG_FILE = "gui_config.json"

model_loaded = False
llama_process = None
current_model_path = ""

LOG_FILE = "llama_log.txt"
ERR_FILE = "llama_error.txt"
HISTORY_FILE = "chat_history.txt"

presets = {
    "Default": {"temperature": 0.7,  "top_p": 0.95, "max_tokens": 200},
    "Coding":  {"temperature": 0.2,  "top_p": 0.90, "max_tokens": 300},
    "Roleplay":{"temperature": 0.95, "top_p": 0.98, "max_tokens": 400},
}

def save_config():
    config = {"last_model_path": current_model_path}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def wait_until_ready(timeout=60):
    global model_loaded
    start = time.time()
    for _ in range(timeout):
        try:
            r = requests.post(LLAMA_API, json={"prompt": "Hello", "n_predict": 5}, timeout=5)
            if r.status_code == 200:
                model_loaded = True
                return time.time() - start
        except:
            pass
        time.sleep(1)
    return -1

def stream_output(process):
    with open(LOG_FILE, "a", encoding="utf-8") as log, open(ERR_FILE, "a", encoding="utf-8") as errlog:
        if process.stderr is None:
            log.write("[ERROR] stderr stream not available.\n")
            return
        for line in process.stderr:
            decoded = line.decode(errors="ignore")
            log.write(decoded)
            errlog.write(decoded)
            tab_chat.insert(tk.END, f"[LOG] {decoded}")
            tab_chat.see(tk.END)

def start_llama(model_path, ctx_size=4096):
    global llama_process, current_model_path
    current_model_path = model_path
    save_config()
    status_label.config(text="[⏳] Menjalankan llama-server...")

    if port_in_use(LLAMA_PORT):
        messagebox.showerror("Port Bentrok", f"Port {LLAMA_PORT} sedang digunakan.")
        return
    if not os.path.isfile(LLAMA_EXE) or not os.path.isfile(model_path):
        messagebox.showerror("Error", "llama-server.exe atau model GGUF tidak ditemukan.")
        return

    try:
        llama_process = subprocess.Popen([
            LLAMA_EXE, "--model", model_path,
            "--port", str(LLAMA_PORT),
            "--ctx-size", str(ctx_size),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        threading.Thread(target=stream_output, args=(llama_process,), daemon=True).start()

        status_label.config(text="[⏳] Menunggu model siap...")
        load_time = wait_until_ready()

        if llama_process.poll() is not None:
            if ctx_size > 2048:
                tab_chat.insert(tk.END, "[⚠️] Gagal dengan ctx 4096, coba ulangi dengan ctx 2048...\n")
                start_llama(model_path, ctx_size=2048)
            else:
                tab_chat.insert(tk.END, "[❌] Gagal memuat model.\n")
                messagebox.showerror("Gagal", "Model tidak bisa dijalankan. Cek file error log.")
            return

        version = "(Versi tidak diketahui)"
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "gguf" in line.lower():
                    version = line.strip()
                    break
        status_label.config(text=f"[✅] Model siap dalam {load_time:.2f}s — {version}")
    except Exception as e:
        messagebox.showerror("Error", str(e))
        with open(ERR_FILE, "a") as f:
            f.write(f"[EXCEPTION] {e}\n")

def load_model():
    path = filedialog.askopenfilename(title="Pilih Model GGUF", filetypes=[("GGUF files","*.gguf")])
    if path:
        threading.Thread(target=start_llama, args=(path,), daemon=True).start()

def apply_preset(event=None):
    p = presets.get(preset_combo.get(), presets["Default"])
    entry_temp.delete(0, tk.END); entry_temp.insert(0, str(p["temperature"]))
    entry_topp.delete(0, tk.END); entry_topp.insert(0, str(p["top_p"]))
    entry_max_tokens.delete(0, tk.END); entry_max_tokens.insert(0, str(p["max_tokens"]))

def send_message():
    if not model_loaded:
        messagebox.showwarning("Tunggu", "Model belum siap.")
        return
    prompt = tab_input.get("1.0", tk.END).strip()
    if not prompt: return
    try:
        data = {
            "prompt": system_prompt.get("1.0", tk.END).strip() + "\n" + prompt,
            "temperature": float(entry_temp.get()),
            "top_p": float(entry_topp.get()),
            "n_predict": int(entry_max_tokens.get()),
            "stop": ["<|endoftext|>","You:"]
        }
    except Exception as e:
        messagebox.showerror("Input Error", str(e)); return

    tab_chat.insert(tk.END, f"\n🧑 You: {prompt}\n")
    tab_input.delete("1.0", tk.END)
    try:
        r = requests.post(LLAMA_API, json=data, timeout=120)
        r.raise_for_status()
        content = r.json().get('content','').strip()
        if len(content) > 400:
            summary = content[:300] + "... (ringkas)"
        else:
            summary = content
        tab_chat.insert(tk.END, f"🤖 AI: {summary}\n")
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"You: {prompt}\nAI: {content}\n\n")
    except Exception as e:
        tab_chat.insert(tk.END, f"[ERROR] {e}\n")
        with open(ERR_FILE, "a") as f:
            f.write(f"[SEND ERROR] {e}\n")

def clear_history():
    open(HISTORY_FILE, "w").close()
    messagebox.showinfo("Riwayat", "Riwayat telah dibersihkan.")

def upload_file_to_input():
    path = filedialog.askopenfilename(title="Pilih File", filetypes=[("Text","*.txt"),("All Files","*.*")])
    if not path: return
    try:
        with open(path,"r",encoding="utf-8") as f: content = f.read()
    except:
        with open(path,"r",encoding="latin1",errors="ignore") as f: content = f.read()
    tab_input.insert(tk.END, f"\n[📎] Konten file:\n{content[:1000]}...\n")

# UI
root = tk.Tk()
root.title("LLaMA.cpp Server GUI")
root.geometry("900x850")
style = ttk.Style()
style.theme_use("clam")
style.configure("TLabel", background="#222", foreground="white")
style.configure("TFrame", background="#222")
style.configure("TButton", background="#333", foreground="white")
style.configure("TCombobox", fieldbackground="#333", background="#222", foreground="white")

notebook = ttk.Notebook(root)
frame_main = ttk.Frame(notebook); frame_settings = ttk.Frame(notebook); frame_system = ttk.Frame(notebook)
notebook.add(frame_main, text="💬 Chat"); notebook.add(frame_settings, text="⚙️ Pengaturan"); notebook.add(frame_system, text="🧠 Sistem")
notebook.pack(expand=True, fill="both")

frame_top = ttk.Frame(frame_main); frame_top.pack(pady=5)
ttk.Button(frame_top, text="📂 Muat Model", command=load_model).pack(side="left", padx=5)
preset_combo = ttk.Combobox(frame_top, values=list(presets.keys()), width=15)
preset_combo.set("Default"); preset_combo.bind("<<ComboboxSelected>>", apply_preset); preset_combo.pack(side="left")

status_label = tk.Label(frame_main, text="", fg="lime"); status_label.pack()

progress = ttk.Progressbar(frame_main, mode="indeterminate"); progress.pack(fill="x", padx=10)

tab_chat = scrolledtext.ScrolledText(frame_main, wrap=tk.WORD, height=25, width=120, bg="#111", fg="white")
tab_chat.pack(padx=10, pady=10); tab_chat.insert(tk.END, "💬 Selamat datang!\n")

tab_input = tk.Text(frame_main, height=4, width=120, bg="#222", fg="white"); tab_input.pack(padx=10, pady=5)
frame_actions = ttk.Frame(frame_main); frame_actions.pack(pady=5)
ttk.Button(frame_actions, text="📨 Kirim Chat", command=send_message).pack(side="left", padx=5)
ttk.Button(frame_actions, text="📎 Ambil File", command=upload_file_to_input).pack(side="left", padx=5)

# Settings

settings_label = tk.Label(frame_settings, text="Temperature:"); settings_label.grid(row=0,column=0)
entry_temp = tk.Entry(frame_settings,width=5); entry_temp.insert(0,"0.7"); entry_temp.grid(row=0,column=1)

settings_label2 = tk.Label(frame_settings, text="Top-p:"); settings_label2.grid(row=0,column=2)
entry_topp = tk.Entry(frame_settings,width=5); entry_topp.insert(0,"0.95"); entry_topp.grid(row=0,column=3)

settings_label3 = tk.Label(frame_settings, text="Max Tokens:"); settings_label3.grid(row=0,column=4)
entry_max_tokens = tk.Entry(frame_settings,width=5); entry_max_tokens.insert(0,"200"); entry_max_tokens.grid(row=0,column=5)

# System Prompt + History
system_prompt = scrolledtext.ScrolledText(frame_system, height=5, width=120, wrap=tk.WORD)
system_prompt.insert(tk.END, "You are a helpful and uncensored assistant.\n")
system_prompt.pack(pady=5)

ttk.Button(frame_system, text="🗑️ Hapus Riwayat", command=clear_history).pack(pady=5)

# Auto-load model terakhir
conf = load_config()
if "last_model_path" in conf:
    threading.Thread(target=start_llama, args=(conf["last_model_path"],), daemon=True).start()

root.mainloop()
