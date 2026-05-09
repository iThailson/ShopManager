import math
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
)

from .data import ItemMallRepository, format_exception, load_item_mappings
from .dialogs import CurrencySettingsDialog, ItemDialog
from .models import CATEGORIES, ItemMall
from .settings import SettingsManager
from .skin import GameSkin


class HitRectItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF, callback, double_callback=None, tooltip: str = ""):
        super().__init__(rect)
        self.callback = callback
        self.double_callback = double_callback
        if tooltip:
            self.setToolTip(tooltip)
        self.setBrush(QColor(0, 0, 0, 1))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setOpacity(0.01)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):
        if self.callback:
            self.callback()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.double_callback:
            self.double_callback()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ShopWindow(QMainWindow):
    FONT_FAMILY = "Tahoma"
    MAIN_FONT_SIZE = 9
    SMALL_FONT_SIZE = 8
    HID_FONT_SIZE = 12
    QUALITY_COLORS = {
        0: "#ffffff",
        1: "#939393",
        2: "#6fe11c",
        3: "#21abeb",
        4: "#ff7b00",
        5: "#eae100",
        6: "#fc14ec",
        7: "#ff0000",
        8: "#ffffff",
    }

    CATEGORY_BUTTONS = {
        1: 5001,
        9: 5009,
        2: 5002,
        3: 5003,
        4: 5004,
        5: 5005,
        6: 5006,
        7: 5007,
        8: 5008,
    }

    def __init__(self, connection, game_directory: str):
        super().__init__()
        self.connection = connection
        self.game_directory = game_directory
        self.settings = SettingsManager()
        self.skin = GameSkin()
        self.scale = 1.0
        self.repository = ItemMallRepository(connection, self.log_message)
        self.current_lang_folder = "Translate_PT"
        self.current_category = 1
        self.current_page = 0
        self.current_money_unit = self.settings.currency_ids()[0]
        self.items: List[ItemMall] = []
        self.filtered_items: List[ItemMall] = []
        self.popular_items: List[ItemMall] = []
        self.item_icon_names: Dict[int, str] = {}
        self.item_display_names: Dict[int, str] = {}
        self.item_qualities: Dict[int, int] = {}
        self.icon_cache: Dict[str, QPixmap] = {}
        self.test_balances = {"points": 55033, "bonus": 8993, "free": 0}

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.RenderHint.TextAntialiasing)
        self.view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.view.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QColor("#d8ca96"))
        self.setCentralWidget(self.view)
        self._enable_accelerated_viewport()

        width, height = self.skin.scene_size(self.scale)
        self.scene.setSceneRect(0, 0, width, height)
        self.view.setFixedSize(width, height)
        self.resize(width, height)
        self.setFixedSize(width, height)
        self.setWindowTitle("Loja")
        self.statusBar().hide()

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(600)
        self.log_box.setVisible(False)

        self._build_menu()
        self.reload_mappings()
        self.load_items_from_db()

    def _enable_accelerated_viewport(self) -> None:
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            return
        try:
            from PyQt6.QtOpenGLWidgets import QOpenGLWidget

            self.view.setViewport(QOpenGLWidget())
        except Exception:
            return

    def _build_menu(self) -> None:
        self.menuBar().hide()
        menu = QMenu("MENU", self)
        actions = [
            ("Recarregar DB", self.load_items_from_db),
            ("Salvar SQL", self.save_sql),
            ("Copiar SQL", self.copy_sql),
            ("Executar SQL", self.open_sql_file),
            ("Configurar Moedas", self.open_currency_settings),
            ("Resetar saldos de teste", self.reset_test_balances),
            ("Mostrar/Ocultar logs", self.toggle_logs),
        ]
        for label, callback in actions:
            action = QAction(label, self)
            action.triggered.connect(callback)
            menu.addAction(action)

        language = QMenu("IDIOMA", self)
        for folder in ("Translate_PT", "Translate", "Translate_EN"):
            action = QAction(folder, self)
            action.triggered.connect(
                lambda _checked=False, name=folder: self.change_language(name)
            )
            language.addAction(action)
        menu.addMenu(language)
        self.context_menu = menu
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(
            lambda _pos: self.context_menu.exec(QCursor.pos())
        )

    def log_message(self, message: str, level: str = "INFO", source: str = "APP") -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{source}] [{level}] [{timestamp}] {message}"
        self.log_box.appendPlainText(line)
        print(line)

    def toggle_logs(self) -> None:
        self.log_box.setVisible(not self.log_box.isVisible())
        if self.log_box.isVisible():
            self.log_box.setWindowTitle("Logs da Loja")
            self.log_box.resize(860, 320)
            self.log_box.show()

    def reload_mappings(self) -> None:
        self.item_icon_names, self.item_display_names, self.item_qualities = load_item_mappings(
            self.game_directory,
            self.current_lang_folder,
            self.log_message,
        )
        self.icon_cache.clear()

    def change_language(self, folder_name: str) -> None:
        self.current_lang_folder = folder_name
        self.reload_mappings()
        self.load_items_from_db()
        self.log_message(f"Idioma alterado para {folder_name}.", "INFO", "UI")

    def load_items_from_db(self) -> None:
        start = time.perf_counter()
        try:
            self.items = self.repository.load_items(
                self.item_icon_names,
                self.item_display_names,
                self.item_qualities,
            )
            self.filter_by_category(self.current_category, preserve_page=True)
        except Exception as exc:
            self.log_message(
                format_exception("Erro inesperado ao carregar itens.", exc),
                "ERROR",
                "DB",
            )
        self.log_message(
            f"Carregamento do DB finalizado em {time.perf_counter() - start:.4f}s.",
            "INFO",
            "DB",
        )

    def filter_by_category(self, category_id: int, preserve_page: bool = False) -> None:
        if category_id != 50:
            self.current_category = category_id
        if not preserve_page:
            self.current_page = 0
        self.popular_items = sorted(
            [
                item
                for item in self.items
                if item.item_group == 50 and item.money_unit == self.current_money_unit
            ],
            key=lambda item: item.item_index,
        )[:8]
        self.filtered_items = sorted(
            [
                item
                for item in self.items
                if item.item_group == self.current_category
                and item.money_unit == self.current_money_unit
            ],
            key=lambda item: item.item_index,
        )
        self.rebuild_scene()

    def set_money_unit(self, money_unit: int) -> None:
        self.current_money_unit = money_unit
        self.current_page = 0
        self.filter_by_category(self.current_category)
        self.log_message(
            f"Loja alterada para {self.settings.store_label(money_unit)}.",
            "INFO",
            "UI",
        )

    def rebuild_scene(self) -> None:
        self.scene.clear()
        self.skin.add_native_layer(
            self.scene,
            self.scale,
            self.skin.dynamic_node_ids(),
        )
        self._draw_static_text()
        self._draw_buttons()
        self._draw_items()

    def _draw_static_text(self) -> None:
        self._shadow_text("Loja de Itens", 5, 2, size=self.MAIN_FONT_SIZE, color="#fff36a")
        self._center_text("Popular", QRectF(9, 54, 75, 21), size=self.SMALL_FONT_SIZE, color="#111111")

        store_rects = [
            self.skin.nodes[301].rect(self.scale),
            self.skin.nodes[302].rect(self.scale),
            self.skin.nodes[303].rect(self.scale),
        ]
        store_labels = ["Loja de Itens", "Loja de Bônus", "Gratuitos"]
        current_store_index = self.settings.currency_ids().index(self.current_money_unit) if self.current_money_unit in self.settings.currency_ids() else 0
        for index, (rect, label) in enumerate(zip(store_rects, store_labels)):
            if index == current_store_index:
                self._draw_node_pixmap(301 + index, state="focus", z=66)
            self._center_text(label, rect, size=self.SMALL_FONT_SIZE)

        role_values = [
            ("points", 402),
            ("bonus", 403),
            ("free", 404),
        ]
        for key, node_id in role_values:
            rect = self.skin.nodes[node_id].rect(self.scale)
            self._center_text(
                str(self.test_balances[key]),
                rect,
                size=self.SMALL_FONT_SIZE,
                color="#ffffff",
            )

        label_overrides = {1: "Lim.", 6: "Fantasias", 7: "Montarias"}
        for category_id, label in CATEGORIES:
            if category_id == 50:
                continue
            node = self.skin.nodes.get(self.CATEGORY_BUTTONS.get(category_id, 0))
            if not node:
                continue
            rect = node.rect(self.scale)
            active = category_id == self.current_category
            if active:
                self._draw_node_pixmap(node.window_id, state="focus", z=66)
            self._center_text(
                label_overrides.get(category_id, label),
                rect,
                size=self.SMALL_FONT_SIZE,
                bold=False,
                color="#ffffff" if active else "#111111",
            )

    def _draw_buttons(self) -> None:
        self._hit(QRectF(9, 54, 75, 21), lambda: self.filter_by_category(50))
        for category_id in [1, 9, 2, 3, 4, 5, 6, 7, 8]:
            node = self.skin.nodes.get(self.CATEGORY_BUTTONS.get(category_id, 0))
            if node:
                self._hit(
                    node.rect(self.scale),
                    lambda cid=category_id: self.filter_by_category(cid),
                )

        store_ids = self.settings.currency_ids()
        store_rects = [
            self.skin.nodes[301].rect(self.scale),
            self.skin.nodes[302].rect(self.scale),
            self.skin.nodes[303].rect(self.scale),
        ]
        for index, rect in enumerate(store_rects):
            if index < len(store_ids):
                self._hit(rect, lambda money=store_ids[index]: self.set_money_unit(money))

        self._hit(
            self.skin.nodes[206].rect(self.scale),
            self.buy_all_visible_items,
        )
        self._hit(
            self.skin.nodes[204].rect(self.scale),
            self.reset_test_balances,
        )
        self._hit(
            self.skin.nodes[201].rect(self.scale),
            self.prev_page,
        )
        self._hit(
            self.skin.nodes[202].rect(self.scale),
            self.next_page,
        )

    def _draw_items(self) -> None:
        total_items = len(self.filtered_items)
        items_per_page = self.items_per_page
        total_pages = self.total_pages
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        start = self.current_page * items_per_page
        page_items = self.filtered_items[start : start + items_per_page]
        popular_rects = self.skin.item_icon_rects(50, self.scale)
        for index, item in enumerate(self.popular_items[: len(popular_rects)]):
            self._draw_popular_item(index, popular_rects[index], item)

        icon_rects = self.skin.item_icon_rects(1, self.scale)

        for index, rect in enumerate(icon_rects):
            item = page_items[index] if index < len(page_items) else None
            if item:
                self._draw_item(index, rect, item)
            elif self._can_add_here(index, len(page_items)):
                self._draw_add_button(rect)

        self._center_text(f"{self.current_page + 1}/{total_pages}", QRectF(433, 438, 50, 18), size=self.MAIN_FONT_SIZE)
        self._draw_node_button(204, "Resetar", self.reset_test_balances)
        self._draw_node_button(205, "MP", lambda: self.log_message("Botão MP acionado.", "INFO", "UI"))
        self._draw_node_button(206, "Pegar Tudo", self.buy_all_visible_items)

    def _draw_item(self, index: int, rect: QRectF, item: ItemMall) -> None:
        if self.current_category == 50:
            self._draw_popular_item(index, rect, item)
            return
        self._draw_main_item(index, rect, item)

    def _draw_main_item(self, index: int, rect: QRectF, item: ItemMall) -> None:
        slot_node_id = (151 if self.current_category == 50 else 101) + index
        slot_node = self.skin.nodes.get(slot_node_id)
        slot_pixmap = self.skin.pixmap_for_node(slot_node_id, self.scale)
        if slot_pixmap:
            slot_item = self.scene.addPixmap(slot_pixmap)
            if slot_node:
                slot_item.setPos(slot_node.left * self.scale, slot_node.top * self.scale)
            else:
                slot_item.setPos(rect.x(), rect.y())
            slot_item.setZValue(68)

        pixmap = self.load_item_icon(item.icon_name, item.item_id, 32)
        if pixmap:
            icon_item = self.scene.addPixmap(pixmap)
            icon_item.setPos(rect.x(), rect.y())
            icon_item.setZValue(70)
        else:
            placeholder = self.scene.addRect(
                rect,
                QPen(QColor("#8f7147")),
                QColor(255, 255, 255, 30),
            )
            placeholder.setZValue(70)
            self._text("?", rect.x() + 10, rect.y() + 6, size=self.HID_FONT_SIZE, scene_pos=True)

        cell = self._card_rect_for_icon(rect)
        self._item_name_text(item, cell.x() + 4, cell.y() + 2, 24)
        offer = item.special_price > 0 and item.point != item.special_price
        if offer:
            self._shadow_text("Oferta", cell.x() + 5, cell.y() + 17, size=self.SMALL_FONT_SIZE, color="#ff1d12", scene_pos=True)

        price = item.special_price if item.special_price > 0 else item.point
        if offer:
            self._draw_price_box(1501 + index, item.point, strike=True)
            self._draw_currency_icon(2801 + index, item.money_unit)
            self._draw_price_box(1401 + index, price)
            self._draw_currency_icon(1101 + index, item.money_unit)
        else:
            self._text(str(item.item_num), rect.x() + 5, rect.y() + 24, size=self.SMALL_FONT_SIZE, color="#473018", scene_pos=True)
            self._draw_currency_icon(2801 + index, item.money_unit)
            self._draw_price_box(1501 + index, price)
            self._draw_currency_icon(1101 + index, item.money_unit)

        self._draw_node_button(1601 + index, "Comprar", lambda current=item: self.buy_test_item(current))
        self._draw_node_button(1701 + index, "Enviar", lambda current=item: self.edit_item(current))
        self._draw_node_button(1801 + index, "Detalhes", lambda current=item: self.edit_item(current))

        card = self._card_rect_for_icon(rect)
        self._hit(
            card,
            lambda current=item: self.edit_item(current),
            lambda current=item: self.edit_item(current),
            z=80,
            tooltip=item.display_name,
        )

    def _draw_popular_item(self, index: int, rect: QRectF, item: ItemMall) -> None:
        slot_node_id = 151 + index
        slot_node = self.skin.nodes.get(slot_node_id)
        slot_pixmap = self.skin.pixmap_for_node(slot_node_id, self.scale)
        if slot_pixmap and slot_node:
            slot_item = self.scene.addPixmap(slot_pixmap)
            slot_item.setPos(slot_node.left, slot_node.top)
            slot_item.setZValue(68)

        pixmap = self.load_item_icon(item.icon_name, item.item_id, 32)
        if pixmap:
            icon_item = self.scene.addPixmap(pixmap)
            icon_item.setPos(rect.x(), rect.y())
            icon_item.setZValue(70)

        self._item_name_text(item, 66, rect.y() - 1, 20)
        price = item.special_price if item.special_price > 0 else item.point
        self._draw_price_box(1551 + index, price)
        self._draw_currency_icon(2851 + index, item.money_unit, popular=True)
        self._draw_node_button(1651 + index, "Comprar", lambda current=item: self.buy_test_item(current))
        card = self._card_rect_for_icon(rect)
        self._hit(card, lambda current=item: self.edit_item(current), lambda current=item: self.edit_item(current), z=80, tooltip=item.display_name)

    def _draw_add_button(self, rect: QRectF) -> None:
        size = 34
        button_rect = QRectF(
            rect.center().x() - size / 2,
            rect.center().y() - size / 2,
            size,
            size,
        )
        plus = self.scene.addRect(
            button_rect,
            QPen(QColor("#8d5d1f")),
            QColor("#c98627"),
        )
        plus.setZValue(80)
        self._text(
            "+",
            button_rect.x() + 10,
            button_rect.y() + 2,
            size=18,
            color="#ffffff",
            scene_pos=True,
        )
        self._hit(button_rect, self.add_item)

    def _card_rect_for_icon(self, rect: QRectF) -> QRectF:
        x = rect.x() / self.scale
        y = rect.y() / self.scale
        if self.current_category == 50:
            return QRectF(
                x - 8,
                y - 7,
                170,
                40,
            )
        return QRectF(
            x - 4,
            y - 20,
            170,
            78,
        )

    def _can_add_here(self, slot_index: int, page_count: int) -> bool:
        if self.current_category == 50 and len(self.filtered_items) >= 8:
            return False
        return self.current_page == self.total_pages - 1 and slot_index == page_count

    @property
    def items_per_page(self) -> int:
        return 12

    @property
    def total_pages(self) -> int:
        total_items = len(self.filtered_items)
        pages = max(1, math.ceil(max(1, total_items + 1) / self.items_per_page))
        return pages

    def prev_page(self) -> None:
        self.current_page = (self.current_page - 1) % self.total_pages
        self.rebuild_scene()

    def next_page(self) -> None:
        self.current_page = (self.current_page + 1) % self.total_pages
        self.rebuild_scene()

    def get_next_index_for_category(self, category_id: int, money_unit: int) -> int:
        indexes = [
            item.item_index
            for item in self.items
            if item.item_group == category_id and item.money_unit == money_unit
        ]
        return max(indexes, default=0) + 1

    def add_item(self) -> None:
        item = ItemMall(
            item_id=0,
            item_group=self.current_category,
            item_index=self.get_next_index_for_category(self.current_category, self.current_money_unit),
            item_num=1,
            money_unit=self.current_money_unit,
            point=ItemDialog._default_point_value if ItemDialog._save_default_point else 0,
            special_price=ItemDialog._default_special_price_value if ItemDialog._save_default_special_price else 0,
            sell=1,
            on_sell_date=0,
            not_sell_date=0,
            account_num_limit=0,
            recognized_percentage=0.0,
            fortune_bag="",
            allow_buy_level=0,
            new_account_day_limit=0,
            note="",
        )
        self.edit_item(item, is_new=True)

    def edit_item(self, item: ItemMall, is_new: bool = False) -> None:
        dialog = ItemDialog(
            item,
            self.settings.combo_values(),
            self.get_next_index_for_category,
            self.load_item_icon,
            self.item_display_names,
            self.item_icon_names,
            is_edit=not is_new,
            parent=self,
        )
        if dialog.exec() != ItemDialog.DialogCode.Accepted:
            return
        if dialog.deleted:
            if self.repository.delete_item(item):
                self.load_items_from_db()
            return
        saved = dialog.item
        if saved.item_group == 50 and self._popular_would_exceed(saved, is_new):
            QMessageBox.warning(self, "Limite", "A aba POPULAR permite no máximo 8 itens.")
            return
        saved.item_quality = self.item_qualities.get(saved.item_id, 0)
        ok = self.repository.insert_item(saved) if is_new else self.repository.update_item(saved)
        if ok:
            self.load_items_from_db()

    def _popular_would_exceed(self, item: ItemMall, is_new: bool) -> bool:
        if item.item_group != 50:
            return False
        count = sum(
            1
            for current in self.items
            if current.item_group == 50 and current.money_unit == item.money_unit
        )
        if is_new:
            return count >= 8
        original_group = getattr(item, "_original_item_group", item.item_group)
        original_money = getattr(item, "_original_money_unit", item.money_unit)
        if original_group == 50 and original_money == item.money_unit:
            return count > 8
        return count >= 8

    def _currency_role(self, money_unit: int) -> str:
        ids = self.settings.currency_ids()
        if ids and money_unit == ids[0]:
            return "points"
        if len(ids) > 1 and money_unit == ids[1]:
            return "bonus"
        if len(ids) > 2 and money_unit == ids[2]:
            return "free"
        return "points"

    def buy_test_item(self, item: ItemMall) -> None:
        price = item.special_price if item.special_price > 0 else item.point
        role = self._currency_role(item.money_unit)
        if role != "free" and self.test_balances[role] < price:
            QMessageBox.warning(
                self,
                "Saldo insuficiente",
                f"Saldo de teste insuficiente para comprar {item.display_name}.",
            )
            self.log_message(f"Compra negada: {item.display_name} custa {price}.", "WARNING", "UI")
            return

        bonus_gain = 0
        if role == "free":
            message = f"Compra grátis de teste: {item.display_name}."
        else:
            self.test_balances[role] -= price
            if role == "points":
                bonus_gain = int(price * 0.05)
                self.test_balances["bonus"] += bonus_gain
            message = f"Compra de teste: {item.display_name} por {price}."
            if bonus_gain:
                message += f" Bônus gerado: {bonus_gain}."
        self.log_message(message, "INFO", "UI")
        self.rebuild_scene()

    def buy_all_visible_items(self) -> None:
        start = self.current_page * self.items_per_page
        page_items = self.filtered_items[start : start + self.items_per_page]
        bought = 0
        bonus_total = 0
        for item in page_items:
            price = item.special_price if item.special_price > 0 else item.point
            role = self._currency_role(item.money_unit)
            if role == "free":
                bought += 1
                continue
            if self.test_balances[role] < price:
                continue
            self.test_balances[role] -= price
            bought += 1
            if role == "points":
                bonus = int(price * 0.05)
                self.test_balances["bonus"] += bonus
                bonus_total += bonus
        self.log_message(
            f"Pegar Tudo: {bought} itens comprados. Bônus gerado: {bonus_total}.",
            "INFO",
            "UI",
        )
        self.rebuild_scene()

    def reset_test_balances(self) -> None:
        self.test_balances = {"points": 55033, "bonus": 8993, "free": 0}
        self.rebuild_scene()
        self.log_message("Saldos de teste restaurados.", "INFO", "UI")

    def open_currency_settings(self) -> None:
        dialog = CurrencySettingsDialog(self.settings, self)
        if dialog.exec() == CurrencySettingsDialog.DialogCode.Accepted:
            if self.current_money_unit not in self.settings.currency_ids():
                self.current_money_unit = self.settings.currency_ids()[0]
            self.filter_by_category(self.current_category, preserve_page=True)
            self.log_message("Configuração de moedas salva.", "INFO", "UI")

    def save_sql(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar SQL",
            "itemmall.sql",
            "SQL (*.sql);;Todos (*.*)",
        )
        if not path:
            self.log_message("Salvamento de SQL cancelado.", "WARNING", "UI")
            return
        Path(path).write_text(self.repository.generate_sql(self.items), encoding="utf-8")
        self.log_message(f"SQL salvo em {path}.", "INFO", "DB")

    def copy_sql(self) -> None:
        QApplication.clipboard().setText(self.repository.generate_sql(self.items))
        self.log_message("SQL copiado para a área de transferência.", "INFO", "UI")

    def open_sql_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Executar SQL",
            "",
            "SQL (*.sql);;Todos (*.*)",
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self,
            "Executar SQL",
            "Essa operação executa o arquivo selecionado no banco conectado. Continuar?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        script = Path(path).read_text(encoding="utf-8", errors="replace")
        if self.repository.execute_sql_script(script):
            self.load_items_from_db()

    def load_item_icon(self, icon_name: str, item_id: int, size: int) -> Optional[QPixmap]:
        if not icon_name:
            return None
        key = f"{icon_name}:{item_id}:{size}"
        if key in self.icon_cache:
            return self.icon_cache[key]
        path = Path(self.game_directory) / "UI" / "itemicon" / f"{icon_name}.dds"
        if not path.exists():
            return None
        try:
            with Image.open(path) as image:
                image = image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                data = image.tobytes("raw", "RGBA")
                qimage = QImage(
                    data,
                    image.width,
                    image.height,
                    QImage.Format.Format_RGBA8888,
                ).copy()
                pixmap = QPixmap.fromImage(qimage)
                self.icon_cache[key] = pixmap
                return pixmap
        except Exception as exc:
            self.log_message(
                format_exception(f"Falha ao carregar ícone {icon_name}.dds.", exc),
                "ERROR",
                "UI",
            )
            return None

    def _draw_node_button(self, node_id: int, label: str, callback) -> None:
        node = self.skin.nodes.get(node_id)
        if not node:
            return
        self._draw_node_pixmap(node_id, z=75)
        rect = node.rect(self.scale)
        self._center_text(label, rect, size=self.SMALL_FONT_SIZE)
        self._hit(rect, callback)

    def _draw_node_pixmap(self, node_id: int, state: str = "normal", z: int = 75) -> None:
        node = self.skin.nodes.get(node_id)
        if not node:
            return
        pixmap = self.skin.pixmap_for_node(node_id, self.scale, state=state)
        if not pixmap:
            return
        item = self.scene.addPixmap(pixmap)
        item.setPos(node.left * self.scale, node.top * self.scale)
        item.setZValue(z)

    def _draw_price_box(self, node_id: int, value: int, strike: bool = False) -> None:
        node = self.skin.nodes.get(node_id)
        if not node:
            return
        pixmap = self.skin.pixmap_for_node(node_id, self.scale)
        if pixmap:
            item = self.scene.addPixmap(pixmap)
            item.setPos(node.left * self.scale, node.top * self.scale)
            item.setZValue(72)
        rect = node.rect(self.scale)
        self._center_text(str(value), rect, size=self.SMALL_FONT_SIZE, color="#ffffff")
        if strike:
            line = self.scene.addLine(
                rect.left() + 2,
                rect.center().y(),
                rect.right() - 2,
                rect.center().y(),
                QPen(QColor("#c40000"), 2),
            )
            line.setZValue(92)

    def _draw_currency_icon(self, node_id: int, money_unit: int, popular: bool = False) -> None:
        role = self._currency_role(money_unit)
        if 1101 <= node_id <= 1112:
            offset = {"points": 0, "bonus": 100, "free": 200}.get(role, 0)
        elif popular or 2801 <= node_id <= 2812 or 2851 <= node_id <= 2858:
            offset = {"points": 0, "bonus": -200, "free": -100}.get(role, 0)
        else:
            offset = 0
        icon_node_id = node_id + offset
        node = self.skin.nodes.get(icon_node_id) or self.skin.nodes.get(node_id)
        if not node:
            return
        pixmap = self.skin.pixmap_for_node(node.window_id, self.scale)
        if not pixmap:
            return
        item = self.scene.addPixmap(pixmap)
        item.setPos(node.left * self.scale, node.top * self.scale)
        item.setZValue(74)

    def _text(
        self,
        text: str,
        x: float,
        y: float,
        size: int = 8,
        bold: bool = False,
        color: str = "#111111",
        align_right: bool = False,
        strike: bool = False,
        scene_pos: bool = False,
        tooltip: str = "",
    ) -> QGraphicsSimpleTextItem:
        item = QGraphicsSimpleTextItem(text)
        font = QFont(self.FONT_FAMILY, max(6, size))
        font.setBold(bold)
        font.setStrikeOut(strike)
        item.setFont(font)
        item.setBrush(QColor(color))
        if tooltip:
            item.setToolTip(tooltip)
        item.setZValue(90)
        px = x if scene_pos else x * self.scale
        py = y if scene_pos else y * self.scale
        if align_right:
            item.setPos(px - item.boundingRect().width(), py)
        else:
            item.setPos(px, py)
        self.scene.addItem(item)
        return item

    def _shadow_text(
        self,
        text: str,
        x: float,
        y: float,
        size: int = MAIN_FONT_SIZE,
        color: str = "#111111",
        bold: bool = False,
        scene_pos: bool = False,
        tooltip: str = "",
    ) -> QGraphicsSimpleTextItem:
        self._text(text, x + 1, y + 1, size=size, bold=bold, color="#000000", scene_pos=scene_pos)
        return self._text(
            text,
            x,
            y,
            size=size,
            bold=bold,
            color=color,
            scene_pos=scene_pos,
            tooltip=tooltip,
        )

    def _item_name_text(
        self,
        item: ItemMall,
        x: float,
        y: float,
        max_len: int,
    ) -> QGraphicsSimpleTextItem:
        return self._shadow_text(
            self._truncate(item.display_name, max_len),
            x,
            y,
            size=self.MAIN_FONT_SIZE,
            color=self._quality_color(item),
            scene_pos=True,
            tooltip=item.display_name,
        )

    def _center_text(
        self,
        text: str,
        rect: QRectF,
        size: int = MAIN_FONT_SIZE,
        bold: bool = False,
        color: str = "#111111",
    ) -> QGraphicsSimpleTextItem:
        item = self._text(text, 0, 0, size=size, bold=bold, color=color, scene_pos=True)
        bounds = item.boundingRect()
        item.setPos(
            rect.x() + (rect.width() - bounds.width()) / 2,
            rect.y() + (rect.height() - bounds.height()) / 2 - 1,
        )
        return item

    def _hit(
        self,
        rect: QRectF,
        callback,
        double_callback=None,
        z: int = 100,
        tooltip: str = "",
    ) -> None:
        item = HitRectItem(rect, callback, double_callback, tooltip)
        item.setZValue(z)
        self.scene.addItem(item)

    def _quality_color(self, item: ItemMall) -> str:
        return self.QUALITY_COLORS.get(item.item_quality, "#ffffff")

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max(1, max_len - 3)] + "..."
