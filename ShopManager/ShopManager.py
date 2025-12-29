import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import os
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict
from PIL import Image, ImageTk
import psycopg2
from psycopg2 import Error as PgError
import queue
import winreg
import time

COR_ICON_ITEM = "#DDC6F2"
COR_ICON_ITEMMALL = "#F8D7C0"


@dataclass
class ItemMall:
    item_id: int
    item_group: int
    item_index: int
    item_num: int
    money_unit: int
    point: int
    special_price: int
    sell: int
    on_sell_date: int
    not_sell_date: int
    account_num_limit: int
    recognized_percentage: float
    fortune_bag: str
    allow_buy_level: int
    new_account_day_limit: int
    note: str
    icon_name: str = ""
    display_name: str = ""


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tooltip,
            text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Tahoma", 10),
        )
        label.pack()

    def hide(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class LogConsole:
    def __init__(self, master):
        self.master = master
        self.log_window = None
        self.log_text = None
        self.message_queue = queue.Queue()
        self.after_id = None
        self.is_showing = False
        self.max_log_length = 500

    def create_log_window(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            return

        self.log_window = tk.Toplevel(self.master)
        self.log_window.title("Log de Operações")
        self.log_window.geometry("600x300")
        self.log_window.configure(bg="#2C3E50")
        self.log_window.protocol("WM_DELETE_WINDOW", self.hide_log_window)

        self.log_window.update_idletasks()
        main_x = self.master.winfo_x()
        main_y = self.master.winfo_y()
        main_width = self.master.winfo_width()
        main_height = self.master.winfo_height()

        log_width = self.log_window.winfo_width()
        log_height = self.log_window.winfo_height()

        x = main_x + (main_width // 2) - (log_width // 2)
        y = main_y + (main_height // 2) - (log_height // 2)

        self.log_window.geometry(f"{log_width}x{log_height}+{x}+{y}")

        log_frame = tk.Frame(self.log_window, bg="#34495E", relief="solid", bd=1)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(
            log_frame,
            text="Log de Operações:",
            font=("Tahoma", 10, "bold"),
            bg="#34495E",
            fg="#BDC3C7",
        ).pack(anchor="w", padx=5, pady=(5, 0))

        self.log_text = tk.Text(
            log_frame,
            bg="#2C3E50",
            fg="#ECF0F1",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            wrap=tk.WORD,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)

        self.log_text.tag_config("INFO", foreground="#8be9fd")
        self.log_text.tag_config("WARNING", foreground="#ffb86c")
        self.log_text.tag_config("ERROR", foreground="#ff5555")
        self.log_text.tag_config("DB", foreground="#50fa7b")
        self.log_text.tag_config("UI", foreground="#f1fa8c")
        self.log_text.tag_config("DEFAULT", foreground="#ECF0F1")

        log_scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        clear_button = ttk.Button(log_frame, text="Limpar Log", command=self.clear_log)
        clear_button.pack(pady=5)

        self.is_showing = True
        self._process_queue()

    def hide_log_window(self):
        if self.log_window:
            self.log_window.destroy()
            self.log_window = None
            self.is_showing = False
            if self.after_id:
                self.master.after_cancel(self.after_id)
                self.after_id = None

    def log_message(self, message, level="INFO", source="DEFAULT"):
        if len(message) > self.max_log_length:
            message = message[: self.max_log_length - 3] + "..."
        timestamp = time.strftime("%H:%M:%S")
        self.message_queue.put((f"[{timestamp}] {message}", level, source))
        if self.is_showing:
            if not self.after_id:
                self.after_id = self.master.after(100, self._process_queue)

    def _process_queue(self):
        while not self.message_queue.empty():
            message, level, source = self.message_queue.get_nowait()
            if self.log_text:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{source}] ", source)
                self.log_text.insert(tk.END, f"[{level}] ", level)
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        self.after_id = None

    def clear_log(self):
        if self.log_text:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log_message("Log limpo.", level="INFO", source="UI")


class RegistryManager:
    def __init__(self, app_name="StoreManager", key_name="GrandFantasiaPath"):
        self.app_name = app_name
        self.key_name = key_name
        self.registry_path = rf"Software\{self.app_name}"

    def read_path(self) -> Optional[str]:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.registry_path, 0, winreg.KEY_READ
            )
            path, _ = winreg.QueryValueEx(key, self.key_name)
            winreg.CloseKey(key)
            return path
        except FileNotFoundError:
            return None
        except Exception as e:
            print(f"Erro ao ler do registro: {e}")
            return None

    def write_path(self, path: str):
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.registry_path)
            winreg.SetValueEx(key, self.key_name, 0, winreg.REG_SZ, path)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Erro ao escrever no registro: {e}")


class DirectoryValidator:
    @staticmethod
    def is_valid_game_directory(directory_path: str) -> bool:
        if not os.path.isdir(directory_path):
            return False

        exe_found = False
        for filename in os.listdir(directory_path):
            if filename.lower() == "grandfantasia.exe":
                exe_found = True
                break
        if not exe_found:
            return False

        required_subdirs = [
            os.path.join(directory_path, "UI", "itemicon"),
            os.path.join(directory_path, "data", "db"),
            os.path.join(directory_path, "data", "Translate"),
        ]
        for subdir in required_subdirs:
            if not os.path.isdir(subdir):
                return False

        return True


class LoginScreen:
    def __init__(self, master):
        self.master = master
        self.master.title("Loja - Login no Banco de Dados")
        self.master.geometry("450x450")
        self.master.configure(bg="#2C3E50")
        self.master.resizable(False, False)

        self.master.update_idletasks()
        x = (self.master.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.master.winfo_screenheight() // 2) - (450 // 2)
        self.master.geometry(f"450x450+{x}+{y}")

        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.style.configure(
            "TButton",
            font=("Tahoma", 10, "bold"),
            padding=10,
            background="#E74C3C",
            foreground="#FFF",
            relief="flat",
        )
        self.style.map(
            "TButton",
            background=[("active", "#C0392B"), ("pressed", "#A93226")],
            foreground=[("active", "#fff")],
        )

        self.style.configure(
            "TLabel", background="#2C3E50", foreground="#ECF0F1", font=("Tahoma", 11)
        )

        self.style.configure(
            "TEntry",
            fieldbackground="#34495E",
            foreground="#ECF0F1",
            insertbackground="#ECF0F1",
            font=("Tahoma", 11),
        )

        self.style.configure("Login.TFrame", background="#34495E", relief="flat", bd=0)
        self.style.configure(
            "Login.TLabel",
            background="#34495E",
            foreground="#BDC3C7",
            font=("Tahoma", 10, "bold"),
        )
        self.style.configure(
            "Login.TEntry",
            fieldbackground="#2C3E50",
            foreground="#ECF0F1",
            insertbackground="#ECF0F1",
            font=("Tahoma", 10),
            relief="flat",
            bd=5,
        )

        self.game_directory = None
        self.registry_manager = RegistryManager()
        self.log_console = LogConsole(self.master)

        self.check_and_set_game_directory()
        self.create_widgets()

    def save_login_info(self, host, port, user, password):
        try:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"DB_HOST={host}\n")
                f.write(f"DB_PORT={port}\n")
                f.write(f"DB_USER={user}\n")
                f.write(f"DB_PASSWORD={password}\n")
            self.log_console.log_message(
                "Informações de login salvas no arquivo .env", level="INFO", source="UI"
            )
        except Exception as e:
            self.log_console.log_message(
                f"Erro ao salvar informações de login: {e}", level="ERROR", source="UI"
            )

    def load_login_info(self):
        try:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            if not os.path.exists(env_path):
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write("DB_HOST=localhost\n")
                    f.write("DB_PORT=5432\n")
                    f.write("DB_USER=postgres\n")
                    f.write("DB_PASSWORD=\n")
                self.log_console.log_message(
                    "Arquivo .env criado com valores padrão", level="INFO", source="UI"
                )

            login_info = {}
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        login_info[key] = value

            self.log_console.log_message(
                "Informações de login carregadas do arquivo .env",
                level="INFO",
                source="UI",
            )
            return login_info
        except Exception as e:
            self.log_console.log_message(
                f"Erro ao carregar informações de login: {e}",
                level="ERROR",
                source="UI",
            )
        return {}

    def check_and_set_game_directory(self):
        start_time = time.time()
        saved_path = self.registry_manager.read_path()

        if saved_path and DirectoryValidator.is_valid_game_directory(saved_path):
            self.game_directory = saved_path
            self.log_console.log_message(
                f"Diretório do jogo carregado do registro: {self.game_directory}",
                level="INFO",
                source="UI",
            )
        else:
            if saved_path:
                self.log_console.log_message(
                    f"Diretório do jogo '{saved_path}' inválido ou incompleto. Por favor, selecione um novo.",
                    level="WARNING",
                    source="UI",
                )
            else:
                self.log_console.log_message(
                    "Diretório do jogo não encontrado no registro. Por favor, selecione-o.",
                    level="INFO",
                    source="UI",
                )
            self.prompt_for_game_directory()

        if not self.game_directory:
            messagebox.showerror(
                "Erro de Diretório",
                "Um diretório válido do jogo Grand Fantasia é necessário para continuar. O aplicativo será fechado.",
            )
            self.master.destroy()
        end_time = time.time()
        self.log_console.log_message(
            f"Tempo de execução check_and_set_game_directory: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="UI",
        )

    def prompt_for_game_directory(self):
        start_time = time.time()
        while True:
            selected_directory = filedialog.askdirectory(
                title="Selecione a pasta do Grand Fantasia (onde está GrandFantasia.exe)"
            )
            if not selected_directory:
                if self.game_directory:
                    self.log_console.log_message(
                        "Seleção de diretório cancelada. Mantendo o diretório anterior.",
                        level="WARNING",
                        source="UI",
                    )
                    break
                else:
                    messagebox.showwarning(
                        "Atenção",
                        "O diretório do jogo é obrigatório. Por favor, selecione um diretório válido.",
                    )
                    continue

            if DirectoryValidator.is_valid_game_directory(selected_directory):
                self.game_directory = selected_directory
                self.registry_manager.write_path(selected_directory)
                self.log_console.log_message(
                    f"Novo diretório do jogo selecionado e salvo: {self.game_directory}",
                    level="INFO",
                    source="UI",
                )
                break
            else:
                messagebox.showwarning(
                    "Diretório Inválido",
                    "O diretório selecionado não é um diretório válido do Grand Fantasia. Certifique-se de que contém 'GrandFantasia.exe' e as pastas 'UI/itemicon', 'data/db' e 'data/Translate'.",
                )
                self.log_console.log_message(
                    f"Tentativa de diretório inválido: {selected_directory}",
                    level="ERROR",
                    source="UI",
                )
        end_time = time.time()
        self.log_console.log_message(
            f"Tempo de execução prompt_for_game_directory: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="UI",
        )

    def create_widgets(self):
        login_frame = ttk.Frame(
            self.master,
            style="Login.TFrame",
            padding=20,
            relief="raised",
            borderwidth=2,
        )
        login_frame.pack(pady=30, padx=30, fill=tk.BOTH, expand=True)
        login_frame.columnconfigure(1, weight=1)

        tk.Label(
            login_frame,
            text="Acessar Banco de Dados",
            font=("Tahoma", 18, "bold"),
            bg="#34495E",
            fg="#F39C12",
        ).grid(row=0, column=0, columnspan=2, pady=(0, 25), sticky="ew")

        saved_login = self.load_login_info()

        form_fields = [
            ("Host:", "host_entry", saved_login.get("DB_HOST", "localhost")),
            ("Porta:", "port_entry", saved_login.get("DB_PORT", "5432")),
            ("Usuário:", "user_entry", saved_login.get("DB_USER", "postgres")),
            ("Senha:", "password_entry", saved_login.get("DB_PASSWORD", "")),
        ]

        self.entries = {}

        for i, (label_text, field_name, default_value) in enumerate(form_fields):
            row_num = i + 1

            lbl = ttk.Label(login_frame, text=label_text, style="Login.TLabel")
            lbl.grid(row=row_num, column=0, sticky="w", padx=(0, 15), pady=8)

            entry = ttk.Entry(login_frame, style="Login.TEntry")
            entry.grid(row=row_num, column=1, sticky="ew", pady=8)
            entry.insert(0, default_value)
            self.entries[field_name] = entry

            if field_name == "password_entry":
                entry.config(show="*")

        connect_button = ttk.Button(
            self.master, text="Conectar", command=self.connect_to_db, style="TButton"
        )
        connect_button.pack(pady=(0, 10))

        change_dir_button = ttk.Button(
            self.master,
            text="Trocar Diretório do Jogo",
            command=self.prompt_for_game_directory,
            style="TButton",
        )
        change_dir_button.pack(pady=(5, 20))

    def connect_to_db(self):
        start_time = time.time()
        if not self.game_directory:
            self.log_console.log_message(
                "Diretório do jogo não definido. Não é possível conectar ao DB.",
                level="ERROR",
                source="UI",
            )
            messagebox.showerror(
                "Erro",
                "O diretório do jogo Grand Fantasia não está definido ou é inválido. Por favor, selecione um diretório válido.",
            )
            self.prompt_for_game_directory()
            if not self.game_directory:
                self.master.destroy()
            return

        host = self.entries["host_entry"].get()
        port = self.entries["port_entry"].get()
        user = self.entries["user_entry"].get()
        password = self.entries["password_entry"].get()
        db_name = "gf_ls"

        self.save_login_info(host, port, user, password)

        conn = None
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=db_name,
                client_encoding="UTF8",
                connect_timeout=5,
            )
            self.log_console.log_message(
                "Conexão ao banco de dados estabelecida!", level="INFO", source="DB"
            )
            self.master.destroy()
            app = ItemMallEditor(db_connection=conn, game_directory=self.game_directory)
            app.run()
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            if (
                "password authentication failed" in error_msg
                or "authentication failed" in error_msg
            ):
                messagebox.showerror(
                    "Erro de Autenticação",
                    "Usuário ou senha inválidos. Verifique suas credenciais e tente novamente.",
                )
                self.log_console.log_message(
                    "Falha na autenticação: usuário ou senha inválidos.",
                    level="ERROR",
                    source="DB",
                )
            elif (
                "could not connect" in error_msg
                or "connection refused" in error_msg
                or "timeout" in error_msg
            ):
                messagebox.showerror(
                    "Erro de Conexão",
                    "Não foi possível conectar ao servidor de banco de dados. Verifique se o servidor está online e as configurações de rede.",
                )
                self.log_console.log_message(
                    "Falha na conexão: servidor inacessível.",
                    level="ERROR",
                    source="DB",
                )
            else:
                messagebox.showerror(
                    "Erro de Conexão",
                    f"Não foi possível conectar ao banco de dados: {e}",
                )
                self.log_console.log_message(
                    f"Erro operacional ao conectar ao DB: {e}",
                    level="ERROR",
                    source="DB",
                )
            if conn:
                conn.close()
        except PgError as e:
            messagebox.showerror(
                "Erro de Banco de Dados",
                f"Login ou senha inválidos, ou erro no banco de dados: {e}",
            )
            self.log_console.log_message(
                f"Erro do PostgreSQL ao conectar: {e}", level="ERROR", source="DB"
            )
            if conn:
                conn.close()
        except Exception as e:
            messagebox.showerror(
                "Erro Inesperado", f"Ocorreu um erro inesperado ao conectar: {e}"
            )
            self.log_console.log_message(
                f"Erro inesperado ao conectar ao DB: {e}", level="ERROR", source="DB"
            )
            if conn:
                conn.close()
        finally:
            end_time = time.time()
            self.log_console.log_message(
                f"Tempo de execução connect_to_db: {end_time - start_time:.4f} segundos",
                level="INFO",
                source="UI",
            )


class ItemMallEditor:
    def __init__(self, db_connection=None, game_directory=None):
        self.root = tk.Tk()
        self.root.title("Loja")
        self.root.geometry("1200x800")
        self.root.configure(bg="#2C3E50")

        self.db_conn = db_connection
        self.game_directory = game_directory
        
        self.current_lang_folder = "Translate_PT"

        self.items_per_page = 12
        self.current_page = 0
        self.current_category = 50
        self.current_money_unit = 1

        self.categories = [
            (50, "POPULAR"),
            (1, "LIMITADO"),
            (9, "BARRO"),
            (2, "BOOSTS"),
            (3, "UTILIDADE"),
            (4, "FABRICAÇÃO"),
            (5, "MELHORIA"),
            (6, "FANTASIA"),
            (7, "MONTARIAS"),
            (8, "SPRITE"),
        ]

        self.items: List[ItemMall] = []
        self.filtered_items: List[ItemMall] = []
        self.item_icons = {}
        self.item_icon_names = {}
        self.item_display_names = {}

        self.log_console = LogConsole(self.root)

        self.load_item_mappings()
        self.build_ui()

        self.log_message(
            "Conectado ao banco de dados PostgreSQL.", level="INFO", source="DB"
        )
        self.load_items_from_db()

        self.filter_by_category(self.current_category, preserve_page=True)

    def log_message(self, message, level="INFO", source="DEFAULT"):
        self.log_console.log_message(message, level, source)

    def detect_encoding(self, file_path):
        encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1", "utf-16"]
        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    f.read()
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        return "utf-8"

    def _process_ini_file(
        self,
        file_path: str,
        parse_line_func: Callable[[str], Optional[tuple]],
        target_dict: Dict,
    ):
        if not os.path.exists(file_path):
            return

        try:
            encoding = self.detect_encoding(file_path)
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()

            for line in lines[1:]:
                line = line.strip()
                if not line or line.startswith(";"):
                    continue

                result = parse_line_func(line)
                if result:
                    key, value = result
                    target_dict[key] = value
        except Exception as e:
            self.log_message(
                f"Erro ao ler arquivo INI {os.path.basename(file_path)}: {e}",
                level="ERROR",
                source="DB",
            )

    def load_item_mappings(self):
        start_time = time.time()
        self.item_display_names = {}
        
        data_db_dir = os.path.join(self.game_directory, "data", "db")
        Translate_dir = os.path.join(self.game_directory, "data", self.current_lang_folder)

        def parse_icon_line(line: str) -> Optional[tuple]:
            parts = line.split("|")
            if len(parts) > 1:
                try:
                    item_id = int(parts[0])
                    icon_name = parts[1].strip()
                    if icon_name:
                        return item_id, icon_name
                except ValueError:
                    pass
            return None

        def parse_name_line(line: str) -> Optional[tuple]:
            parts = line.split("|")
            if len(parts) > 2:
                try:
                    item_id = int(parts[0])
                    display_name = parts[1].strip()
                    if display_name:
                        return item_id, display_name
                except ValueError:
                    pass
            return None

        self._process_ini_file(
            os.path.join(data_db_dir, "C_Item.ini"),
            parse_icon_line,
            self.item_icon_names,
        )
        self._process_ini_file(
            os.path.join(data_db_dir, "C_ItemMall.ini"),
            parse_icon_line,
            self.item_icon_names,
        )
        self._process_ini_file(
            os.path.join(Translate_dir, "T_Item.ini"),
            parse_name_line,
            self.item_display_names,
        )
        self._process_ini_file(
            os.path.join(Translate_dir, "T_ItemMall.ini"),
            parse_name_line,
            self.item_display_names,
        )

        end_time = time.time()
        self.log_message(
            f"Tempo de leitura dos scripts INI ({self.current_lang_folder}): {end_time - start_time:.4f} segundos",
            level="INFO",
            source="DB",
        )

    def change_language(self, folder_name):
        """Troca a pasta de tradução e recarrega os itens."""
        self.current_lang_folder = folder_name
        self.log_message(f"Idioma alterado para pasta: {folder_name}", level="INFO", source="UI")
        self.load_item_mappings()
        self.load_items_from_db()

    def load_item_icon(
        self, icon_name: str, item_id: int
    ) -> Optional[ImageTk.PhotoImage]:
        key = f"{icon_name}_{item_id}"
        if key in self.item_icons:
            return self.item_icons[key]

        icon_path = os.path.join(
            self.game_directory, "UI", "itemicon", f"{icon_name}.dds"
        )
        if not os.path.exists(icon_path):
            return None

        try:
            with Image.open(icon_path) as img:
                img = img.resize((32, 32), Image.Resampling.LANCZOS)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")

                bg = Image.new(
                    "RGBA",
                    (40, 40),
                    COR_ICON_ITEM if item_id < 40000 else COR_ICON_ITEMMALL,
                )
                bg.paste(img, (4, 4), img)

                photo = ImageTk.PhotoImage(bg)
                self.item_icons[key] = photo
                return photo
        except Exception as e:
            self.log_message(
                f"Erro ao carregar ícone {icon_name}: {e}", level="ERROR", source="UI"
            )
            return None

    def _generate_itemmall_sql_content(self, items_list: List[ItemMall]) -> str:
        sql_content = 'DROP TABLE IF EXISTS "public"."itemmall";\n\n'
        sql_content += 'CREATE TABLE "public"."itemmall" (\n'
        sql_content += '  "item_id" int4 NOT NULL,\n'
        sql_content += '  "item_group" int4 NOT NULL,\n'
        sql_content += '  "item_index" int4 NOT NULL,\n'
        sql_content += '  "item_num" int4 NOT NULL,\n'
        sql_content += '  "money_unit" int4 NOT NULL,\n'
        sql_content += '  "point" int4 NOT NULL,\n'
        sql_content += '  "special_price" int4 NOT NULL,\n'
        sql_content += '  "sell" int4 NOT NULL,\n'
        sql_content += '  "on_sell_date" int4 NOT NULL,\n'
        sql_content += '  "not_sell_date" int4 NOT NULL,\n'
        sql_content += '  "account_num_limit" int4 DEFAULT 0,\n'
        sql_content += '  "recognized_percentage" float8 NOT NULL,\n'
        sql_content += (
            ' "fortune_bag" text COLLATE "pg_catalog"."default" DEFAULT \'\'::text,\n'
        )
        sql_content += '  "allow_buy_level" int4 NOT NULL,\n'
        sql_content += '  "new_account_day_limit" int4 DEFAULT 0,\n'
        sql_content += (
            ' "note" text COLLATE "pg_catalog"."default" DEFAULT \'\'::text\n'
        )
        sql_content += ");\n\n"

        for item in items_list:
            escaped_note = item.note.replace("'", "''")
            sql_content += f'INSERT INTO "public"."itemmall" VALUES '
            sql_content += f"({item.item_id}, {item.item_group}, {item.item_index}, "
            sql_content += f"{item.item_num}, {item.money_unit}, {item.point}, "
            sql_content += f"{item.special_price}, {item.sell}, {item.on_sell_date}, "
            sql_content += f"{item.not_sell_date}, {item.account_num_limit}, "
            sql_content += f'{item.recognized_percentage}, \'{item.fortune_bag.replace("'", "''")}\''
            sql_content += f", {item.allow_buy_level}, {item.new_account_day_limit}, "
            sql_content += f"'{escaped_note}');\n"
        return sql_content

    def _handle_sql_export_action(self, action: str, sql_content: str):
        if action == "copy_db":
            self.root.clipboard_clear()
            self.root.clipboard_append(sql_content)
            self.root.update()
            self.log_message(
                "Script SQL copiado para a área de transferência.",
                level="INFO",
                source="UI",
            )
        elif action == "save":
            file_path = filedialog.asksaveasfilename(
                title="Salvar arquivo SQL",
                defaultextension=".sql",
                filetypes=[("Arquivos SQL", "*.sql"), ("Todos os arquivos", "*.*")],
                initialfile="itemmall.sql",
            )
            if not file_path:
                self.log_message(
                    "Salvamento de arquivo SQL cancelado.",
                    level="WARNING",
                    source="DB",
                )
                return
            with open(file_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(sql_content)
            self.log_message(
                f"Arquivo SQL salvo em: {file_path}", level="INFO", source="DB"
            )
        elif action == "execute_db":
            if not self.db_conn:
                self.log_message(
                    "Não está conectado ao banco de dados para executar o script.",
                    level="ERROR",
                    source="DB",
                )
                return

            self.log_message(
                "AVISO: Esta operação irá APAGAR e REINSERIR todos os itens da tabela itemmall no banco de dados.",
                level="WARNING",
                source="DB",
            )
            try:
                cursor = self.db_conn.cursor()
                self.log_message(
                    "Iniciando execução do script SQL no banco de dados...",
                    level="INFO",
                    source="DB",
                )

                commands = [
                    cmd.strip() for cmd in sql_content.split(";") if cmd.strip()
                ]

                for cmd in commands:
                    if cmd:
                        cursor.execute(cmd)
                        self.db_conn.commit()

                self.log_message(
                    "Script SQL executado no banco de dados com sucesso.",
                    level="INFO",
                    source="DB",
                )
                cursor.close()
                self.load_items_from_db()
            except PgError as e:
                self.db_conn.rollback()
                self.log_message(
                    f"Erro ao executar script no DB: {e}",
                    level="ERROR",
                    source="DB",
                )
            except Exception as e:
                self.db_conn.rollback()
                self.log_message(
                    f"Erro inesperado ao executar script no DB: {str(e)}",
                    level="ERROR",
                    source="DB",
                )
        else:
            self.log_message(
                "Ação desconhecida para exportação de SQL.",
                level="ERROR",
                source="UI",
            )

    def export_sql(self, action: str):
        start_time = time.time()
        try:
            self.log_message("Gerando script SQL...", level="INFO", source="DB")
            sorted_items = sorted(
                self.items, key=lambda x: (x.item_group, x.item_index, x.money_unit)
            )
            sql_content = self._generate_itemmall_sql_content(sorted_items)
            self._handle_sql_export_action(action, sql_content)
        except Exception as e:
            self.log_message(
                f"Erro ao exportar SQL: {str(e)}", level="ERROR", source="UI"
            )
        finally:
            end_time = time.time()
            self.log_message(
                f"Tempo de execução export_sql: {end_time - start_time:.4f} segundos",
                level="INFO",
                source="DB",
            )

    def run_sql_file_on_db(self):
        start_time = time.time()
        if not self.db_conn:
            self.log_message(
                "Não está conectado ao banco de dados para rodar um arquivo SQL.",
                level="ERROR",
                source="DB",
            )
            return

        file_path = filedialog.askopenfilename(
            title="Selecionar arquivo SQL para rodar no DB",
            filetypes=[("Arquivos SQL", "*.sql"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            self.log_message(
                "Execução de arquivo SQL no DB cancelada pelo usuário.",
                level="WARNING",
                source="UI",
            )
            return

        self.log_message(
            f"AVISO: Esta operação irá APAGAR e REINSERIR os dados na tabela 'itemmall' "
            f"do banco de dados com o conteúdo de '{os.path.basename(file_path)}'.",
            level="WARNING",
            source="DB",
        )

        try:
            encoding = self.detect_encoding(file_path)
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                sql_content = f.read()

            cursor = self.db_conn.cursor()
            self.log_message(
                f"Iniciando execução do arquivo SQL '{file_path}' no banco de dados...",
                level="INFO",
                source="DB",
            )

            commands = [
                cmd.strip()
                for cmd in re.split(r";\s*$", sql_content, flags=re.MULTILINE)
                if cmd.strip()
            ]

            for cmd in commands:
                try:
                    cursor.execute(cmd)
                    self.db_conn.commit()
                except PgError as statement_error:
                    self.db_conn.rollback()
                    self.log_message(
                        f"Erro ao executar comando do arquivo SQL: {statement_error}\nComando: {cmd[:200]}...",
                        level="ERROR",
                        source="DB",
                    )
                    cursor.close()
                    return

            cursor.close()
            self.log_message(
                f"Arquivo SQL '{os.path.basename(file_path)}' executado no banco de dados com sucesso!",
                level="INFO",
                source="DB",
            )
            self.load_items_from_db()

        except FileNotFoundError:
            self.log_message(
                f"Arquivo não encontrado: {file_path}", level="ERROR", source="DB"
            )
        except PgError as e:
            self.db_conn.rollback()
            self.log_message(
                f"Erro ao rodar arquivo SQL no DB: {e}", level="ERROR", source="DB"
            )
        except Exception as e:
            self.db_conn.rollback()
            self.log_message(
                f"Erro inesperado ao rodar arquivo SQL no DB: {e}",
                level="ERROR",
                source="DB",
            )
        finally:
            end_time = time.time()
            self.log_message(
                f"Tempo de execução run_sql_file_on_db: {end_time - start_time:.4f} segundos",
                level="INFO",
                source="DB",
            )

    def build_ui(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TButton",
            font=("Tahoma", 10, "bold"),
            padding=6,
            background="#E74C3C",
            foreground="#FFF",
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", "#C0392B"), ("pressed", "#A93226")],
            foreground=[("active", "#fff")],
        )
        style.configure(
            "TLabel", background="#2C3E50", foreground="#ECF0F1", font=("Tahoma", 11)
        )

        menubar = tk.Menu(
            self.root,
            tearoff=0,
            bg="#2C3E50",
            fg="#ECF0F1",
            font=("Tahoma", 11, "bold"),
            activebackground="#34495E",
            activeforeground="#F39C12",
            relief="flat",
            bd=0,
        )

        filemenu = tk.Menu(
            menubar,
            tearoff=0,
            bg="#2C3E50",
            fg="#ECF0F1",
            font=("Tahoma", 11),
            activebackground="#E74C3C",
            activeforeground="#FFF",
            relief="flat",
            bd=1,
        )

        filemenu.add_command(label="🔄 Recarregar DB", command=self.load_items_from_db)
        filemenu.add_command(
            label="💾 Salvar SQL", command=lambda: self.export_sql("save")
        )
        filemenu.add_command(
            label="📝 Rodar SQL no DB", command=self.run_sql_file_on_db
        )
        filemenu.add_command(
            label="📋 Copiar SQL", command=lambda: self.export_sql("copy_db")
        )

        filemenu.add_separator()
        filemenu.add_command(label="🔄 Alterar Loja", command=self.switch_money_unit)
        filemenu.add_separator()
        filemenu.add_command(
            label="📜 Mostrar Log", command=self.log_console.create_log_window
        )

        langmenu = tk.Menu(
            menubar,
            tearoff=0,
            bg="#2C3E50",
            fg="#ECF0F1",
            font=("Tahoma", 11),
            activebackground="#F39C12",
            activeforeground="#FFF",
            relief="flat",
            bd=1,
        )
        langmenu.add_command(label="🇧🇷 Português", command=lambda: self.change_language("Translate_PT"))
        langmenu.add_command(label="🇺🇸 Inglês", command=lambda: self.change_language("Translate_EN"))
        langmenu.add_command(label="🇪🇸 Espanhol", command=lambda: self.change_language("Translate"))
        langmenu.add_command(label="🇫🇷 Francês", command=lambda: self.change_language("Translate_FR"))
        langmenu.add_command(label="🇩🇪 Alemão", command=lambda: self.change_language("Translate_DE"))

        menubar.add_cascade(label="📚 MENU", menu=filemenu)
        menubar.add_cascade(label="🌐 IDIOMA", menu=langmenu)
        
        self.root.config(menu=menubar)

        topbar = tk.Frame(self.root, bg="#2C3E50", relief="flat", bd=0)
        topbar.pack(fill=tk.X, padx=0, pady=(0, 10))

        title_container = tk.Frame(topbar, bg="#34495E", relief="solid", bd=1)
        title_container.pack(pady=15, padx=20)

        self.nome_loja_label = tk.Label(
            title_container,
            text=self.get_nome_loja(),
            font=("Tahoma", 18, "bold"),
            bg="#34495E",
            fg="#F39C12",
            padx=30,
            pady=10,
        )
        self.nome_loja_label.pack()

        self.cat_frame = tk.Frame(self.root, bg="#2C3E50")
        self.cat_frame.pack(pady=(0, 15))

        self.cat_buttons = {}
        for cat_id, cat_name in self.categories:
            btn = ttk.Button(
                self.cat_frame,
                text=cat_name,
                width=12,
                style="TButton",
                command=lambda c=cat_id: self.filter_by_category(c),
            )
            btn.pack(side=tk.LEFT, padx=3)
            self.cat_buttons[cat_id] = btn

        self.cards_frame = tk.Frame(self.root, bg="#2C3E50")
        self.cards_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 0))

        pag_frame = tk.Frame(self.root, bg="#2C3E50")
        pag_frame.pack(fill=tk.X, pady=(8, 18), padx=0)

        pag_inner = tk.Frame(pag_frame, bg="#2C3E50")
        pag_inner.pack(anchor="center")

        self.btn_prev = ttk.Button(pag_inner, text="Anterior", command=self.prev_page)
        self.btn_prev.pack(side=tk.LEFT)

        self.page_label = ttk.Label(
            pag_inner, text="Página 1 de 1", font=("Tahoma", 11, "bold")
        )
        self.page_label.pack(side=tk.LEFT, padx=20)

        self.btn_next = ttk.Button(pag_inner, text="Próxima", command=self.next_page)
        self.btn_next.pack(side=tk.LEFT)

        self.info_label = ttk.Label(pag_frame, text="", font=("Tahoma", 10))
        self.info_label.pack(side=tk.RIGHT, padx=30)

    def get_nome_loja(self):
        return (
            "🏪 Loja de Pontos"
            if self.current_money_unit == 1
            else "🏪 Loja de Bônus Point"
        )

    def switch_money_unit(self):
        self.current_money_unit = 2 if self.current_money_unit == 1 else 1
        self.nome_loja_label.config(text=self.get_nome_loja())
        self.filter_by_category(self.current_category, preserve_page=True)
        self.log_message(
            f"Loja alterada para: {self.get_nome_loja()}", level="INFO", source="UI"
        )

    def filter_by_category(self, category_id: int, preserve_page: bool = False):
        self.current_category = category_id
        if not preserve_page:
            self.current_page = 0

        for cid, btn in self.cat_buttons.items():
            if cid == category_id:
                btn.state(["pressed"])
            else:
                btn.state(["!pressed"])

        self.filtered_items = [
            item
            for item in self.items
            if item.item_group == category_id
            and item.money_unit == self.current_money_unit
        ]
        self.filtered_items.sort(key=lambda x: x.item_index)

        if category_id == 50:
            self.filtered_items = self.filtered_items[:8]

        if preserve_page:
            total_pages = self._get_total_pages()
            if self.current_page >= total_pages:
                self.current_page = max(0, total_pages - 1)
        self.refresh_cards()

        category_name = "Desconhecido"
        for cat_id, name in self.categories:
            if cat_id == category_id:
                category_name = name
                break

        self.log_message(
            f"Filtrando por categoria: {category_name}", level="INFO", source="UI"
        )

    def truncate_text(self, text, max_length=20):
        if len(text) > max_length:
            return text[: max_length - 3] + "..."
        return text

    def build_card(self, parent, item: ItemMall):
        card = tk.Frame(
            parent,
            bg="#34495E",
            width=260,
            height=120,
            highlightthickness=1,
            highlightcolor="#BDC3C7",
            bd=0,
        )
        card.grid_propagate(False)

        top_row = tk.Frame(card, bg="#34495E")
        top_row.pack(fill=tk.X, padx=10, pady=(8, 5))

        icon_container = tk.Frame(top_row, bg="#34495E", width=45, height=45)
        icon_container.pack(side=tk.LEFT, padx=(0, 8))
        icon_container.pack_propagate(False)

        icon_img = self.load_item_icon(item.icon_name, item.item_id)
        icon_bg = tk.Frame(
            icon_container,
            width=40,
            height=40,
            bg=COR_ICON_ITEM if item.item_id < 40000 else COR_ICON_ITEMMALL,
            bd=0,
        )
        icon_bg.place(x=0, y=0)
        icon_bg.pack_propagate(False)

        if icon_img:
            lbl_icon = tk.Label(icon_bg, image=icon_img, bg=icon_bg["bg"])
            lbl_icon.image = icon_img
            lbl_icon.pack(expand=True, fill=tk.BOTH)
        else:
            lbl_icon = tk.Label(
                icon_bg, text="?", bg=icon_bg["bg"], font=("Tahoma", 16, "bold")
            )
            lbl_icon.pack(expand=True, fill=tk.BOTH)

        if item.item_num > 1:
            qty_label = tk.Label(
                icon_container,
                text=str(item.item_num),
                font=("Tahoma", 8, "bold"),
                bg="#E74C3C",
                fg="white",
                width=3,
                height=1,
            )
            qty_label.place(x=20, y=25)

        truncated_name = self.truncate_text(item.display_name)
        lbl_nome = tk.Label(
            top_row,
            text=truncated_name,
            font=("Tahoma", 12, "bold"),
            bg="#34495E",
            fg="#F39C12",
            anchor="w",
        )
        lbl_nome.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if len(item.display_name) > 20:
            Tooltip(lbl_nome, item.display_name)

        price_row = tk.Frame(card, bg="#34495E")
        price_row.pack(fill=tk.X, padx=10, pady=(0, 8))

        if item.special_price > 0:
            lbl_original = tk.Label(
                price_row,
                text=f"{item.point}",
                font=("Tahoma", 10, "bold", "overstrike"),
                bg="#34495E",
                fg="#E74C3C",
            )
            lbl_original.pack(side=tk.LEFT)
            lbl_special = tk.Label(
                price_row,
                text=f"{item.special_price}",
                font=("Tahoma", 11, "bold"),
                bg="#34495E",
                fg="#27AE60",
            )
            lbl_special.pack(side=tk.LEFT, padx=(10, 0))
        else:
            lbl_price = tk.Label(
                price_row,
                text=f"{item.point}",
                font=("Tahoma", 11, "bold"),
                bg="#34495E",
                fg="#27AE60",
            )
            lbl_price.pack(side=tk.LEFT)

        def bind_click(widget):
            widget.bind("<Button-1>", lambda e: self.edit_item_popup(item))

        bind_click(card)
        bind_click(top_row)
        bind_click(icon_container)
        bind_click(icon_bg)
        bind_click(lbl_icon)
        bind_click(lbl_nome)
        bind_click(price_row)
        return card

    def _get_total_pages(self):
        total_items = len(self.filtered_items)
        total_pages = max(
            1, (total_items + self.items_per_page - 1) // self.items_per_page
        )
        if (
            total_items > 0
            and total_items % self.items_per_page == 0
            and (self.current_category != 50 or len(self.filtered_items) < 8)
        ):
            total_pages += 1
        return total_pages

    def refresh_cards(self):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        total_items = len(self.filtered_items)
        total_pages = self._get_total_pages()

        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, total_items)
        page_items = self.filtered_items[start_idx:end_idx]

        cols = 3
        rows = 4

        for idx in range(rows * cols):
            col = idx // rows
            row = idx % rows

            if idx < len(page_items):
                item = page_items[idx]
                f = self.build_card(self.cards_frame, item)
                f.grid(row=row, column=col, padx=18, pady=14, sticky="nsew")
            elif (
                self.current_page == total_pages - 1
                and idx == len(page_items)
                and (self.current_category != 50 or len(self.filtered_items) < 8)
            ):
                plus = tk.Frame(
                    self.cards_frame,
                    bg="#34495E",
                    width=260,
                    height=120,
                    highlightthickness=0,
                )
                plus.grid_propagate(False)
                btn = tk.Button(
                    plus,
                    text="+",
                    font=("Tahoma", 32, "bold"),
                    bg="#E74C3C",
                    fg="#fff",
                    width=2,
                    height=1,
                    bd=0,
                    relief="flat",
                    activebackground="#C0392B",
                    activeforeground="#fff",
                    cursor="hand2",
                    command=self.add_item,
                )
                btn.place(relx=0.5, rely=0.5, anchor="center")
                plus.grid(row=row, column=col, padx=18, pady=14, sticky="nsew")
            else:
                empty = tk.Frame(self.cards_frame, bg="#2C3E50", width=260, height=120)
                empty.grid(row=row, column=col, padx=18, pady=14, sticky="nsew")

        for i in range(cols):
            self.cards_frame.grid_columnconfigure(i, weight=1)
        for i in range(rows):
            self.cards_frame.grid_rowconfigure(i, weight=1)

        effective_end_idx = start_idx + len(page_items) if total_items > 0 else 0
        self.update_pagination_controls(
            total_pages,
            total_items,
            start_idx + 1 if total_items > 0 else 0,
            effective_end_idx,
        )

    def update_pagination_controls(
        self, total_pages: int, total_items: int, start_item: int, end_item: int
    ):
        self.page_label.config(text=f"Página {self.current_page + 1} de {total_pages}")
        self.info_label.config(
            text=f"Mostrando {start_item}-{end_item} de {total_items} itens"
        )

        self.btn_prev.config(state="normal")
        self.btn_next.config(state="normal")

    def prev_page(self):
        total_pages = self._get_total_pages()

        if self.current_page > 0:
            self.current_page -= 1
        else:
            self.current_page = total_pages - 1
        self.refresh_cards()
        self.log_message(
            f"Página anterior. Atual: {self.current_page + 1}",
            level="INFO",
            source="UI",
        )

    def next_page(self):
        total_pages = self._get_total_pages()

        if self.current_page < total_pages - 1:
            self.current_page += 1
        else:
            self.current_page = 0
        self.refresh_cards()
        self.log_message(
            f"Próxima página. Atual: {self.current_page + 1}", level="INFO", source="UI"
        )

    def edit_item_popup(self, item: ItemMall):
        ItemDialog(
            self.root, item, self.after_edit_item, self.categories, self, is_edit=True
        )
        self.log_message(
            f"Abrindo editor para o item: {item.display_name} (ID: {item.item_id})",
            level="INFO",
            source="UI",
        )

    def after_edit_item(self, item: ItemMall):
        self.update_item_in_db(item)
        self.load_items_from_db()

    def get_next_index_for_category(self, category_id: int, money_unit: int) -> int:
        category_items = [
            item
            for item in self.items
            if item.item_group == category_id and item.money_unit == money_unit
        ]
        if not category_items:
            return 1
        max_index = max(item.item_index for item in category_items)
        return max_index + 1

    def load_items_from_db(self):
        start_time = time.time()
        if not self.db_conn:
            self.log_message(
                "Não está em modo de banco de dados para carregar itens.",
                level="ERROR",
                source="DB",
            )
            return

        self.items = []
        query = """
            SELECT item_id, item_group, item_index, item_num, money_unit, point, special_price, sell, on_sell_date,
                   not_sell_date, account_num_limit, recognized_percentage, fortune_bag, allow_buy_level,
                   new_account_day_limit, note
            FROM public.itemmall
            ORDER BY item_group, item_index, money_unit;
        """

        def process_rows(cursor):
            for row in cursor.fetchall():
                item_id = row[0]
                item = ItemMall(
                    item_id=item_id,
                    item_group=row[1],
                    item_index=row[2],
                    item_num=row[3],
                    money_unit=row[4],
                    point=row[5],
                    special_price=row[6],
                    sell=row[7],
                    on_sell_date=row[8],
                    not_sell_date=row[9],
                    account_num_limit=row[10],
                    recognized_percentage=row[11],
                    fortune_bag=row[12],
                    allow_buy_level=row[13],
                    new_account_day_limit=row[14],
                    note=row[15],
                    icon_name=self.item_icon_names.get(item_id, ""),
                    display_name=self.item_display_names.get(
                        item_id, f"Item {item_id}"
                    ),
                )
                self.items.append(item)
            self.filter_by_category(self.current_category, preserve_page=True)
            self.log_message(
                f"Carregados {len(self.items)} itens do banco de dados.",
                level="INFO",
                source="DB",
            )

        self._execute_db_operation(
            query,
            msg_success="Itens carregados do DB.",
            msg_fail="Erro ao carregar itens do DB.",
            callback=process_rows,
        )
        end_time = time.time()
        self.log_message(
            f"Tempo de carregamento de itens do DB: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="DB",
        )

    def add_item(self):
        start_time = time.time()
        if self.current_category == 50:
            count_popular = len(
                [
                    item
                    for item in self.items
                    if item.item_group == 50
                    and item.money_unit == self.current_money_unit
                ]
            )
            if count_popular >= 8:
                self.log_message(
                    "Só é permitido até 8 itens na aba POPULAR.",
                    level="WARNING",
                    source="UI",
                )
                return

        next_index = self.get_next_index_for_category(
            self.current_category, self.current_money_unit
        )

        new_item = ItemMall(
            item_id=0,
            item_group=self.current_category,
            item_index=next_index,
            item_num=1,
            money_unit=self.current_money_unit,
            point=(
                ItemDialog._default_point_value if ItemDialog._save_default_point else 0
            ),
            special_price=(
                ItemDialog._default_special_price_value
                if ItemDialog._save_default_special_price
                else 0
            ),
            sell=1,
            on_sell_date=0,
            not_sell_date=0,
            account_num_limit=0,
            recognized_percentage=0.0,
            fortune_bag="",
            allow_buy_level=0,
            new_account_day_limit=0,
            note="",
            icon_name="",
            display_name="",
        )

        ItemDialog(
            self.root,
            new_item,
            self.add_item_callback,
            self.categories,
            self,
            is_edit=False,
        )
        self.log_message(
            "Abrindo diálogo para adicionar novo item.", level="INFO", source="UI"
        )
        end_time = time.time()
        self.log_message(
            f"Tempo para iniciar adição de item: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="UI",
        )

    def add_item_callback(self, new_item: ItemMall):
        start_time = time.time()
        if new_item.item_group == 50:
            count_popular = len(
                [
                    item
                    for item in self.items
                    if item.item_group == 50
                    and item.money_unit == self.current_money_unit
                ]
            )
            if count_popular >= 8 and new_item not in self.items:
                self.log_message(
                    "Só é permitido até 8 itens na aba POPULAR.",
                    level="WARNING",
                    source="UI",
                )
                return

        new_item.icon_name = self.item_icon_names.get(new_item.item_id, "")
        new_item.display_name = self.item_display_names.get(
            new_item.item_id, f"Item {new_item.item_id}"
        )

        self.insert_item_into_db(new_item)
        self.load_items_from_db()
        end_time = time.time()
        self.log_message(
            f"Tempo de callback de adição de item: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="UI",
        )

    def _execute_db_operation(
        self,
        query: str,
        params=None,
        msg_success: str = "",
        msg_fail: str = "",
        callback: Optional[Callable] = None,
    ):
        if not self.db_conn:
            self.log_message(
                msg_fail or "Não conectado ao banco de dados.",
                level="ERROR",
                source="DB",
            )
            return False

        try:
            cursor = self.db_conn.cursor()
            cursor.execute(query, params)
            self.db_conn.commit()
            if callback:
                callback(cursor)
            cursor.close()
            self.log_message(msg_success, level="INFO", source="DB")
            return True
        except PgError as e:
            self.db_conn.rollback()
            self.log_message(f"{msg_fail}: {e}", level="ERROR", source="DB")
            return False
        except Exception as e:
            self.db_conn.rollback()
            self.log_message(
                f"Erro inesperado durante a operação no DB: {str(e)}",
                level="ERROR",
                source="DB",
            )
            return False

    def insert_item_into_db(self, item: ItemMall):
        start_time = time.time()
        insert_query = """
            INSERT INTO public.itemmall (item_id, item_group, item_index, item_num, money_unit, point,
            special_price, sell, on_sell_date, not_sell_date, account_num_limit,
            recognized_percentage, fortune_bag, allow_buy_level, new_account_day_limit, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """

        check_query = """SELECT COUNT(*) FROM public.itemmall WHERE item_group = %s AND item_index = %s AND money_unit = %s;"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute(
                check_query, (item.item_group, item.item_index, item.money_unit)
            )
            count = cursor.fetchone()[0]
            cursor.close()

            if count > 0:
                original_index = item.item_index
                item.item_index = self.get_next_index_for_category(
                    item.item_group, item.money_unit
                )
                self.log_message(
                    f"Já existe um item com a mesma Categoria, Index ({original_index}) e Tipo de Moeda. O item será adicionado com o índice: {item.item_index}.",
                    level="WARNING",
                    source="DB",
                )
        except Exception as e:
            self.log_message(
                f"Erro ao verificar índice do item: {e}", level="ERROR", source="DB"
            )

        params = (
            item.item_id,
            item.item_group,
            item.item_index,
            item.item_num,
            item.money_unit,
            item.point,
            item.special_price,
            item.sell,
            item.on_sell_date,
            item.not_sell_date,
            item.account_num_limit,
            item.recognized_percentage,
            item.fortune_bag,
            item.allow_buy_level,
            item.new_account_day_limit,
            item.note,
        )
        self._execute_db_operation(
            insert_query,
            params,
            msg_success=f"Item {item.item_id} (Index: {item.item_index}) inserido no banco de dados.",
            msg_fail="Erro ao inserir item no DB.",
        )
        end_time = time.time()
        self.log_message(
            f"Tempo de inserção de item no DB: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="DB",
        )

    def update_item_in_db(self, item: ItemMall):
        start_time = time.time()
        update_query = """
            UPDATE public.itemmall SET
                item_id = %s,
                item_group = %s,
                item_index = %s,
                item_num = %s,
                money_unit = %s,
                point = %s,
                special_price = %s,
                sell = %s,
                on_sell_date = %s,
                not_sell_date = %s,
                account_num_limit = %s,
                recognized_percentage = %s,
                fortune_bag = %s,
                allow_buy_level = %s,
                new_account_day_limit = %s,
                note = %s
            WHERE item_id = %s AND item_group = %s AND item_index = %s AND money_unit = %s;
        """

        original_item_id = getattr(item, "_original_item_id", item.item_id)
        original_item_group = getattr(item, "_original_item_group", item.item_group)
        original_item_index = getattr(item, "_original_item_index", item.item_index)
        original_money_unit = getattr(item, "_original_money_unit", item.money_unit)

        params = (
            item.item_id,
            item.item_group,
            item.item_index,
            item.item_num,
            item.money_unit,
            item.point,
            item.special_price,
            item.sell,
            item.on_sell_date,
            item.not_sell_date,
            item.account_num_limit,
            item.recognized_percentage,
            item.fortune_bag,
            item.allow_buy_level,
            item.new_account_day_limit,
            item.note,
            original_item_id,
            original_item_group,
            original_item_index,
            original_money_unit,
        )
        self._execute_db_operation(
            update_query,
            params,
            msg_success=f"Item {item.item_id} (Index: {item.item_index}) atualizado no banco de dados.",
            msg_fail="Erro ao atualizar item no DB.",
        )
        end_time = time.time()
        self.log_message(
            f"Tempo de atualização de item no DB: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="DB",
        )

    def remove_item_by_unique_key(self, item_to_remove: ItemMall):
        self.delete_item_from_db(item_to_remove)
        self.load_items_from_db()

    def delete_item_from_db(self, item_to_remove: ItemMall):
        start_time = time.time()
        delete_query = """
            DELETE FROM public.itemmall
            WHERE item_id = %s AND item_group = %s AND item_index = %s AND money_unit = %s;
        """
        params = (
            item_to_remove.item_id,
            item_to_remove.item_group,
            item_to_remove.item_index,
            item_to_remove.money_unit,
        )
        self._execute_db_operation(
            delete_query,
            params,
            msg_success=f"Item {item_to_remove.item_id} (Index: {item_to_remove.item_index}) excluído do banco de dados.",
            msg_fail="Erro ao excluir item do DB.",
        )
        end_time = time.time()
        self.log_message(
            f"Tempo de exclusão de item do DB: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="DB",
        )

    def run(self):
        self.root.mainloop()


class ItemDialog:
    _default_point_value = 0
    _default_special_price_value = 0
    _save_default_point = False
    _save_default_special_price = False

    def __init__(
        self, parent, item: ItemMall, callback, categories, main_app, is_edit=True
    ):
        self.item = item
        self.callback = callback
        self.categories = categories
        self.main_app = main_app
        self.is_edit = is_edit

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"{'Editar' if is_edit else 'Adicionar'} Item")
        self.dialog.geometry("550x750")
        self.dialog.configure(bg="#2C3E50")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (550 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (750 // 2)
        self.dialog.geometry(f"550x750+{x}+{y}")

        self.save_point_var = tk.BooleanVar(value=ItemDialog._save_default_point)
        self.save_special_price_var = tk.BooleanVar(
            value=ItemDialog._save_default_special_price
        )

        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel_and_save_state)

        self.build_form()

    def build_form(self):
        main_frame = tk.Frame(self.dialog, bg="#2C3E50")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        title_label = tk.Label(
            main_frame,
            text=f"{'Editar Item' if self.is_edit else 'Adicionar Novo Item'}",
            font=("Tahoma", 16, "bold"),
            bg="#2C3E50",
            fg="#F39C12",
        )
        title_label.pack(pady=(0, 20))

        preview_frame = tk.Frame(main_frame, bg="#34495E", relief="solid", bd=1)
        preview_frame.pack(fill=tk.X, pady=(0, 20), padx=10)

        icon_frame = tk.Frame(preview_frame, bg="#34495E")
        icon_frame.pack(side=tk.LEFT, padx=15, pady=10)

        self.icon_container = tk.Frame(
            icon_frame,
            width=50,
            height=50,
            bg=COR_ICON_ITEM if self.item.item_id < 40000 else COR_ICON_ITEMMALL,
            relief="solid",
            bd=1,
        )
        self.icon_container.pack()
        self.icon_container.pack_propagate(False)

        self.icon_label = tk.Label(
            self.icon_container,
            text="?",
            bg=self.icon_container["bg"],
            font=("Tahoma", 20, "bold"),
        )
        self.icon_label.pack(expand=True, fill=tk.BOTH)

        name_frame = tk.Frame(preview_frame, bg="#34495E")
        name_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15), pady=10)

        tk.Label(
            name_frame,
            text="Nome do Item:",
            font=("Tahoma", 10, "bold"),
            bg="#34495E",
            fg="#BDC3C7",
        ).pack(anchor="w")

        self.item_name_label = tk.Label(
            name_frame,
            text="Nenhum item selecionado",
            font=("Tahoma", 12, "bold"),
            bg="#34495E",
            fg="#F39C12",
            wraplength=300,
            justify="left",
        )
        self.item_name_label.pack(anchor="w", fill=tk.X)

        form_frame = tk.Frame(main_frame, bg="#2C3E50")
        form_frame.pack(fill=tk.BOTH, expand=True)
        form_frame.columnconfigure(1, weight=1)

        self.entries = {}
        self.combos = {}
        self.checkbox_buttons = {}

        fields = [
            ("ID do Item:", "item_id", "entry"),
            ("Categoria:", "item_group", "combo_category"),
            ("Index:", "item_index", "entry"),
            ("Quantidade:", "item_num", "entry"),
            ("Tipo de Moeda:", "money_unit", "combo_money"),
            ("Preço (Pontos):", "point", "entry_with_button"),
            ("Preço Especial:", "special_price", "entry_with_button"),
            ("À Venda:", "sell", "combo_sell"),
            ("Nota:", "note", "text_with_button"),
        ]

        row = 0
        for label_text, field_name, field_type in fields:
            lbl = tk.Label(
                form_frame,
                text=label_text,
                font=("Tahoma", 12, "bold"),
                bg="#2C3E50",
                fg="#ECF0F1",
            )
            lbl.grid(row=row, column=0, sticky="nw", pady=(10, 5), padx=(0, 10))

            if field_type == "entry" or field_type == "entry_with_button":
                entry_container = tk.Frame(form_frame, bg="#2C3E50")
                entry_container.grid(row=row, column=1, sticky="ew", pady=(10, 5))

                entry = tk.Entry(
                    entry_container,
                    width=35,
                    font=("Tahoma", 11),
                    bg="#34495E",
                    fg="#ECF0F1",
                    insertbackground="#ECF0F1",
                    relief="flat",
                    bd=5,
                )
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

                if not self.is_edit:
                    if field_name == "point" and ItemDialog._save_default_point:
                        entry.insert(0, str(ItemDialog._default_point_value))
                    elif (
                        field_name == "special_price"
                        and ItemDialog._save_default_special_price
                    ):
                        entry.insert(0, str(ItemDialog._default_special_price_value))
                    else:
                        val = getattr(self.item, field_name)
                        entry.insert(0, str(val))
                else:
                    val = getattr(self.item, field_name)
                    entry.insert(0, str(val))

                self.entries[field_name] = entry
                if field_name == "item_id":
                    entry.bind("<KeyRelease>", self.update_item_preview)
                    entry.bind("<FocusOut>", self.update_item_preview)
                if field_name == "item_index":
                    if not self.is_edit:
                        Tooltip(entry, f"Próximo índice sugerido: {val}")
                    else:
                        Tooltip(entry, f"Índice atual na categoria")

                if field_type == "entry_with_button":
                    if field_name == "point":
                        chk_var = self.save_point_var
                    elif field_name == "special_price":
                        chk_var = self.save_special_price_var
                    else:
                        chk_var = None

                    if chk_var:
                        initial_text = "🔒" if chk_var.get() else "🔓"
                        initial_bg = "#E74C3C" if chk_var.get() else "#27AE60"
                        lock_button = tk.Button(
                            entry_container,
                            text=initial_text,
                            font=("Tahoma", 14),
                            width=2,
                            height=1,
                            bg=initial_bg,
                            fg="#fff",
                            relief="flat",
                            bd=0,
                            command=lambda f=field_name: self.toggle_lock_button(f),
                        )
                        lock_button.pack(side=tk.RIGHT, padx=(5, 0))
                        self.checkbox_buttons[field_name] = lock_button

            elif field_type == "combo_category":
                combo = ttk.Combobox(
                    form_frame,
                    values=[
                        f"{cat_id} - {cat_name}" for cat_id, cat_name in self.categories
                    ],
                    width=32,
                    font=("Tahoma", 11),
                    state="readonly",
                )
                combo.grid(row=row, column=1, sticky="ew", pady=(10, 5))
                current_cat = next(
                    (
                        f"{cat_id} - {cat_name}"
                        for cat_id, cat_name in self.categories
                        if cat_id == self.item.item_group
                    ),
                    None,
                )
                if current_cat:
                    combo.set(current_cat)
                combo.bind("<<ComboboxSelected>>", self.on_category_change)
                self.combos[field_name] = combo
            elif field_type == "combo_money":
                combo = ttk.Combobox(
                    form_frame,
                    values=["1 - Cash Point", "2 - Bônus Point"],
                    width=32,
                    font=("Tahoma", 11),
                    state="readonly",
                )
                combo.grid(row=row, column=1, sticky="ew", pady=(10, 5))
                combo.set(
                    f"{self.item.money_unit} - {'Cash Point' if self.item.money_unit == 1 else 'Bônus Point'}"
                )
                combo.bind("<<ComboboxSelected>>", self.on_money_unit_change)
                self.combos[field_name] = combo
            elif field_type == "combo_sell":
                combo = ttk.Combobox(
                    form_frame,
                    values=["1 - Sim", "0 - Não"],
                    width=32,
                    font=("Tahoma", 11),
                    state="readonly",
                )
                combo.grid(row=row, column=1, sticky="ew", pady=(10, 5))
                combo.set(
                    f"{self.item.sell} - {'Sim' if self.item.sell == 1 else 'Não'}"
                )
                self.combos[field_name] = combo
            elif field_type == "text_with_button":
                text_frame = tk.Frame(form_frame, bg="#2C3E50")
                text_frame.grid(row=row, column=1, sticky="ew", pady=(10, 5))

                text_widget = tk.Text(
                    text_frame,
                    width=35,
                    height=3,
                    font=("Tahoma", 11),
                    bg="#34495E",
                    fg="#ECF0F1",
                    insertbackground="#ECF0F1",
                    relief="flat",
                    bd=5,
                )
                text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                text_widget.insert("1.0", self.item.note)
                self.entries[field_name] = text_widget

                clear_button = tk.Button(
                    text_frame,
                    text="Limpar",
                    command=self.clear_note,
                    bg="#E74C3C",
                    fg="#fff",
                    font=("Tahoma", 9, "bold"),
                    relief="flat",
                    padx=5,
                    pady=2,
                    cursor="hand2",
                )
                clear_button.pack(side=tk.RIGHT, padx=(5, 0), anchor="n")

                Tooltip(text_widget, "Campo para anotações do item.")
            row += 1

        button_frame = tk.Frame(main_frame, bg="#2C3E50")
        button_frame.pack(fill=tk.X, pady=(30, 0))

        if self.is_edit:
            save_btn = tk.Button(
                button_frame,
                text="Salvar Alterações",
                command=self.save,
                bg="#27AE60",
                fg="#fff",
                font=("Tahoma", 12, "bold"),
                relief="flat",
                padx=20,
                pady=8,
                cursor="hand2",
            )
            save_btn.pack(side=tk.LEFT, padx=(0, 10))

            delete_btn = tk.Button(
                button_frame,
                text="Excluir Item",
                command=self.delete_item,
                bg="#E74C3C",
                fg="#fff",
                font=("Tahoma", 12, "bold"),
                relief="flat",
                padx=20,
                pady=8,
                cursor="hand2",
            )
            delete_btn.pack(side=tk.LEFT, padx=(0, 10))
        else:
            add_btn = tk.Button(
                button_frame,
                text="Adicionar Item",
                command=self.save,
                bg="#27AE60",
                fg="#fff",
                font=("Tahoma", 12, "bold"),
                relief="flat",
                padx=20,
                pady=8,
                cursor="hand2",
            )
            add_btn.pack(side=tk.LEFT, padx=(0, 10))

        cancel_btn = tk.Button(
            button_frame,
            text="Cancelar",
            command=self.cancel_and_save_state,
            bg="#95A5A6",
            fg="#fff",
            font=("Tahoma", 12, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
        )
        cancel_btn.pack(side=tk.RIGHT)

        self.update_item_preview()

    def toggle_lock_button(self, field_name):
        if field_name == "point":
            chk_var = self.save_point_var
            button = self.checkbox_buttons["point"]
        elif field_name == "special_price":
            chk_var = self.save_special_price_var
            button = self.checkbox_buttons["special_price"]
        else:
            return

        chk_var.set(not chk_var.get())
        if chk_var.get():
            button.config(text="🔒", bg="#E74C3C")
        else:
            button.config(text="🔓", bg="#27AE60")

    def clear_note(self):
        self.entries["note"].delete("1.0", tk.END)
        self.main_app.log_message("Campo 'Nota' limpo.", level="INFO", source="UI")

    def cancel_and_save_state(self):
        ItemDialog._save_default_point = self.save_point_var.get()
        ItemDialog._save_default_special_price = self.save_special_price_var.get()

        if not self.is_edit and hasattr(self.item, "_original_item_id"):
            delattr(self.item, "_original_item_id")
            delattr(self.item, "_original_item_group")
            delattr(self.item, "_original_item_index")
            delattr(self.item, "_original_money_unit")

        self.dialog.destroy()

    def update_item_preview(self, event=None):
        try:
            item_id_text = self.entries["item_id"].get().strip()
            if item_id_text and item_id_text.isdigit():
                item_id = int(item_id_text)
                item_name = self.main_app.item_display_names.get(
                    item_id, f"Item {item_id}"
                )
                icon_name = self.main_app.item_icon_names.get(item_id, "")

                self.item_name_label.config(text=item_name)

                icon_img = self.main_app.load_item_icon(icon_name, item_id)
                self.icon_container.config(
                    bg=COR_ICON_ITEM if item_id < 40000 else COR_ICON_ITEMMALL
                )
                if icon_img:
                    self.icon_label.config(
                        image=icon_img, text="", bg=self.icon_container["bg"]
                    )
                    self.icon_label.image = icon_img
                else:
                    self.icon_label.config(
                        image="", text="?", bg=self.icon_container["bg"]
                    )
                    self.icon_label.image = None
            else:
                self.item_name_label.config(text="ID do Item inválido ou vazio")
                self.icon_label.config(image="", text="?", bg=self.icon_container["bg"])
                self.icon_label.image = None
        except Exception as e:
            self.main_app.log_message(
                f"Erro ao atualizar pré-visualização: {e}", level="ERROR", source="UI"
            )

    def on_category_change(self, event):
        selected_category_str = self.combos["item_group"].get()
        try:
            selected_category_id = int(selected_category_str.split(" - ")[0])
            selected_money_unit_str = self.combos["money_unit"].get()
            selected_money_unit_id = int(selected_money_unit_str.split(" - ")[0])

            next_index = self.main_app.get_next_index_for_category(
                selected_category_id, selected_money_unit_id
            )
            self.entries["item_index"].delete(0, tk.END)
            self.entries["item_index"].insert(0, str(next_index))
            self.main_app.log_message(
                f"Categoria alterada para {selected_category_str}. Índice sugerido: {next_index}",
                level="INFO",
                source="UI",
            )

        except ValueError:
            self.main_app.log_message(
                "Valor inválido na categoria selecionada.", level="ERROR", source="UI"
            )

    def on_money_unit_change(self, event):
        selected_category_str = self.combos["item_group"].get()
        try:
            selected_category_id = int(selected_category_str.split(" - ")[0])
            selected_money_unit_str = self.combos["money_unit"].get()
            selected_money_unit_id = int(selected_money_unit_str.split(" - ")[0])
            next_index = self.main_app.get_next_index_for_category(
                selected_category_id, selected_money_unit_id
            )
            self.entries["item_index"].delete(0, tk.END)
            self.entries["item_index"].insert(0, str(next_index))
            self.main_app.log_message(
                f"Tipo de moeda alterado para {selected_money_unit_str}. Índice sugerido: {next_index}",
                level="INFO",
                source="UI",
            )

        except ValueError:
            self.main_app.log_message(
                "Valor inválido na unidade de moeda selecionada.",
                level="ERROR",
                source="UI",
            )

    def save(self):
        start_time = time.time()
        try:
            item_id = int(self.entries["item_id"].get())
            item_group = int(self.combos["item_group"].get().split(" - ")[0])
            item_index = int(self.entries["item_index"].get())
            item_num = int(self.entries["item_num"].get())
            money_unit = int(self.combos["money_unit"].get().split(" - ")[0])
            point = int(self.entries["point"].get())
            special_price = int(self.entries["special_price"].get())
            sell = int(self.combos["sell"].get().split(" - ")[0])
            note = self.entries["note"].get("1.0", tk.END).strip()

            if (
                item_id < 0
                or item_group < 0
                or item_index < 0
                or item_num < 0
                or money_unit < 0
                or point < 0
                or special_price < 0
                or sell not in [0, 1]
            ):
                messagebox.showwarning(
                    "Entrada Inválida",
                    "Valores numéricos não podem ser negativos. 'À Venda' deve ser 0 ou 1.",
                )
                self.main_app.log_message(
                    "Valores numéricos não podem ser negativos. 'À Venda' deve ser 0 ou 1.",
                    level="ERROR",
                    source="UI",
                )
                return

            if item_group == 50:
                current_popular_items_count = len(
                    [
                        item
                        for item in self.main_app.items
                        if item.item_group == 50 and item.money_unit == money_unit
                    ]
                )
                if current_popular_items_count >= 8:
                    if self.is_edit:
                        is_current_item_in_popular = (
                            self.item.item_group == 50
                            and self.item.money_unit == money_unit
                        )
                        if (
                            item_group == 50
                            and not is_current_item_in_popular
                            and current_popular_items_count >= 8
                        ):
                            messagebox.showwarning(
                                "Limite de Itens",
                                "A aba POPULAR permite um máximo de 8 itens. Não é possível adicionar mais.",
                            )
                            self.main_app.log_message(
                                "Tentativa de adicionar mais de 8 itens na aba POPULAR.",
                                level="WARNING",
                                source="UI",
                            )
                            return
                        elif (
                            item_group == 50
                            and is_current_item_in_popular
                            and current_popular_items_count > 8
                        ):
                            messagebox.showwarning(
                                "Limite de Itens",
                                "A aba POPULAR permite um máximo de 8 itens. Não é possível ter mais do que isso.",
                            )
                            self.main_app.log_message(
                                "Tentativa de alterar um item na aba POPULAR, resultando em mais de 8 itens.",
                                level="WARNING",
                                source="UI",
                            )
                            return
                    else:
                        messagebox.showwarning(
                            "Limite de Itens",
                            "A aba POPULAR permite um máximo de 8 itens. Não é possível adicionar mais.",
                        )
                        self.main_app.log_message(
                            "Tentativa de adicionar mais de 8 itens na aba POPULAR.",
                            level="WARNING",
                            source="UI",
                        )
                        return

            if self.is_edit:
                self.item._original_item_id = self.item.item_id
                self.item._original_item_group = self.item.item_group
                self.item._original_item_index = self.item.item_index
                self.item._original_money_unit = self.item.money_unit
            else:
                pass

            self.item.item_id = item_id
            self.item.item_group = item_group
            self.item.item_index = item_index
            self.item.item_num = item_num
            self.item.money_unit = money_unit
            self.item.point = point
            self.item.special_price = special_price
            self.item.sell = sell
            self.item.note = note
            self.item.icon_name = self.main_app.item_icon_names.get(item_id, "")
            self.item.display_name = self.main_app.item_display_names.get(
                item_id, f"Item {item_id}"
            )

            if self.save_point_var.get():
                ItemDialog._default_point_value = point
            else:
                ItemDialog._default_point_value = 0
            ItemDialog._save_default_point = self.save_point_var.get()

            if self.save_special_price_var.get():
                ItemDialog._default_special_price_value = special_price
            else:
                ItemDialog._default_special_price_value = 0
            ItemDialog._save_default_special_price = self.save_special_price_var.get()

            self.callback(self.item)
            self.main_app.log_message(
                f"Item {self.item.display_name} (ID: {self.item.item_id}) salvo com sucesso.",
                level="INFO",
                source="UI",
            )
            self.dialog.destroy()
        except ValueError as e:
            messagebox.showwarning(
                "Entrada Inválida",
                f"Erro de tipo: Verifique se todos os campos numéricos estão corretos. Detalhe: {e}",
            )
            self.main_app.log_message(
                f"Entrada inválida. Verifique os campos numéricos. {e}",
                level="ERROR",
                source="UI",
            )
        except Exception as e:
            messagebox.showerror(
                "Erro Inesperado", f"Ocorreu um erro ao salvar o item: {e}"
            )
            self.main_app.log_message(
                f"Ocorreu um erro ao salvar o item: {e}", level="ERROR", source="UI"
            )
        finally:
            end_time = time.time()
            self.main_app.log_message(
                f"Tempo de salvamento/adição de item: {end_time - start_time:.4f} segundos",
                level="INFO",
                source="UI",
            )

    def delete_item(self):
        start_time = time.time()
        if messagebox.askyesno(
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o item '{self.item.display_name}' (ID: {self.item.item_id})?",
        ):
            self.main_app.remove_item_by_unique_key(self.item)
            self.main_app.log_message(
                f"Item {self.item.display_name} (ID: {self.item.item_id}) excluído.",
                level="INFO",
                source="UI",
            )
            self.dialog.destroy()
        else:
            self.main_app.log_message(
                "Exclusão de item cancelada pelo usuário.",
                level="INFO",
                source="UI",
            )
        end_time = time.time()
        self.main_app.log_message(
            f"Tempo de exclusão de item: {end_time - start_time:.4f} segundos",
            level="INFO",
            source="UI",
        )


if __name__ == "__main__":
    root = tk.Tk()
    login_app = LoginScreen(root)
    root.mainloop()