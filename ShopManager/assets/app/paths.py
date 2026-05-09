import os
from pathlib import Path
from typing import Optional


APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR.parent
PROJECT_DIR = ASSETS_DIR.parent
UI_DIR = ASSETS_DIR / "ui"
ENV_PATH = PROJECT_DIR / ".env"


class DirectoryValidator:
    @staticmethod
    def is_valid_game_directory(directory_path: str) -> bool:
        base = Path(directory_path)
        return (
            base.is_dir()
            and (base / "GrandFantasia.exe").exists()
            and (base / "UI" / "itemicon").is_dir()
            and (base / "data" / "db").is_dir()
            and (base / "data" / "Translate").is_dir()
        )


class RegistryManager:
    def __init__(self, app_name="StoreManager", key_name="GrandFantasiaPath"):
        self.app_name = app_name
        self.key_name = key_name
        self.registry_path = rf"Software\{self.app_name}"

    def read_path(self) -> Optional[str]:
        if os.name != "nt":
            return None
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.registry_path, 0, winreg.KEY_READ
            )
            path, _ = winreg.QueryValueEx(key, self.key_name)
            winreg.CloseKey(key)
            return path
        except Exception:
            return None

    def write_path(self, path: str) -> None:
        if os.name != "nt":
            return
        try:
            import winreg

            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.registry_path)
            winreg.SetValueEx(key, self.key_name, 0, winreg.REG_SZ, path)
            winreg.CloseKey(key)
        except Exception:
            return
