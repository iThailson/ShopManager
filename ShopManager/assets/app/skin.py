import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import hashlib
import xml.etree.ElementTree as ET

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QImageReader, QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from .paths import UI_DIR


@dataclass
class DirectDdsImage:
    width: int
    height: int
    raw: bytes
    offset: int = 128

    def crop_bytes(self, uv: Tuple[int, int, int, int]) -> bytes:
        left, top, width, height = uv
        pitch = self.width * 4
        rows = []
        for row in range(top, top + height):
            start = self.offset + row * pitch + left * 4
            rows.append(self.raw[start : start + width * 4])
        return b"".join(rows)

    def crop_qimage(self, uv: Tuple[int, int, int, int]) -> QImage:
        _, _, width, height = uv
        data = self.crop_bytes(uv)
        image = QImage(data, width, height, QImage.Format.Format_ARGB32)
        return image.copy()

    def crop_pil(self, uv: Tuple[int, int, int, int]) -> Image.Image:
        _, _, width, height = uv
        return Image.frombytes("RGBA", (width, height), self.crop_bytes(uv), "raw", "BGRA")


@dataclass(frozen=True)
class SkinNode:
    window_id: int
    left: int
    top: int
    width: int
    height: int
    texture: str
    uv: Tuple[int, int, int, int]
    button_uvs: Dict[str, Tuple[int, int, int, int]] = field(default_factory=dict)

    def rect(self, scale: float) -> QRectF:
        return QRectF(
            self.left * scale,
            self.top * scale,
            self.width * scale,
            self.height * scale,
        )


class ClickablePixmapItem(QGraphicsPixmapItem):
    def __init__(self, pixmap: QPixmap, callback=None):
        super().__init__(pixmap)
        self.callback = callback
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event):
        if self.callback:
            self.callback()
            event.accept()
            return
        super().mousePressEvent(event)


class DdsTextureCache:
    def __init__(self, texture_dir: Path = UI_DIR):
        self.texture_dir = texture_dir
        self.direct_images: Dict[str, Optional[DirectDdsImage]] = {}
        self.images: Dict[str, Image.Image] = {}
        self.pixmaps: Dict[Tuple[str, Tuple[int, int, int, int], float], QPixmap] = {}
        self.fallbacks = {"uiobj04.dds": ["uiobj04.dds", "uiobj04_e.dds"]}

    def texture_exists(self, texture_name: str) -> bool:
        return self._resolve_texture_path(texture_name) is not None

    def pixmap(
        self,
        texture_name: str,
        uv: Tuple[int, int, int, int],
        scale: float = 1.0,
    ) -> Optional[QPixmap]:
        if uv[2] <= 0 or uv[3] <= 0:
            return None

        texture_path = self._resolve_texture_path(texture_name)
        if not texture_path:
            return None

        key = (texture_path.name.lower(), uv, scale)
        if key in self.pixmaps:
            return self.pixmaps[key]

        image = self._load_qimage_region(texture_path, uv)
        if image is None:
            pil_image = self._load_pil_region(texture_path, uv)
            if pil_image is None:
                return None
            image = self._pil_to_qimage(pil_image)

        pixmap = QPixmap.fromImage(image)
        if scale != 1.0:
            pixmap = pixmap.scaled(
                max(1, round(pixmap.width() * scale)),
                max(1, round(pixmap.height() * scale)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        self.pixmaps[key] = pixmap
        return pixmap

    def _load_qimage_region(
        self, texture_path: Path, uv: Tuple[int, int, int, int]
    ) -> Optional[QImage]:
        direct = self._load_direct_dds(texture_path)
        if direct:
            return direct.crop_qimage(uv)

        reader = QImageReader(str(texture_path))
        if not reader.canRead():
            return None
        image = reader.read()
        if image.isNull():
            return None
        left, top, width, height = uv
        return image.copy(left, top, width, height).convertToFormat(
            QImage.Format.Format_RGBA8888
        )

    def _load_pil_region(
        self, texture_path: Path, uv: Tuple[int, int, int, int]
    ) -> Optional[Image.Image]:
        direct = self._load_direct_dds(texture_path)
        if direct:
            return direct.crop_pil(uv)

        cache_key = texture_path.name.lower()
        if cache_key not in self.images:
            self.images[cache_key] = Image.open(texture_path).convert("RGBA")
        texture = self.images[cache_key]
        left, top, width, height = uv
        return texture.crop((left, top, left + width, top + height))

    def _load_direct_dds(self, texture_path: Path) -> Optional[DirectDdsImage]:
        cache_key = texture_path.name.lower()
        if cache_key in self.direct_images:
            return self.direct_images[cache_key]

        try:
            raw = texture_path.read_bytes()
            if len(raw) < 128 or raw[:4] != b"DDS ":
                self.direct_images[cache_key] = None
                return None

            header_size = struct.unpack_from("<I", raw, 4)[0]
            height = struct.unpack_from("<I", raw, 12)[0]
            width = struct.unpack_from("<I", raw, 16)[0]
            pixel_flags = struct.unpack_from("<I", raw, 80)[0]
            fourcc = raw[84:88]
            rgb_bits = struct.unpack_from("<I", raw, 88)[0]
            masks = struct.unpack_from("<IIII", raw, 92)

            is_raw_bgra = (
                header_size == 124
                and (pixel_flags & 0x40)
                and fourcc == b"\x00\x00\x00\x00"
                and rgb_bits == 32
                and masks == (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
            )
            if not is_raw_bgra:
                self.direct_images[cache_key] = None
                return None

            image = DirectDdsImage(width=width, height=height, raw=raw)
            self.direct_images[cache_key] = image
            return image
        except OSError:
            self.direct_images[cache_key] = None
            return None

    @staticmethod
    def _pil_to_qimage(image: Image.Image) -> QImage:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        data = image.tobytes("raw", "RGBA")
        qimage = QImage(data, image.width, image.height, QImage.Format.Format_RGBA8888)
        return qimage.copy()

    def _resolve_texture_path(self, texture_name: str) -> Optional[Path]:
        for candidate in self.fallbacks.get(texture_name, [texture_name]):
            path = self.texture_dir / candidate
            if path.exists():
                return path
        return None


class GameSkin:
    BACKGROUND_ID = 2
    MAIN_ICON_IDS = range(2401, 2413)
    POPULAR_ICON_IDS = range(2451, 2459)

    def __init__(self, xml_path: Path = UI_DIR / "ItemMallHot.xml"):
        self.xml_path = xml_path
        self.cache = DdsTextureCache(xml_path.parent)
        self.composite_cache: Dict[Tuple[float, Tuple[int, ...]], QPixmap] = {}
        self.nodes: Dict[int, SkinNode] = {}
        self.ordered_nodes: List[SkinNode] = []
        self._load()

    def _load(self) -> None:
        root = ET.fromstring(self.xml_path.read_text(encoding="utf-8", errors="replace"))
        for element in root.iter("BaseWndProperty"):
            bg = element.find("BackGroundMap")
            uv = bg.find("NorUV") if bg is not None else None
            if bg is None or uv is None:
                continue
            window_id = int(element.get("WindowID", "0"))
            node = SkinNode(
                window_id=window_id,
                left=int(element.get("WindowLeft", "0")),
                top=int(element.get("WindowTop", "0")),
                width=int(element.get("WindowHeight", "0")),
                height=int(element.get("WindowWidth", "0")),
                texture=bg.get("BGmap", ""),
                uv=(
                    int(uv.get("NorUVLeft", "0")),
                    int(uv.get("NorUVTop", "0")),
                    int(uv.get("NorUVWidth", "0")),
                    int(uv.get("NorUVHeight", "0")),
                ),
                button_uvs=self._button_uvs(element),
            )
            self.nodes[window_id] = node
            self.ordered_nodes.append(node)

    def scene_size(self, scale: float) -> Tuple[int, int]:
        node = self.nodes[self.BACKGROUND_ID]
        return (round(node.width * scale), round(node.height * scale))

    def add_native_layer(
        self,
        scene: QGraphicsScene,
        scale: float,
        skip_ids: Iterable[int] = (),
    ) -> None:
        pixmap = self.native_pixmap(scale, skip_ids)
        if pixmap is not None:
            item = QGraphicsPixmapItem(pixmap)
            item.setPos(0, 0)
            item.setZValue(1)
            scene.addItem(item)

    def native_pixmap(
        self,
        scale: float,
        skip_ids: Iterable[int] = (),
    ) -> Optional[QPixmap]:
        skip = set(skip_ids)
        key = (scale, tuple(sorted(skip)))
        if key in self.composite_cache:
            return self.composite_cache[key]

        cache_path = self._native_cache_path(scale, skip)
        if cache_path.exists():
            pixmap = QPixmap(str(cache_path))
            if not pixmap.isNull():
                self.composite_cache[key] = pixmap
                return pixmap

        width, height = self.scene_size(scale)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for node in self.ordered_nodes:
            if node.window_id in skip or node.window_id == 1:
                continue
            if node.width <= 0 or node.height <= 0:
                continue
            texture_path = self.cache._resolve_texture_path(node.texture)
            region = (
                self.cache._load_pil_region(texture_path, node.uv)
                if texture_path
                else None
            )
            if region is None:
                continue
            if scale != 1.0:
                region = region.resize(
                    (
                        max(1, round(region.width * scale)),
                        max(1, round(region.height * scale)),
                    ),
                    Image.Resampling.NEAREST,
                )
            canvas.alpha_composite(
                region,
                (round(node.left * scale), round(node.top * scale)),
            )

        pixmap = QPixmap.fromImage(DdsTextureCache._pil_to_qimage(canvas))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(cache_path), "PNG")
        self.composite_cache[key] = pixmap
        return pixmap

    def _native_cache_path(self, scale: float, skip: set[int]) -> Path:
        digest = hashlib.sha1()
        tracked = {self.xml_path}
        for node in self.ordered_nodes:
            path = self.cache._resolve_texture_path(node.texture)
            if path:
                tracked.add(path)
        for path in sorted(tracked, key=lambda item: item.name.lower()):
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(path.name.lower().encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(int(stat.st_mtime)).encode("ascii"))
        digest.update(str(scale).encode("ascii"))
        digest.update(",".join(map(str, sorted(skip))).encode("ascii"))
        return self.xml_path.parent / ".cache" / f"native_{digest.hexdigest()[:16]}.png"

    def dynamic_node_ids(self) -> set[int]:
        ids = set(self.MAIN_ICON_IDS) | set(self.POPULAR_ICON_IDS)
        ids.update(range(101, 113))
        ids.update(range(151, 159))
        ids.update(range(1101, 1313))
        ids.update(range(1401, 1513))
        ids.update(range(1551, 1559))
        ids.update(range(1601, 1813))
        ids.update(range(2301, 2313))
        ids.update(range(2501, 2813))
        ids.update(range(2851, 2859))
        return ids

    def pixmap_for_node(
        self,
        window_id: int,
        scale: float,
        state: str = "normal",
    ) -> Optional[QPixmap]:
        node = self.nodes.get(window_id)
        if not node:
            return None
        uv = node.button_uvs.get(state, node.uv)
        return self.cache.pixmap(node.texture, uv, scale)

    def make_clickable(
        self,
        window_id: int,
        callback,
        scale: float,
        state: str = "normal",
    ) -> Optional[ClickablePixmapItem]:
        node = self.nodes.get(window_id)
        if not node:
            return None
        uv = node.button_uvs.get(state, node.uv)
        pixmap = self.cache.pixmap(node.texture, uv, scale)
        if pixmap is None:
            return None
        item = ClickablePixmapItem(pixmap, callback)
        item.setPos(node.left * scale, node.top * scale)
        item.setZValue(50)
        return item

    def item_icon_rects(self, category_id: int, scale: float) -> List[QRectF]:
        ids = self.POPULAR_ICON_IDS if category_id == 50 else self.MAIN_ICON_IDS
        rects = []
        for window_id in ids:
            node = self.nodes.get(window_id)
            if node:
                rects.append(node.rect(scale))
        return rects

    @staticmethod
    def _button_uvs(element) -> Dict[str, Tuple[int, int, int, int]]:
        button = element.find("ButtonNode")
        if button is None:
            return {}
        result = {}
        for key, tag in {
            "focus": "FocusUV",
            "down": "DownUV",
            "disabled": "DisableUV",
        }.items():
            uv = button.find(tag)
            if uv is None:
                continue
            result[key] = (
                int(uv.get(f"{tag}Left", "0")),
                int(uv.get(f"{tag}Top", "0")),
                int(uv.get(f"{tag}Width", "0")),
                int(uv.get(f"{tag}Height", "0")),
            )
        return result
