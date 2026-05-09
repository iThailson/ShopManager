from dataclasses import dataclass


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
    item_quality: int = 0


CATEGORIES = [
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
