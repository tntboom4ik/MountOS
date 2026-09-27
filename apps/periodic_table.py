"""
MountOS — Таблица Менделеева.

Интерактивная периодическая таблица:
  • 118 элементов с полными данными
  • Категории элементов
  • Поиск по названию/символу/номеру
  • Фильтр по категории
  • Подробная информация о каждом элементе
  • Клик по элементу → детальная карточка
  • Экспорт карточки элемента в PNG (в VFS)

Установка: apps/periodic_table.py + перезапуск MountOS.
"""

import json
import os
import time

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QScrollArea, QFrame,
                                QSizePolicy, QComboBox, QMessageBox,
                                QDialog, QDialogButtonBox, QGridLayout)
from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QSize,
                             QBuffer, QByteArray)
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QLinearGradient, QIcon, QPixmap)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Таблица Менделеева"
APP_ICON = "grid"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


OUT_DIR = "/Pictures/Chemistry"


# ============================================================
#  Категории
# ============================================================

CATEGORIES = {
    "alkali":         {"name": "Щелочные металлы",   "color": "#FF6B8A"},
    "alkaline":       {"name": "Щёлочноземельные",   "color": "#FFB86C"},
    "transition":     {"name": "Переходные металлы", "color": "#6EC6FF"},
    "post_transition":{"name": "Постпереходные",     "color": "#6EE7B7"},
    "metalloid":      {"name": "Металлоиды",         "color": "#5EEAD4"},
    "nonmetal":       {"name": "Неметаллы",          "color": "#B388FF"},
    "halogen":        {"name": "Галогены",           "color": "#FBBF24"},
    "noble":          {"name": "Благородные газы",   "color": "#F472B6"},
    "lanthanide":     {"name": "Лантаноиды",         "color": "#F59E0B"},
    "actinide":       {"name": "Актиноиды",          "color": "#EC4899"},
}


# ============================================================
#  Данные элементов
#  (num, sym, name_ru, name_en, mass, category, group, period,
#   config, t_melt, t_boil, year, discoverer)
# ============================================================

ELEMENTS = [
    (1,  "H",  "Водород",     "Hydrogen",      1.008,   "nonmetal",        1,  1, "1s¹",                              -259,   -253, 1766, "Кавендиш"),
    (2,  "He", "Гелий",       "Helium",        4.0026,  "noble",          18,  1, "1s²",                              -272,   -269, 1868, "Жансен, Локьер"),
    (3,  "Li", "Литий",       "Lithium",       6.94,    "alkali",          1,  2, "[He] 2s¹",                          181,   1342, 1817, "Арфведсон"),
    (4,  "Be", "Бериллий",    "Beryllium",     9.0122,  "alkaline",        2,  2, "[He] 2s²",                         1287,   2469, 1798, "Воклен"),
    (5,  "B",  "Бор",         "Boron",        10.81,    "metalloid",      13,  2, "[He] 2s² 2p¹",                     2076,   3927, 1808, "Гей-Люссак, Тенар"),
    (6,  "C",  "Углерод",     "Carbon",       12.011,   "nonmetal",       14,  2, "[He] 2s² 2p²",                     3550,   4027, "др.", "древние"),
    (7,  "N",  "Азот",        "Nitrogen",     14.007,   "nonmetal",       15,  2, "[He] 2s² 2p³",                     -210,   -196, 1772, "Резерфорд"),
    (8,  "O",  "Кислород",    "Oxygen",       15.999,   "nonmetal",       16,  2, "[He] 2s² 2p⁴",                     -218,   -183, 1774, "Пристли, Шееле"),
    (9,  "F",  "Фтор",        "Fluorine",     18.998,   "halogen",        17,  2, "[He] 2s² 2p⁵",                     -220,   -188, 1886, "Муассан"),
    (10, "Ne", "Неон",        "Neon",         20.180,   "noble",          18,  2, "[He] 2s² 2p⁶",                     -249,   -246, 1898, "Рамзай, Траверс"),
    (11, "Na", "Натрий",      "Sodium",       22.990,   "alkali",          1,  3, "[Ne] 3s¹",                           98,    883, 1807, "Дэви"),
    (12, "Mg", "Магний",      "Magnesium",    24.305,   "alkaline",        2,  3, "[Ne] 3s²",                          650,   1090, 1755, "Блэк"),
    (13, "Al", "Алюминий",    "Aluminium",    26.982,   "post_transition",13,  3, "[Ne] 3s² 3p¹",                      660,   2519, 1825, "Эрстед"),
    (14, "Si", "Кремний",     "Silicon",      28.085,   "metalloid",      14,  3, "[Ne] 3s² 3p²",                     1414,   3265, 1824, "Берцелиус"),
    (15, "P",  "Фосфор",      "Phosphorus",   30.974,   "nonmetal",       15,  3, "[Ne] 3s² 3p³",                       44,    281, 1669, "Бранд"),
    (16, "S",  "Сера",        "Sulfur",       32.06,    "nonmetal",       16,  3, "[Ne] 3s² 3p⁴",                      115,    445, "др.", "древние"),
    (17, "Cl", "Хлор",        "Chlorine",     35.45,    "halogen",        17,  3, "[Ne] 3s² 3p⁵",                     -102,    -34, 1774, "Шееле"),
    (18, "Ar", "Аргон",       "Argon",        39.948,   "noble",          18,  3, "[Ne] 3s² 3p⁶",                     -189,   -186, 1894, "Рэлей, Рамзай"),
    (19, "K",  "Калий",       "Potassium",    39.098,   "alkali",          1,  4, "[Ar] 4s¹",                           63,    759, 1807, "Дэви"),
    (20, "Ca", "Кальций",     "Calcium",      40.078,   "alkaline",        2,  4, "[Ar] 4s²",                          842,   1484, 1808, "Дэви"),
    (21, "Sc", "Скандий",     "Scandium",     44.956,   "transition",      3,  4, "[Ar] 3d¹ 4s²",                     1541,   2836, 1879, "Нильсон"),
    (22, "Ti", "Титан",       "Titanium",     47.867,   "transition",      4,  4, "[Ar] 3d² 4s²",                     1668,   3287, 1791, "Грегор"),
    (23, "V",  "Ванадий",     "Vanadium",     50.942,   "transition",      5,  4, "[Ar] 3d³ 4s²",                     1910,   3407, 1801, "Дель Рио"),
    (24, "Cr", "Хром",        "Chromium",     51.996,   "transition",      6,  4, "[Ar] 3d⁵ 4s¹",                     1907,   2671, 1797, "Воклен"),
    (25, "Mn", "Марганец",    "Manganese",    54.938,   "transition",      7,  4, "[Ar] 3d⁵ 4s²",                     1246,   2061, 1774, "Ган"),
    (26, "Fe", "Железо",      "Iron",         55.845,   "transition",      8,  4, "[Ar] 3d⁶ 4s²",                     1538,   2861, "др.", "древние"),
    (27, "Co", "Кобальт",     "Cobalt",       58.933,   "transition",      9,  4, "[Ar] 3d⁷ 4s²",                     1495,   2927, 1735, "Брандт"),
    (28, "Ni", "Никель",      "Nickel",       58.693,   "transition",     10,  4, "[Ar] 3d⁸ 4s²",                     1455,   2913, 1751, "Кронстедт"),
    (29, "Cu", "Медь",        "Copper",       63.546,   "transition",     11,  4, "[Ar] 3d¹⁰ 4s¹",                    1085,   2562, "др.", "древние"),
    (30, "Zn", "Цинк",        "Zinc",         65.38,    "transition",     12,  4, "[Ar] 3d¹⁰ 4s²",                     420,    907, "др.", "древние"),
    (31, "Ga", "Галлий",      "Gallium",      69.723,   "post_transition",13,  4, "[Ar] 3d¹⁰ 4s² 4p¹",                  30,   2204, 1875, "Буабодран"),
    (32, "Ge", "Германий",    "Germanium",    72.630,   "metalloid",      14,  4, "[Ar] 3d¹⁰ 4s² 4p²",                 938,   2833, 1886, "Винклер"),
    (33, "As", "Арсен",       "Arsenic",      74.922,   "metalloid",      15,  4, "[Ar] 3d¹⁰ 4s² 4p³",                 817,    614, "др.", "древние"),
    (34, "Se", "Селен",       "Selenium",     78.971,   "nonmetal",       16,  4, "[Ar] 3d¹⁰ 4s² 4p⁴",                 221,    685, 1817, "Берцелиус"),
    (35, "Br", "Бром",        "Bromine",      79.904,   "halogen",        17,  4, "[Ar] 3d¹⁰ 4s² 4p⁵",                 -7,     59, 1826, "Балар"),
    (36, "Kr", "Криптон",     "Krypton",      83.798,   "noble",          18,  4, "[Ar] 3d¹⁰ 4s² 4p⁶",                -157,   -153, 1898, "Рамзай, Траверс"),
    (37, "Rb", "Рубидий",     "Rubidium",     85.468,   "alkali",          1,  5, "[Kr] 5s¹",                           39,    688, 1861, "Бунзен, Кирхгоф"),
    (38, "Sr", "Стронций",    "Strontium",    87.62,    "alkaline",        2,  5, "[Kr] 5s²",                          777,   1382, 1790, "Кроуфорд"),
    (39, "Y",  "Иттрий",      "Yttrium",      88.906,   "transition",      3,  5, "[Kr] 4d¹ 5s²",                     1526,   3336, 1794, "Гадолин"),
    (40, "Zr", "Цирконий",    "Zirconium",    91.224,   "transition",      4,  5, "[Kr] 4d² 5s²",                     1855,   4409, 1789, "Клапрот"),
    (41, "Nb", "Ниобий",      "Niobium",      92.906,   "transition",      5,  5, "[Kr] 4d⁴ 5s¹",                     2477,   4744, 1801, "Хэтчетт"),
    (42, "Mo", "Молибден",    "Molybdenum",   95.95,    "transition",      6,  5, "[Kr] 4d⁵ 5s¹",                     2623,   4639, 1778, "Шееле"),
    (43, "Tc", "Технеций",    "Technetium",   98,       "transition",      7,  5, "[Kr] 4d⁵ 5s²",                     2157,   4265, 1937, "Перье, Сегре"),
    (44, "Ru", "Рутений",     "Ruthenium",   101.07,    "transition",      8,  5, "[Kr] 4d⁷ 5s¹",                     2334,   4150, 1844, "Клаус"),
    (45, "Rh", "Родий",       "Rhodium",     102.91,    "transition",      9,  5, "[Kr] 4d⁸ 5s¹",                     1964,   3695, 1803, "Волластон"),
    (46, "Pd", "Палладий",    "Palladium",   106.42,    "transition",     10,  5, "[Kr] 4d¹⁰",                        1555,   2963, 1803, "Волластон"),
    (47, "Ag", "Серебро",     "Silver",      107.87,    "transition",     11,  5, "[Kr] 4d¹⁰ 5s¹",                     962,   2162, "др.", "древние"),
    (48, "Cd", "Кадмий",      "Cadmium",     112.41,    "transition",     12,  5, "[Kr] 4d¹⁰ 5s²",                     321,    767, 1817, "Штромейер"),
    (49, "In", "Индий",       "Indium",      114.82,    "post_transition",13,  5, "[Kr] 4d¹⁰ 5s² 5p¹",                157,   2072, 1863, "Рейх, Рихтер"),
    (50, "Sn", "Олово",       "Tin",         118.71,    "post_transition",14,  5, "[Kr] 4d¹⁰ 5s² 5p²",                232,   2602, "др.", "древние"),
    (51, "Sb", "Сурьма",      "Antimony",    121.76,    "metalloid",      15,  5, "[Kr] 4d¹⁰ 5s² 5p³",                631,   1587, "др.", "древние"),
    (52, "Te", "Теллур",      "Tellurium",   127.60,    "metalloid",      16,  5, "[Kr] 4d¹⁰ 5s² 5p⁴",                450,    988, 1782, "Рейхенштейн"),
    (53, "I",  "Йод",         "Iodine",      126.90,    "halogen",        17,  5, "[Kr] 4d¹⁰ 5s² 5p⁵",                114,    184, 1811, "Куртуа"),
    (54, "Xe", "Ксенон",      "Xenon",       131.29,    "noble",          18,  5, "[Kr] 4d¹⁰ 5s² 5p⁶",                -112,   -108, 1898, "Рамзай, Траверс"),
    (55, "Cs", "Цезий",       "Caesium",     132.91,    "alkali",          1,  6, "[Xe] 6s¹",                           28,    671, 1860, "Бунзен, Кирхгоф"),
    (56, "Ba", "Барий",       "Barium",      137.33,    "alkaline",        2,  6, "[Xe] 6s²",                          727,   1897, 1808, "Дэви"),
    (57, "La", "Лантан",      "Lanthanum",   138.91,    "lanthanide",      3,  6, "[Xe] 5d¹ 6s²",                      920,   3464, 1839, "Мосандер"),
    (58, "Ce", "Церий",       "Cerium",      140.12,    "lanthanide",      3,  6, "[Xe] 4f¹ 5d¹ 6s²",                  795,   3443, 1803, "Клапрот"),
    (59, "Pr", "Празеодим",   "Praseodymium",140.91,    "lanthanide",      3,  6, "[Xe] 4f³ 6s²",                      935,   3520, 1885, "Вельсбах"),
    (60, "Nd", "Неодим",      "Neodymium",   144.24,    "lanthanide",      3,  6, "[Xe] 4f⁴ 6s²",                     1024,   3074, 1885, "Вельсбах"),
    (61, "Pm", "Прометий",    "Promethium",  145,       "lanthanide",      3,  6, "[Xe] 4f⁵ 6s²",                     1042,   3000, 1945, "Маринский"),
    (62, "Sm", "Самарий",     "Samarium",    150.36,    "lanthanide",      3,  6, "[Xe] 4f⁶ 6s²",                     1072,   1794, 1879, "Буабодран"),
    (63, "Eu", "Европий",     "Europium",    151.96,    "lanthanide",      3,  6, "[Xe] 4f⁷ 6s²",                      826,   1529, 1901, "Демарсе"),
    (64, "Gd", "Гадолиний",   "Gadolinium",  157.25,    "lanthanide",      3,  6, "[Xe] 4f⁷ 5d¹ 6s²",                 1312,   3273, 1880, "Мариньяк"),
    (65, "Tb", "Тербий",      "Terbium",     158.93,    "lanthanide",      3,  6, "[Xe] 4f⁹ 6s²",                     1356,   3230, 1843, "Мосандер"),
    (66, "Dy", "Диспрозий",   "Dysprosium",  162.50,    "lanthanide",      3,  6, "[Xe] 4f¹⁰ 6s²",                    1407,   2562, 1886, "Буабодран"),
    (67, "Ho", "Гольмий",     "Holmium",     164.93,    "lanthanide",      3,  6, "[Xe] 4f¹¹ 6s²",                    1461,   2720, 1878, "Соре, Делафонтен"),
    (68, "Er", "Эрбий",       "Erbium",      167.26,    "lanthanide",      3,  6, "[Xe] 4f¹² 6s²",                    1529,   2868, 1843, "Мосандер"),
    (69, "Tm", "Тулий",       "Thulium",     168.93,    "lanthanide",      3,  6, "[Xe] 4f¹³ 6s²",                    1545,   1950, 1879, "Клеве"),
    (70, "Yb", "Иттербий",    "Ytterbium",   173.05,    "lanthanide",      3,  6, "[Xe] 4f¹⁴ 6s²",                     824,   1196, 1878, "Мариньяк"),
    (71, "Lu", "Лютеций",     "Lutetium",    174.97,    "lanthanide",      3,  6, "[Xe] 4f¹⁴ 5d¹ 6s²",                1652,   3402, 1907, "Урбен"),
    (72, "Hf", "Гафний",      "Hafnium",     178.49,    "transition",      4,  6, "[Xe] 4f¹⁴ 5d² 6s²",                2233,   4603, 1923, "Костер, Хевеши"),
    (73, "Ta", "Тантал",      "Tantalum",    180.95,    "transition",      5,  6, "[Xe] 4f¹⁴ 5d³ 6s²",                3017,   5458, 1802, "Экеберг"),
    (74, "W",  "Вольфрам",    "Tungsten",    183.84,    "transition",      6,  6, "[Xe] 4f¹⁴ 5d⁴ 6s²",                3422,   5555, 1783, "Элюар"),
    (75, "Re", "Рений",       "Rhenium",     186.21,    "transition",      7,  6, "[Xe] 4f¹⁴ 5d⁵ 6s²",                3186,   5596, 1925, "Ноддак"),
    (76, "Os", "Осмий",       "Osmium",      190.23,    "transition",      8,  6, "[Xe] 4f¹⁴ 5d⁶ 6s²",                3033,   5012, 1803, "Теннант"),
    (77, "Ir", "Иридий",      "Iridium",     192.22,    "transition",      9,  6, "[Xe] 4f¹⁴ 5d⁷ 6s²",                2466,   4428, 1803, "Теннант"),
    (78, "Pt", "Платина",     "Platinum",    195.08,    "transition",     10,  6, "[Xe] 4f¹⁴ 5d⁹ 6s¹",                1768,   3825, 1735, "Уллоа"),
    (79, "Au", "Золото",      "Gold",        196.97,    "transition",     11,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s¹",               1064,   2856, "др.", "древние"),
    (80, "Hg", "Ртуть",       "Mercury",     200.59,    "transition",     12,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s²",                -39,    357, "др.", "древние"),
    (81, "Tl", "Таллий",      "Thallium",    204.38,    "post_transition",13,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p¹",           304,   1473, 1861, "Крукс"),
    (82, "Pb", "Свинец",      "Lead",        207.2,     "post_transition",14,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p²",           327,   1749, "др.", "древние"),
    (83, "Bi", "Висмут",      "Bismuth",     208.98,    "post_transition",15,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p³",           271,   1564, 1753, "Жоффруа"),
    (84, "Po", "Полоний",     "Polonium",    209,       "post_transition",16,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p⁴",           254,    962, 1898, "Кюри"),
    (85, "At", "Астат",       "Astatine",    210,       "halogen",        17,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p⁵",           302,    337, 1940, "Корсон"),
    (86, "Rn", "Радон",       "Radon",       222,       "noble",          18,  6, "[Xe] 4f¹⁴ 5d¹⁰ 6s² 6p⁶",           -71,    -62, 1900, "Дорн"),
    (87, "Fr", "Франций",     "Francium",    223,       "alkali",          1,  7, "[Rn] 7s¹",                           27,    677, 1939, "Перей"),
    (88, "Ra", "Радий",       "Radium",      226,       "alkaline",        2,  7, "[Rn] 7s²",                          700,   1737, 1898, "Кюри"),
    (89, "Ac", "Актиний",     "Actinium",    227,       "actinide",        3,  7, "[Rn] 6d¹ 7s²",                     1050,   3200, 1899, "Дебир"),
    (90, "Th", "Торий",       "Thorium",     232.04,    "actinide",        3,  7, "[Rn] 6d² 7s²",                     1750,   4788, 1829, "Берцелиус"),
    (91, "Pa", "Протактиний", "Protactinium",231.04,    "actinide",        3,  7, "[Rn] 5f² 6d¹ 7s²",                 1568,   4027, 1913, "Фаянс, Гёринг"),
    (92, "U",  "Уран",        "Uranium",     238.03,    "actinide",        3,  7, "[Rn] 5f³ 6d¹ 7s²",                 1132,   4131, 1789, "Клапрот"),
    (93, "Np", "Нептуний",    "Neptunium",   237,       "actinide",        3,  7, "[Rn] 5f⁴ 6d¹ 7s²",                  644,   3902, 1940, "Макмиллан, Абельсон"),
    (94, "Pu", "Плутоний",    "Plutonium",   244,       "actinide",        3,  7, "[Rn] 5f⁶ 7s²",                      640,   3228, 1940, "Сиборг"),
    (95, "Am", "Америций",    "Americium",   243,       "actinide",        3,  7, "[Rn] 5f⁷ 7s²",                     1176,   2607, 1944, "Сиборг"),
    (96, "Cm", "Кюрий",       "Curium",      247,       "actinide",        3,  7, "[Rn] 5f⁷ 6d¹ 7s²",                 1340,   3110, 1944, "Сиборг"),
    (97, "Bk", "Берклий",     "Berkelium",   247,       "actinide",        3,  7, "[Rn] 5f⁹ 7s²",                      986,   2627, 1949, "Сиборг"),
    (98, "Cf", "Калифорний",  "Californium", 251,       "actinide",        3,  7, "[Rn] 5f¹⁰ 7s²",                     900,   1470, 1950, "Сиборг"),
    (99, "Es", "Эйнштейний",  "Einsteinium", 252,       "actinide",        3,  7, "[Rn] 5f¹¹ 7s²",                     860,    996, 1952, "Гиорсо"),
    (100,"Fm", "Фермий",      "Fermium",     257,       "actinide",        3,  7, "[Rn] 5f¹² 7s²",                    1527,    "-", 1952, "Гиорсо"),
    (101,"Md", "Менделевий",  "Mendelevium", 258,       "actinide",        3,  7, "[Rn] 5f¹³ 7s²",                     827,    "-", 1955, "Гиорсо"),
    (102,"No", "Нобелий",     "Nobelium",    259,       "actinide",        3,  7, "[Rn] 5f¹⁴ 7s²",                     827,    "-", 1966, "Флёров"),
    (103,"Lr", "Лоуренсий",   "Lawrencium",  266,       "actinide",        3,  7, "[Rn] 5f¹⁴ 7s² 7p¹",                1627,    "-", 1961, "Гиорсо"),
    (104,"Rf", "Резерфордий", "Rutherfordium",267,      "transition",      4,  7, "[Rn] 5f¹⁴ 6d² 7s²",                2100,   5500, 1964, "Флёров"),
    (105,"Db", "Дубний",      "Dubnium",     268,       "transition",      5,  7, "[Rn] 5f¹⁴ 6d³ 7s²",                "-",    "-", 1967, "Флёров"),
    (106,"Sg", "Сиборгий",    "Seaborgium",  269,       "transition",      6,  7, "[Rn] 5f¹⁴ 6d⁴ 7s²",                "-",    "-", 1974, "Гиорсо"),
    (107,"Bh", "Борий",       "Bohrium",     270,       "transition",      7,  7, "[Rn] 5f¹⁴ 6d⁵ 7s²",                "-",    "-", 1981, "ГСИ"),
    (108,"Hs", "Хассий",      "Hassium",     269,       "transition",      8,  7, "[Rn] 5f¹⁴ 6d⁶ 7s²",                "-",    "-", 1984, "ГСИ"),
    (109,"Mt", "Мейтнерий",   "Meitnerium",  278,       "transition",      9,  7, "[Rn] 5f¹⁴ 6d⁷ 7s²",                "-",    "-", 1982, "ГСИ"),
    (110,"Ds", "Дармштадтий","Darmstadtium", 281,       "transition",     10,  7, "[Rn] 5f¹⁴ 6d⁸ 7s²",                "-",    "-", 1994, "ГСИ"),
    (111,"Rg", "Рентгений",   "Roentgenium", 282,       "transition",     11,  7, "[Rn] 5f¹⁴ 6d⁹ 7s²",                "-",    "-", 1994, "ГСИ"),
    (112,"Cn", "Коперниций",  "Copernicium", 285,       "transition",     12,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s²",               "-",    "-", 1996, "ГСИ"),
    (113,"Nh", "Нихоний",     "Nihonium",    286,       "post_transition",13,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p¹",           "-",    "-", 2003, "РИКЕН"),
    (114,"Fl", "Флеровий",    "Flerovium",   289,       "post_transition",14,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p²",           "-",    "-", 1998, "ОИЯИ"),
    (115,"Mc", "Московий",    "Moscovium",   290,       "post_transition",15,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p³",           "-",    "-", 2003, "ОИЯИ"),
    (116,"Lv", "Ливерморий",  "Livermorium", 293,       "post_transition",16,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p⁴",           "-",    "-", 2000, "ОИЯИ"),
    (117,"Ts", "Теннессин",   "Tennessine",  294,       "halogen",        17,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p⁵",           "-",    "-", 2010, "ОИЯИ"),
    (118,"Og", "Оганесон",    "Oganesson",   294,       "noble",          18,  7, "[Rn] 5f¹⁴ 6d¹⁰ 7s² 7p⁶",           "-",    "-", 2002, "ОИЯИ"),
]


def get_grid_position(atomic_number: int, group: int, period: int) -> tuple:
    if 57 <= atomic_number <= 71:
        return (9, atomic_number - 57 + 3)
    if 89 <= atomic_number <= 103:
        return (10, atomic_number - 89 + 3)
    return (period, group)


# ============================================================
#  Поиск VFS / Desktop
# ============================================================

def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return getattr(p.desktop_ref, "vfs", None)
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "vfs"):
            return top.vfs
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "vfs"):
            return ref.vfs
    return None


def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return p.desktop_ref
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
        ref = getattr(top, "desktop_ref", None)
        if ref is not None:
            return ref
    return None


# ============================================================
#  Виджет таблицы
# ============================================================

class TableWidget(QWidget):
    element_clicked = None

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import Signal as _Signal
        self.setMinimumSize(900, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        self.cell_w = 60
        self.cell_h = 60
        self.gap = 2

        self.grid = {}
        self._build_grid()

        self.visible_numbers = set(e[0] for e in ELEMENTS)
        self._hovered = None
        self._click_callback = None

    def _build_grid(self):
        for e in ELEMENTS:
            num = e[0]
            group = e[6]
            period = e[7]
            pos = get_grid_position(num, group, period)
            self.grid[pos] = e

    def set_click_callback(self, fn):
        self._click_callback = fn

    def set_visible(self, numbers: set):
        self.visible_numbers = numbers
        self.update()

    def _cell_rect(self, row: int, col: int) -> QRectF:
        x = (col - 1) * (self.cell_w + self.gap)
        y = (row - 1) * (self.cell_h + self.gap)
        if row >= 9:
            y += self.cell_h * 0.4
        return QRectF(x, y, self.cell_w, self.cell_h)

    def _min_size(self) -> tuple:
        w = 18 * (self.cell_w + self.gap) + 20
        h = 10 * (self.cell_h + self.gap) + self.cell_h * 0.5
        return (w, h)

    def sizeHint(self):
        return QSize(*self._min_size())

    def minimumSizeHint(self):
        return QSize(*self._min_size())

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        for (row, col), element in self.grid.items():
            rect = self._cell_rect(row, col)
            if rect.contains(pos):
                if element[0] in self.visible_numbers and self._click_callback:
                    self._click_callback({
                        "num": element[0],
                        "sym": element[1],
                        "name_ru": element[2],
                        "name_en": element[3],
                        "mass": element[4],
                        "category": element[5],
                        "group": element[6],
                        "period": element[7],
                        "config": element[8],
                        "t_melt": element[9],
                        "t_boil": element[10],
                        "year": element[11],
                        "discoverer": element[12],
                    })
                return

    def mouseMoveEvent(self, e):
        pos = e.position()
        new_hover = None
        for (row, col), element in self.grid.items():
            rect = self._cell_rect(row, col)
            if rect.contains(pos):
                new_hover = (row, col)
                break
        if new_hover != self._hovered:
            self._hovered = new_hover
            self.update()
            if new_hover:
                elem = self.grid[new_hover]
                self.setToolTip(
                    f"{elem[2]} ({elem[1]})\n"
                    f"№{elem[0]}  ·  Масса: {elem[4]}\n"
                    f"{CATEGORIES[elem[5]]['name']}"
                )
            else:
                self.setToolTip("")

    def leaveEvent(self, e):
        self._hovered = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        p.fillRect(self.rect(), QColor("#0A0E1A"))

        p.setPen(QColor(255, 255, 255, 80))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        for col in range(1, 19):
            rect = self._cell_rect(0, col)
            rect.moveTop(-10)
            p.drawText(rect, Qt.AlignCenter, str(col))

        for row in range(1, 8):
            rect = self._cell_rect(row, 0)
            rect.moveLeft(-18)
            p.drawText(rect, Qt.AlignCenter, str(row))

        accent = state().get("accent", "#6EC6FF")
        for (row, col), element in self.grid.items():
            self._draw_cell(p, element, row, col, accent)

        sep_y = self._cell_rect(9, 1).top() - 10
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(0, int(sep_y), self.width(), int(sep_y))

    def _draw_cell(self, p: QPainter, element: tuple, row: int, col: int, accent: str):
        num, sym, name_ru = element[0], element[1], element[2]
        cat_key = element[5]
        cat = CATEGORIES.get(cat_key, {"color": "#6EC6FF", "name": "?"})

        rect = self._cell_rect(row, col)
        is_visible = num in self.visible_numbers
        is_hovered = self._hovered == (row, col)

        base_color = QColor(cat["color"])

        if not is_visible:
            bg = QColor(base_color)
            bg.setAlpha(20)
            border = QColor(base_color)
            border.setAlpha(30)
            text_color = QColor(255, 255, 255, 40)
        elif is_hovered:
            bg = QColor(base_color)
            bg.setAlpha(200)
            border = QColor("white")
            text_color = QColor("white")
        else:
            bg = QColor(base_color)
            bg.setAlpha(60)
            border = base_color
            border.setAlpha(180)
            text_color = QColor("white")

        p.setBrush(QBrush(bg))
        p.setPen(QPen(border, 1.5))
        p.drawRoundedRect(rect, 6, 6)

        if not is_visible:
            return

        p.setPen(text_color)
        font = QFont()
        font.setPointSize(7)
        p.setFont(font)
        p.drawText(QRectF(rect.left() + 4, rect.top() + 2,
                          rect.width() * 0.5, 10),
                   Qt.AlignLeft, str(num))

        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(rect.left(), rect.top() + 8,
                          rect.width(), rect.height() * 0.55),
                   Qt.AlignCenter, sym)

        font = QFont()
        font.setPointSize(6)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 160 if is_hovered else 120))
        name_short = name_ru
        if len(name_short) > 9:
            name_short = name_short[:8] + "."
        p.drawText(QRectF(rect.left() + 1, rect.bottom() - 14,
                          rect.width() - 2, 12),
                   Qt.AlignCenter, name_short)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)
    desktop = _get_desktop(root)

    # Левая панель
    side = QWidget()
    side.setFixedWidth(280)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(16, 16, 16, 16)
    sl.setSpacing(10)

    title = QLabel("⚗️  Таблица Менделеева")
    title.setStyleSheet("color: white; font-size: 15px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    search_lbl = QLabel("ПОИСК")
    search_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 4px;
    """)
    sl.addWidget(search_lbl)

    search_input = QLineEdit()
    search_input.setPlaceholderText("Название, символ или №")
    search_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    sl.addWidget(search_input)

    cat_lbl = QLabel("КАТЕГОРИИ")
    cat_lbl.setStyleSheet(search_lbl.styleSheet())
    sl.addWidget(cat_lbl)

    cat_list = QListWidget()
    cat_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 7px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)

    all_item = QListWidgetItem("🌐  Все элементы")
    all_item.setData(Qt.UserRole, "__all__")
    cat_list.addItem(all_item)

    for key, data in CATEGORIES.items():
        cnt = sum(1 for e in ELEMENTS if e[5] == key)
        item = QListWidgetItem(f"●  {data['name']}  ({cnt})")
        color = QColor(data["color"])
        item.setForeground(color)
        item.setData(Qt.UserRole, key)
        cat_list.addItem(item)

    cat_list.setCurrentRow(0)
    sl.addWidget(cat_list, 1)

    hint = QLabel("🖱 Клик по элементу — подробная информация")
    hint.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        background: rgba(0,0,0,0.20);
        border-radius: 8px;
        padding: 8px 10px;
    """)
    hint.setWordWrap(True)
    sl.addWidget(hint)

    h.addWidget(side)

    # Центр
    center = QWidget()
    cl = QVBoxLayout(center)
    cl.setContentsMargins(20, 20, 20, 20)
    cl.setSpacing(14)

    info_lbl = QLabel("Все элементы: 118")
    info_lbl.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 14px; font-weight: 600;")
    cl.addWidget(info_lbl)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet("""
        QScrollArea { background: transparent; border: none; }
        QScrollBar:vertical, QScrollBar:horizontal {
            background: transparent; width: 8px; height: 8px;
        }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
            background: rgba(255,255,255,0.20);
            border-radius: 4px;
            min-height: 30px;
            min-width: 30px;
        }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    """)

    table = TableWidget()
    scroll.setWidget(table)
    cl.addWidget(scroll, 1)

    # Легенда
    legend_row = QHBoxLayout()
    legend_row.setSpacing(8)
    legend_row.setContentsMargins(0, 6, 0, 0)

    for key, data in CATEGORIES.items():
        rgb = ','.join(str(int(data['color'][i:i+2], 16)) for i in (1, 3, 5))
        chip = QLabel(f"  {data['name']}  ")
        chip.setStyleSheet(f"""
            background: rgba({rgb}, 0.20);
            color: {data['color']};
            border: 1px solid {data['color']};
            border-radius: 8px;
            padding: 3px 8px;
            font-size: 9px;
        """)
        legend_row.addWidget(chip)

    legend_row.addStretch(1)
    cl.addLayout(legend_row)

    h.addWidget(center, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def apply_filter():
        query = search_input.text().strip().lower()
        cur = cat_list.currentItem()
        cat_key = cur.data(Qt.UserRole) if cur else "__all__"

        visible = set()
        for e in ELEMENTS:
            num, sym, name_ru, name_en = e[0], e[1], e[2], e[3]
            cat = e[5]

            if cat_key != "__all__" and cat != cat_key:
                continue

            if query:
                if (query not in name_ru.lower() and
                    query not in name_en.lower() and
                    query not in sym.lower() and
                    query not in str(num)):
                    continue

            visible.add(num)

        table.set_visible(visible)

        total = len(visible)
        if query or cat_key != "__all__":
            info_lbl.setText(f"Найдено: {total} элементов")
        else:
            info_lbl.setText(f"Все элементы: {total}")

    search_input.textChanged.connect(apply_filter)
    cat_list.itemClicked.connect(lambda _: apply_filter())

    def show_element_info(data: dict):
        dlg = QDialog(root)
        dlg.setWindowTitle(f"{data['name_ru']} ({data['sym']})")
        dlg.setFixedSize(500, 580)
        dlg.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QLabel { color: white; }
        """)

        cat = CATEGORIES.get(data["category"], {"name": "?", "color": "#6EC6FF"})
        rgb = ','.join(str(int(cat['color'][i:i+2], 16)) for i in (1, 3, 5))

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        header = QWidget()
        header.setFixedHeight(140)
        header.setStyleSheet(f"""
            QWidget {{
                background: rgba({rgb}, 0.18);
                border: 2px solid {cat['color']};
                border-radius: 16px;
            }}
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 12, 20, 12)

        sym_lbl = QLabel(data["sym"])
        sym_lbl.setStyleSheet(f"""
            color: {cat['color']};
            font-size: 84px;
            font-weight: 700;
            background: transparent;
            border: none;
        """)
        hl.addWidget(sym_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        name = QLabel(data["name_ru"])
        name.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        text_col.addWidget(name)

        name_en = QLabel(data["name_en"])
        name_en.setStyleSheet("""
            color: rgba(255,255,255,0.65);
            font-size: 14px;
            font-style: italic;
            background: transparent;
            border: none;
        """)
        text_col.addWidget(name_en)

        cat_lbl = QLabel(cat["name"])
        cat_lbl.setStyleSheet(f"""
            color: {cat['color']};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        text_col.addWidget(cat_lbl)

        text_col.addStretch(1)
        hl.addLayout(text_col, 1)

        lay.addWidget(header)

        props = [
            ("Атомный номер", str(data["num"])),
            ("Атомная масса", f"{data['mass']} а.е.м."),
            ("Период", str(data["period"])),
            ("Группа", str(data["group"])),
            ("Электронная конфигурация", data["config"]),
            ("Температура плавления", f"{data['t_melt']} °C" if data['t_melt'] != "-" else 'неизвестно'),
            ("Температура кипения", f"{data['t_boil']} °C" if data['t_boil'] != "-" else 'неизвестно'),
            ("Год открытия", str(data["year"])),
            ("Первооткрыватель", data["discoverer"]),
        ]

        props_widget = QWidget()
        pl = QGridLayout(props_widget)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setHorizontalSpacing(14)
        pl.setVerticalSpacing(8)

        for i, (k, v) in enumerate(props):
            key_lbl = QLabel(k)
            key_lbl.setStyleSheet("""
                color: rgba(255,255,255,0.55);
                font-size: 12px;
                background: transparent;
            """)
            val_lbl = QLabel(str(v))
            val_lbl.setStyleSheet("""
                color: white;
                font-size: 12px;
                font-weight: 600;
                background: transparent;
            """)
            val_lbl.setWordWrap(True)
            pl.addWidget(key_lbl, i, 0, Qt.AlignTop)
            pl.addWidget(val_lbl, i, 1)

        lay.addWidget(props_widget)
        lay.addStretch(1)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)

        save_btn = QPushButton("💾  Сохранить карточку")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,231,183,0.18);
                color: white;
                border: 1px solid rgba(110,231,183,0.55);
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 13px;
            }
            QPushButton:hover { background: rgba(110,231,183,0.40); }
        """)
        save_btn.clicked.connect(lambda: save_card_png(data, cat))
        btns.addButton(save_btn, QDialogButtonBox.ActionRole)

        btns.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 12px;
                min-width: 100px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.20); }
        """)
        lay.addWidget(btns)

        dlg.exec()

    def save_card_png(data: dict, cat: dict):
        if vfs is None:
            return
        try:
            pm = render_element_card(data, cat)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.WriteOnly)
            pm.save(buf, "PNG")
            buf.close()

            vfs.mkdir(OUT_DIR)
            path = f"{OUT_DIR}/{data['num']:03d}_{data['sym']}.png"
            vfs.write_bytes(path, bytes(ba))

            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("Карточка сохранена", path)
            QMessageBox.information(root, "Сохранено",
                f"Карточка элемента {data['sym']} сохранена:\n{path}")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    def render_element_card(data: dict, cat: dict) -> QPixmap:
        W, H = 600, 800
        pm = QPixmap(W, H)
        pm.fill(QColor("#0A0E1A"))

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        grad = QLinearGradient(0, 0, 0, 300)
        base = QColor(cat["color"])
        grad.setColorAt(0, QColor(base.red(), base.green(), base.blue(), 100))
        grad.setColorAt(1, QColor(base.red(), base.green(), base.blue(), 0))
        p.fillRect(0, 0, W, 300, QBrush(grad))

        p.setPen(QColor(cat["color"]))
        font = QFont()
        font.setPointSize(140)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, 60, W, 200), Qt.AlignCenter, data["sym"])

        p.setPen(QColor("white"))
        font = QFont()
        font.setPointSize(36)
        font.setWeight(QFont.Light)
        p.setFont(font)
        p.drawText(QRectF(0, 270, W, 50), Qt.AlignCenter, data["name_ru"])

        p.setPen(QColor(255, 255, 255, 140))
        font = QFont()
        font.setPointSize(18)
        font.setItalic(True)
        p.setFont(font)
        p.drawText(QRectF(0, 320, W, 30), Qt.AlignCenter, data["name_en"])

        p.setPen(QColor(cat["color"]))
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, 370, W, 40), Qt.AlignCenter, f"№ {data['num']}")

        p.setPen(QColor(cat["color"]))
        font = QFont()
        font.setPointSize(14)
        p.setFont(font)
        p.drawText(QRectF(0, 420, W, 30), Qt.AlignCenter, cat["name"])

        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawLine(50, 480, W - 50, 480)

        props = [
            ("Атомная масса", f"{data['mass']} а.е.м."),
            ("Период / Группа", f"{data['period']} / {data['group']}"),
            ("Электронная конфигурация", data["config"]),
            ("Температура плавления", f"{data['t_melt']} °C" if data['t_melt'] != "-" else "—"),
            ("Температура кипения", f"{data['t_boil']} °C" if data['t_boil'] != "-" else "—"),
            ("Год открытия", str(data["year"])),
            ("Первооткрыватель", data["discoverer"]),
        ]

        y = 510
        for k, v in props:
            p.setPen(QColor(255, 255, 255, 100))
            font = QFont()
            font.setPointSize(11)
            p.setFont(font)
            p.drawText(QRectF(50, y, 250, 26),
                       Qt.AlignLeft | Qt.AlignVCenter, k)

            p.setPen(QColor("white"))
            font = QFont()
            font.setPointSize(12)
            font.setBold(True)
            p.setFont(font)
            p.drawText(QRectF(310, y, W - 360, 26),
                       Qt.AlignLeft | Qt.AlignVCenter, str(v))
            y += 32

        p.setPen(QColor(255, 255, 255, 60))
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        p.drawText(QRectF(0, H - 30, W, 20), Qt.AlignCenter,
                   "MountOS · Таблица Менделеева")

        p.end()
        return pm

    table.set_click_callback(show_element_info)
    apply_filter()

    return root


# Отдельный импорт QListWidget и QListWidgetItem — они используются в build()
from PySide6.QtWidgets import QListWidget, QListWidgetItem