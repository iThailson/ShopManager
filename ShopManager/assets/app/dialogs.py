from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from .data import connect_postgres, load_env, save_env
from .models import CATEGORIES, ItemMall
from .paths import DirectoryValidator, RegistryManager
from .settings import CurrencyOption, DEFAULT_CURRENCY_OPTIONS, SettingsManager


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectar ao Banco")
        self.setMinimumWidth(460)
        self.connection = None
        self.game_directory: Optional[str] = None
        self.registry = RegistryManager()

        values = load_env()
        saved_game_dir = self.registry.read_path()
        if saved_game_dir and DirectoryValidator.is_valid_game_directory(saved_game_dir):
            self.game_directory = saved_game_dir

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.host = QLineEdit(values.get("DB_HOST", "localhost"))
        self.port = QLineEdit(values.get("DB_PORT", "5432"))
        self.port.setValidator(QIntValidator(1, 65535, self))
        self.user = QLineEdit(values.get("DB_USER", "postgres"))
        self.password = QLineEdit(values.get("DB_PASSWORD", ""))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.game_dir_label = QLabel(self.game_directory or "Nenhuma pasta selecionada")
        self.game_dir_label.setWordWrap(True)

        choose_dir = QPushButton("Selecionar pasta do jogo")
        choose_dir.clicked.connect(self.choose_game_directory)

        form.addRow("Host:", self.host)
        form.addRow("Porta:", self.port)
        form.addRow("Usuário:", self.user)
        form.addRow("Senha:", self.password)
        form.addRow("Pasta do jogo:", self.game_dir_label)
        layout.addLayout(form)
        layout.addWidget(choose_dir)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Conectar")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.connect)
        layout.addWidget(buttons)

    def choose_game_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Selecionar diretório do Grand Fantasia",
            self.game_directory or str(Path.home()),
        )
        if not selected:
            return
        if not DirectoryValidator.is_valid_game_directory(selected):
            QMessageBox.warning(
                self,
                "Pasta inválida",
                "A pasta precisa conter GrandFantasia.exe, UI/itemicon, data/db e data/Translate.",
            )
            return
        self.game_directory = selected
        self.registry.write_path(selected)
        self.game_dir_label.setText(selected)

    def connect(self) -> None:
        if not self.game_directory:
            self.choose_game_directory()
            if not self.game_directory:
                return

        host = self.host.text().strip() or "localhost"
        port = self.port.text().strip() or "5432"
        user = self.user.text().strip() or "postgres"
        password = self.password.text()
        try:
            self.connection = connect_postgres(host, port, user, password)
            save_env(host, port, user, password)
            self.accept()
        except ModuleNotFoundError as exc:
            QMessageBox.critical(
                self,
                "Dependência ausente",
                f"Instale a dependência necessária antes de abrir a loja:\n{exc.name}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro de conexão",
                f"Não foi possível conectar ao PostgreSQL.\n\n{type(exc).__name__}: {exc}",
            )


class CurrencySettingsDialog(QDialog):
    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.rows: Dict[str, Dict[str, QLineEdit]] = {}
        self.setWindowTitle("Configurar Moedas")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(QLabel("Loja"), 0, 0)
        grid.addWidget(QLabel("ID"), 0, 1)
        grid.addWidget(QLabel("Nome da Moeda"), 0, 2)
        grid.addWidget(QLabel("Nome do Botão"), 0, 3)

        for row_index, option in enumerate(settings.currency_options, start=1):
            grid.addWidget(QLabel(option.key), row_index, 0)
            id_entry = QLineEdit(str(option.id))
            id_entry.setValidator(QIntValidator(1, 999999, self))
            name_entry = QLineEdit(option.name)
            store_entry = QLineEdit(option.store_name)
            grid.addWidget(id_entry, row_index, 1)
            grid.addWidget(name_entry, row_index, 2)
            grid.addWidget(store_entry, row_index, 3)
            self.rows[option.key] = {
                "id": id_entry,
                "name": name_entry,
                "store_name": store_entry,
            }

        layout.addLayout(grid)
        restore = QPushButton("Restaurar padrão")
        restore.clicked.connect(self.restore_defaults)
        layout.addWidget(restore, alignment=Qt.AlignmentFlag.AlignLeft)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.save)
        layout.addWidget(buttons)

    def restore_defaults(self) -> None:
        defaults = {option.key: option for option in DEFAULT_CURRENCY_OPTIONS}
        for key, row in self.rows.items():
            option = defaults[key]
            row["id"].setText(str(option.id))
            row["name"].setText(option.name)
            row["store_name"].setText(option.store_name)

    def save(self) -> None:
        options = []
        ids = set()
        for fallback in DEFAULT_CURRENCY_OPTIONS:
            row = self.rows[fallback.key]
            money_id = int(row["id"].text() or fallback.id)
            if money_id in ids:
                QMessageBox.warning(self, "IDs duplicados", "Cada moeda precisa ter um ID diferente.")
                return
            ids.add(money_id)
            options.append(
                CurrencyOption(
                    key=fallback.key,
                    id=money_id,
                    name=row["name"].text().strip() or fallback.name,
                    store_name=row["store_name"].text().strip() or fallback.store_name,
                )
            )
        self.settings.save_currency_options(options)
        self.accept()


class ItemDialog(QDialog):
    _default_point_value = 0
    _default_special_price_value = 0
    _save_default_point = False
    _save_default_special_price = False

    def __init__(
        self,
        item: ItemMall,
        currency_options: Iterable[str],
        get_next_index: Callable[[int, int], int],
        load_icon: Callable[[str, int, int], Optional[QPixmap]],
        item_names: Dict[int, str],
        item_icons: Dict[int, str],
        is_edit: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.original_item = item
        self.item = replace(item)
        self.currency_options = list(currency_options)
        self.get_next_index = get_next_index
        self.load_icon = load_icon
        self.item_names = item_names
        self.item_icons = item_icons
        self.is_edit = is_edit
        self.deleted = False

        self.setWindowTitle("Editar Item" if is_edit else "Adicionar Item")
        self.setMinimumSize(640, 640)
        self._build()
        self._populate()
        self._update_preview()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        preview_box = QHBoxLayout()
        self.preview_icon = QLabel("?")
        self.preview_icon.setFixedSize(46, 46)
        self.preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_name = QLabel("Nenhum item selecionado")
        self.preview_name.setStyleSheet("font-weight: 700;")
        preview_box.addWidget(self.preview_icon)
        preview_box.addWidget(self.preview_name, stretch=1)
        layout.addLayout(preview_box)

        form = QFormLayout()
        self.item_id = QLineEdit()
        self.item_id.setValidator(QIntValidator(0, 999999999, self))
        self.category = QComboBox()
        for category_id, label in CATEGORIES:
            self.category.addItem(f"{category_id} - {label}", category_id)
        self.item_index = QSpinBox()
        self.item_index.setRange(0, 999999)
        self.item_num = QSpinBox()
        self.item_num.setRange(0, 999999)
        self.money_unit = QComboBox()
        self.money_unit.addItems(self.currency_options)
        self.point = QSpinBox()
        self.point.setRange(0, 999999999)
        self.special_price = QSpinBox()
        self.special_price.setRange(0, 999999999)
        self.sell = QComboBox()
        self.sell.addItems(["1 - Sim", "0 - Não"])
        self.on_sell_date = QSpinBox()
        self.on_sell_date.setRange(0, 999999999)
        self.not_sell_date = QSpinBox()
        self.not_sell_date.setRange(0, 999999999)
        self.account_num_limit = QSpinBox()
        self.account_num_limit.setRange(0, 999999999)
        self.recognized_percentage = QLineEdit()
        self.fortune_bag = QLineEdit()
        self.allow_buy_level = QSpinBox()
        self.allow_buy_level.setRange(0, 999999)
        self.new_account_day_limit = QSpinBox()
        self.new_account_day_limit.setRange(0, 999999)
        self.note = QTextEdit()
        self.note.setFixedHeight(86)

        form.addRow("ID do Item:", self.item_id)
        form.addRow("Categoria:", self.category)
        form.addRow("Index:", self.item_index)
        form.addRow("Quantidade:", self.item_num)
        form.addRow("Tipo de Moeda:", self.money_unit)
        form.addRow("Preço:", self.point)
        form.addRow("Preço Especial:", self.special_price)
        form.addRow("À Venda:", self.sell)
        form.addRow("Início Venda:", self.on_sell_date)
        form.addRow("Fim Venda:", self.not_sell_date)
        form.addRow("Limite por Conta:", self.account_num_limit)
        form.addRow("Porcentagem Reconhecida:", self.recognized_percentage)
        form.addRow("Fortune Bag:", self.fortune_bag)
        form.addRow("Nível para Comprar:", self.allow_buy_level)
        form.addRow("Limite Nova Conta:", self.new_account_day_limit)
        form.addRow("Nota:", self.note)
        layout.addLayout(form)

        options = QHBoxLayout()
        self.save_point = QCheckBox("Manter preço como padrão")
        self.save_special = QCheckBox("Manter preço especial como padrão")
        options.addWidget(self.save_point)
        options.addWidget(self.save_special)
        layout.addLayout(options)

        action_row = QHBoxLayout()
        if self.is_edit:
            delete = QPushButton("Excluir")
            delete.clicked.connect(self.delete)
            action_row.addWidget(delete)
        action_row.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.save)
        action_row.addWidget(buttons)
        layout.addLayout(action_row)

        self.item_id.textChanged.connect(self._update_preview)
        self.category.currentIndexChanged.connect(self._suggest_index)
        self.money_unit.currentIndexChanged.connect(self._suggest_index)

    def _populate(self) -> None:
        self.item_id.setText(str(self.item.item_id))
        self._set_combo_by_data(self.category, self.item.item_group)
        self.item_index.setValue(self.item.item_index)
        self.item_num.setValue(self.item.item_num)
        self._set_money_combo(self.item.money_unit)
        self.point.setValue(
            self.item.point
            if self.is_edit or not self._save_default_point
            else self._default_point_value
        )
        self.special_price.setValue(
            self.item.special_price
            if self.is_edit or not self._save_default_special_price
            else self._default_special_price_value
        )
        self.sell.setCurrentIndex(0 if self.item.sell else 1)
        self.on_sell_date.setValue(self.item.on_sell_date)
        self.not_sell_date.setValue(self.item.not_sell_date)
        self.account_num_limit.setValue(self.item.account_num_limit)
        self.recognized_percentage.setText(str(self.item.recognized_percentage))
        self.fortune_bag.setText(self.item.fortune_bag)
        self.allow_buy_level.setValue(self.item.allow_buy_level)
        self.new_account_day_limit.setValue(self.item.new_account_day_limit)
        self.note.setPlainText(self.item.note)
        self.save_point.setChecked(self._save_default_point)
        self.save_special.setChecked(self._save_default_special_price)

    def _set_combo_by_data(self, combo: QComboBox, value: int) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _set_money_combo(self, money_unit: int) -> None:
        prefix = f"{money_unit} - "
        for index in range(self.money_unit.count()):
            if self.money_unit.itemText(index).startswith(prefix):
                self.money_unit.setCurrentIndex(index)
                return

    def _current_money_unit(self) -> int:
        text = self.money_unit.currentText()
        try:
            return int(text.split(" - ", 1)[0])
        except (ValueError, IndexError):
            return 1

    def _suggest_index(self) -> None:
        if self.is_edit:
            return
        category_id = int(self.category.currentData())
        money_unit = self._current_money_unit()
        self.item_index.setValue(self.get_next_index(category_id, money_unit))

    def _update_preview(self) -> None:
        try:
            item_id = int(self.item_id.text() or 0)
        except ValueError:
            item_id = 0
        name = self.item_names.get(item_id, f"Item {item_id}" if item_id else "Nenhum item selecionado")
        icon_name = self.item_icons.get(item_id, "")
        self.preview_name.setText(name)
        pixmap = self.load_icon(icon_name, item_id, 42) if icon_name else None
        if pixmap:
            self.preview_icon.setPixmap(pixmap)
            self.preview_icon.setText("")
        else:
            self.preview_icon.setPixmap(QPixmap())
            self.preview_icon.setText("?")

    def save(self) -> None:
        try:
            recognized_percentage = float(
                (self.recognized_percentage.text() or "0").replace(",", ".")
            )
        except ValueError:
            QMessageBox.warning(self, "Valor inválido", "Porcentagem reconhecida precisa ser numérica.")
            return

        item_id = int(self.item_id.text() or 0)
        if item_id <= 0:
            QMessageBox.warning(self, "Item inválido", "Informe um ID de item válido.")
            return

        if self.is_edit:
            self.item._original_item_id = self.original_item.item_id
            self.item._original_item_group = self.original_item.item_group
            self.item._original_item_index = self.original_item.item_index
            self.item._original_money_unit = self.original_item.money_unit

        self.item.item_id = item_id
        self.item.item_group = int(self.category.currentData())
        self.item.item_index = int(self.item_index.value())
        self.item.item_num = int(self.item_num.value())
        self.item.money_unit = self._current_money_unit()
        self.item.point = int(self.point.value())
        self.item.special_price = int(self.special_price.value())
        self.item.sell = 1 if self.sell.currentIndex() == 0 else 0
        self.item.on_sell_date = int(self.on_sell_date.value())
        self.item.not_sell_date = int(self.not_sell_date.value())
        self.item.account_num_limit = int(self.account_num_limit.value())
        self.item.recognized_percentage = recognized_percentage
        self.item.fortune_bag = self.fortune_bag.text()
        self.item.allow_buy_level = int(self.allow_buy_level.value())
        self.item.new_account_day_limit = int(self.new_account_day_limit.value())
        self.item.note = self.note.toPlainText().strip()
        self.item.icon_name = self.item_icons.get(item_id, "")
        self.item.display_name = self.item_names.get(item_id, f"Item {item_id}")

        ItemDialog._save_default_point = self.save_point.isChecked()
        ItemDialog._save_default_special_price = self.save_special.isChecked()
        ItemDialog._default_point_value = self.item.point if self.save_point.isChecked() else 0
        ItemDialog._default_special_price_value = (
            self.item.special_price if self.save_special.isChecked() else 0
        )
        self.accept()

    def delete(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Excluir item",
            f"Excluir '{self.original_item.display_name}' (ID {self.original_item.item_id})?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.deleted = True
            self.accept()
