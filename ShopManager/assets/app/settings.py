import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional


APP_NAME = "ShopManager"
SETTINGS_FILENAME = "settings.json"


@dataclass
class CurrencyOption:
    key: str
    id: int
    name: str
    store_name: str

    @property
    def combo_label(self) -> str:
        return f"{self.id} - {self.name}"


DEFAULT_CURRENCY_OPTIONS = [
    CurrencyOption("cash", 1, "Cash Point", "Loja de Itens"),
    CurrencyOption("bonus", 2, "Bônus Point", "Loja de Bônus"),
    CurrencyOption("free", 3, "Moeda Grátis", "Gratuitos"),
]


class SettingsManager:
    def __init__(self, settings_path: Optional[Path] = None):
        self.settings_path = settings_path or self.default_settings_path()
        self.currency_options = self.load_currency_options()

    @staticmethod
    def default_settings_path() -> Path:
        appdata = os.getenv("APPDATA")
        base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base_dir / APP_NAME / SETTINGS_FILENAME

    def currency_ids(self) -> List[int]:
        return [option.id for option in self.currency_options]

    def combo_values(self) -> List[str]:
        return [option.combo_label for option in self.currency_options]

    def option_by_id(self, money_unit: int) -> Optional[CurrencyOption]:
        return next((opt for opt in self.currency_options if opt.id == money_unit), None)

    def format_money_unit_option(self, money_unit: int) -> str:
        option = self.option_by_id(money_unit)
        return option.combo_label if option else f"{money_unit} - Moeda {money_unit}"

    def store_label(self, money_unit: int) -> str:
        option = self.option_by_id(money_unit)
        return option.store_name if option else f"Loja {money_unit}"

    def load_currency_options(self) -> List[CurrencyOption]:
        data = self._read_settings()
        raw_options = data.get("currency_options", [])
        options = []

        for fallback, raw in zip(DEFAULT_CURRENCY_OPTIONS, raw_options):
            try:
                options.append(
                    CurrencyOption(
                        key=fallback.key,
                        id=int(raw.get("id", fallback.id)),
                        name=str(raw.get("name", fallback.name)).strip()
                        or fallback.name,
                        store_name=str(
                            raw.get("store_name", fallback.store_name)
                        ).strip()
                        or fallback.store_name,
                    )
                )
            except (TypeError, ValueError):
                options.append(fallback)

        while len(options) < len(DEFAULT_CURRENCY_OPTIONS):
            options.append(DEFAULT_CURRENCY_OPTIONS[len(options)])

        return self._dedupe_or_default(options)

    def save_currency_options(self, options: Iterable[CurrencyOption]) -> None:
        validated = self._dedupe_or_default(list(options))
        data = self._read_settings()
        data["currency_options"] = [asdict(option) for option in validated]
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.currency_options = validated

    def _read_settings(self) -> dict:
        if not self.settings_path.exists():
            return {}
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _dedupe_or_default(options: List[CurrencyOption]) -> List[CurrencyOption]:
        if len({option.id for option in options}) != len(options):
            return list(DEFAULT_CURRENCY_OPTIONS)
        return options
