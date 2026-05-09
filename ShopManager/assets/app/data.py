import re
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import ItemMall
from .paths import ENV_PATH


LogFunc = Callable[[str, str, str], None]


def null_logger(message: str, level: str = "INFO", source: str = "APP") -> None:
    _ = (message, level, source)


def load_env() -> Dict[str, str]:
    if not ENV_PATH.exists():
        save_env("localhost", "5432", "postgres", "")
    values: Dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def save_env(host: str, port: str, user: str, password: str) -> None:
    ENV_PATH.write_text(
        "\n".join(
            [
                f"DB_HOST={host}",
                f"DB_PORT={port}",
                f"DB_USER={user}",
                f"DB_PASSWORD={password}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def connect_postgres(host: str, port: str, user: str, password: str):
    import psycopg2

    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname="gf_ls",
        connect_timeout=5,
    )


def format_exception(prefix: str, exc: Exception) -> str:
    details = [prefix, f"{type(exc).__name__}: {exc}"]
    pgcode = getattr(exc, "pgcode", None)
    pgerror = getattr(exc, "pgerror", None)
    diag = getattr(exc, "diag", None)
    diag_message = getattr(diag, "message_primary", None) if diag else None

    if pgcode:
        details.append(f"Código PostgreSQL: {pgcode}")
    if diag_message:
        details.append(f"Detalhe PostgreSQL: {diag_message}")
    elif pgerror:
        details.append(f"Detalhe PostgreSQL: {str(pgerror).strip()}")

    stack = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__, limit=8)
    ).strip()
    if stack:
        details.append(f"Traceback:\n{stack}")
    return "\n".join(details)


def detect_encoding(path: Path) -> str:
    for encoding in ("utf-8", "latin-1", "cp1252", "iso-8859-1", "utf-16"):
        try:
            path.read_text(encoding=encoding)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError:
            break
    return "utf-8"


def _read_ini(
    file_path: Path,
    parse_line: Callable[[str], Optional[Tuple[int, Any]]],
    target: Dict[int, Any],
    logger: LogFunc,
) -> None:
    if not file_path.exists():
        logger(f"Arquivo INI não encontrado: {file_path}", "WARNING", "UI")
        return

    try:
        encoding = detect_encoding(file_path)
        with file_path.open("r", encoding=encoding, errors="replace") as handle:
            next(handle, None)
            for line in handle:
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                parsed = parse_line(line)
                if parsed:
                    key, value = parsed
                    target[key] = value
    except Exception as exc:
        logger(format_exception(f"Falha ao ler {file_path.name}.", exc), "ERROR", "UI")


def _read_item_db_ini(
    file_path: Path,
    icon_names: Dict[int, str],
    item_qualities: Dict[int, int],
    logger: LogFunc,
) -> None:
    if not file_path.exists():
        return

    try:
        encoding = detect_encoding(file_path)
        with file_path.open("r", encoding=encoding, errors="replace") as handle:
            next(handle, None)
            for line in handle:
                line = line.strip()
                if not line or line.startswith(";"):
                    continue
                parts = line.split("|")
                if len(parts) < 2:
                    continue
                try:
                    item_id = int(parts[0])
                except ValueError:
                    continue
                icon_name = parts[1].strip()
                if icon_name:
                    icon_names[item_id] = icon_name
                if len(parts) > 24:
                    raw_quality = parts[24].strip()
                    try:
                        item_qualities[item_id] = int(raw_quality) if raw_quality else 0
                    except ValueError:
                        item_qualities[item_id] = 0
    except Exception as exc:
        logger(format_exception(f"Falha ao ler {file_path.name}.", exc), "ERROR", "UI")


def load_item_mappings(
    game_directory: str,
    lang_folder: str = "Translate_PT",
    logger: LogFunc = null_logger,
) -> Tuple[Dict[int, str], Dict[int, str], Dict[int, int]]:
    start = time.perf_counter()
    base = Path(game_directory)
    icon_names: Dict[int, str] = {}
    display_names: Dict[int, str] = {}
    item_qualities: Dict[int, int] = {}

    def parse_name(line: str) -> Optional[Tuple[int, str]]:
        parts = line.split("|")
        if len(parts) < 2:
            return None
        try:
            item_id = int(parts[0])
        except ValueError:
            return None
        display_name = parts[1].strip()
        return (item_id, display_name) if display_name else None

    db_dir = base / "data" / "db"
    translate_dir = base / "data" / lang_folder
    fallback_translate_dir = base / "data" / "Translate"
    if not translate_dir.is_dir():
        translate_dir = fallback_translate_dir

    for filename in ("C_Item.ini", "C_ItemMall.ini", "C_ItemMalll.ini"):
        path = db_dir / filename
        if path.exists():
            _read_item_db_ini(path, icon_names, item_qualities, logger)
    _read_ini(translate_dir / "T_Item.ini", parse_name, display_names, logger)
    _read_ini(translate_dir / "T_ItemMall.ini", parse_name, display_names, logger)

    logger(
        f"Leitura dos INIs ({translate_dir.name}) concluída em {time.perf_counter() - start:.4f}s.",
        "INFO",
        "UI",
    )
    return icon_names, display_names, item_qualities


class ItemMallRepository:
    def __init__(self, connection, logger: LogFunc = null_logger):
        self.connection = connection
        self.logger = logger

    def load_items(
        self,
        icon_names: Dict[int, str],
        display_names: Dict[int, str],
        item_qualities: Dict[int, int],
    ) -> List[ItemMall]:
        query = """
            SELECT item_id, item_group, item_index, item_num, money_unit, point,
                   special_price, sell, on_sell_date, not_sell_date,
                   account_num_limit, recognized_percentage, fortune_bag,
                   allow_buy_level, new_account_day_limit, note
            FROM public.itemmall
            ORDER BY item_group, item_index, money_unit;
        """
        rows = self._fetchall(query, "Erro ao carregar itens do DB.")
        items: List[ItemMall] = []
        for row in rows:
            item_id = int(row[0])
            items.append(
                ItemMall(
                    item_id=item_id,
                    item_group=int(row[1]),
                    item_index=int(row[2]),
                    item_num=int(row[3]),
                    money_unit=int(row[4]),
                    point=int(row[5]),
                    special_price=int(row[6]),
                    sell=int(row[7]),
                    on_sell_date=int(row[8]),
                    not_sell_date=int(row[9]),
                    account_num_limit=int(row[10]),
                    recognized_percentage=float(row[11]),
                    fortune_bag=row[12] or "",
                    allow_buy_level=int(row[13]),
                    new_account_day_limit=int(row[14]),
                    note=row[15] or "",
                    icon_name=icon_names.get(item_id, ""),
                    display_name=display_names.get(item_id, f"Item {item_id}"),
                    item_quality=item_qualities.get(item_id, 0),
                )
            )
        self.logger(f"{len(items)} itens carregados do banco.", "INFO", "DB")
        return items

    def insert_item(self, item: ItemMall) -> bool:
        query = """
            INSERT INTO public.itemmall (
                item_id, item_group, item_index, item_num, money_unit, point,
                special_price, sell, on_sell_date, not_sell_date, account_num_limit,
                recognized_percentage, fortune_bag, allow_buy_level,
                new_account_day_limit, note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        return self._execute(
            query,
            self._params(item),
            f"Item {item.item_id} inserido no DB no índice {item.item_index}.",
            "Erro ao inserir item no DB.",
        )

    def update_item(self, item: ItemMall) -> bool:
        query = """
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
        original = (
            getattr(item, "_original_item_id", item.item_id),
            getattr(item, "_original_item_group", item.item_group),
            getattr(item, "_original_item_index", item.item_index),
            getattr(item, "_original_money_unit", item.money_unit),
        )
        return self._execute(
            query,
            self._params(item) + original,
            f"Item {item.item_id} atualizado no DB.",
            "Erro ao atualizar item no DB.",
        )

    def delete_item(self, item: ItemMall) -> bool:
        query = """
            DELETE FROM public.itemmall
            WHERE item_id = %s AND item_group = %s AND item_index = %s AND money_unit = %s;
        """
        return self._execute(
            query,
            (item.item_id, item.item_group, item.item_index, item.money_unit),
            f"Item {item.item_id} excluído do DB.",
            "Erro ao excluir item do DB.",
        )

    def generate_sql(self, items: List[ItemMall]) -> str:
        lines = [
            'DROP TABLE IF EXISTS "public"."itemmall";',
            "",
            'CREATE TABLE "public"."itemmall" (',
            '  "item_id" int4 NOT NULL,',
            '  "item_group" int4 NOT NULL,',
            '  "item_index" int4 NOT NULL,',
            '  "item_num" int4 NOT NULL,',
            '  "money_unit" int4 NOT NULL,',
            '  "point" int4 NOT NULL,',
            '  "special_price" int4 NOT NULL,',
            '  "sell" int4 NOT NULL,',
            '  "on_sell_date" int4 NOT NULL,',
            '  "not_sell_date" int4 NOT NULL,',
            '  "account_num_limit" int4 DEFAULT 0,',
            '  "recognized_percentage" float8 NOT NULL,',
            '  "fortune_bag" text COLLATE "pg_catalog"."default" DEFAULT \'\'::text,',
            '  "allow_buy_level" int4 NOT NULL,',
            '  "new_account_day_limit" int4 DEFAULT 0,',
            '  "note" text COLLATE "pg_catalog"."default" DEFAULT \'\'::text',
            ");",
            "",
        ]
        ordered = sorted(items, key=lambda x: (x.item_group, x.item_index, x.money_unit))
        for item in ordered:
            fortune_bag = item.fortune_bag.replace("'", "''")
            note = item.note.replace("'", "''")
            lines.append(
                'INSERT INTO "public"."itemmall" VALUES '
                f"({item.item_id}, {item.item_group}, {item.item_index}, "
                f"{item.item_num}, {item.money_unit}, {item.point}, "
                f"{item.special_price}, {item.sell}, {item.on_sell_date}, "
                f"{item.not_sell_date}, {item.account_num_limit}, "
                f"{item.recognized_percentage}, '{fortune_bag}', "
                f"{item.allow_buy_level}, {item.new_account_day_limit}, '{note}');"
            )
        return "\n".join(lines) + "\n"

    def execute_sql_script(self, script: str) -> bool:
        commands = [
            cmd.strip()
            for cmd in re.split(r";\s*$", script, flags=re.MULTILINE)
            if cmd.strip()
        ]
        if not commands:
            self.logger("Arquivo SQL vazio.", "WARNING", "DB")
            return False
        cursor = None
        try:
            cursor = self.connection.cursor()
            for command in commands:
                cursor.execute(command)
            self.connection.commit()
            self.logger(f"{len(commands)} comandos SQL executados.", "INFO", "DB")
            return True
        except Exception as exc:
            self.connection.rollback()
            self.logger(format_exception("Falha ao executar script SQL.", exc), "ERROR", "DB")
            return False
        finally:
            if cursor:
                cursor.close()

    def _fetchall(self, query: str, error_message: str) -> List[tuple]:
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            self.connection.commit()
            return rows
        except Exception as exc:
            self.connection.rollback()
            self.logger(format_exception(error_message, exc), "ERROR", "DB")
            return []
        finally:
            if cursor:
                cursor.close()

    def _execute(
        self,
        query: str,
        params: tuple,
        success_message: str,
        error_message: str,
    ) -> bool:
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            self.connection.commit()
            self.logger(success_message, "INFO", "DB")
            return True
        except Exception as exc:
            self.connection.rollback()
            self.logger(format_exception(error_message, exc), "ERROR", "DB")
            return False
        finally:
            if cursor:
                cursor.close()

    @staticmethod
    def _params(item: ItemMall) -> tuple:
        return (
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
