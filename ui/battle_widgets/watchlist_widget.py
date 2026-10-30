# -*- coding: utf-8 -*-
"""
模块1：我的自选
- 表格：股票名称 | 股票代码 | 现价 | 涨幅 | 添加 | 振幅 | 市值 | 题材
- 题材：选股雷达同源数据 services/concept_matcher
- 点击"股票名称"单元格才跳转个股分析，其他单元格不跳转
- 添加/删除自选，持久化到 data/watchlist.json
- 批量实时行情 via get_realtime_quotes_http
- 排序：手动上下移（持久化到 watchlist.json）+ 列头三态排序（临时查看）+ 拖拽排序
"""
import os
import json
import locale

from PyQt6.QtWidgets import (
    QHBoxLayout, QPushButton, QLineEdit, QCompleter,
    QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QStringListModel, QTimer, QEvent, pyqtSignal

from .base import (
    BattleModuleBase, make_table, set_table_item,
    pct_color, format_pct, BC, L, CTRL_COL_TITLE,
)
from .widget_common import make_add_button, get_radar_theme, get_industry_map

WATCHLIST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'watchlist.json'
)
STOCK_NAMES_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'stock_names_cache.json'
)

# 列定义
COL_NAME, COL_CODE, COL_PRICE, COL_PCT = 0, 1, 2, 3
COL_AMP, COL_MV, COL_THEME = 4, 5, 6
COL_CTRL = 7
HEADER_LABELS = ['股票名称', '股票代码', '现价', '涨幅', '振幅', '市值', '题材',
                 CTRL_COL_TITLE]
# 不参与列头排序的列（按钮列）
_NON_SORT_COLS = set()

# 尝试启用中文 collation，用于按名称拼音排序
for _loc in ('Chinese (Simplified)_China.936', 'zh_CN.UTF-8', 'chinese'):
    try:
        locale.setlocale(locale.LC_COLLATE, _loc)
        break
    except Exception:
        continue


def _name_sort_key(name):
    """中文按拼音排序（通过 locale.strxfrm），失败回退到原字符串"""
    try:
        return locale.strxfrm(str(name))
    except Exception:
        return str(name)


def _num_sort_key(v):
    """数值列排序键：None/无法解析排到最后"""
    if v is None:
        return (1, 0.0)
    try:
        return (0, float(v))
    except (TypeError, ValueError):
        return (1, 0.0)


def _reverse_str(s):
    """将字符串逐字符映射到反向 code point，用于"降序"比较。
    中文等 BMP 字符均适用，使反向后的升序等价于原字符串降序。"""
    return ''.join(chr(0x10FFFF - ord(c)) for c in str(s))


class WatchlistWidget(BattleModuleBase):
    """我的自选模块"""

    # 点击股票名称 -> 通知主窗口跳转个股分析(code, name)
    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__('★ 我的自选', parent)
        # 复用 core/watchlist.py 的单例管理器，与"自选评分"Tab 共享同一份数据，
        # 避免两个组件各自持有内存副本导致互相覆盖。
        from core.watchlist import get_watchlist_manager
        self.watchlist_manager = get_watchlist_manager()
        self._watchlist = self.watchlist_manager.stocks  # 直接引用同一份 list
        self._stock_names = {}  # {name: code}
        self._code_to_name = {}  # {code: name}
        self._last_quotes = {}  # 最近一次行情，用于列头排序/移动后立即重渲染
        self._themes = {}  # {code: 题材}
        self._sort_state = None  # None 或 (col:int, order:Qt.SortOrder)
        self._loading = False  # 填充表格期间临时屏蔽 selectionChanged，避免递归
        self._load_stock_names()
        self._load_watchlist()
        self._build_content()
        # 监听 manager 变化：其他模块（如"自选评分"Tab）增删自选时，本面板自动同步
        try:
            self.watchlist_manager.add_change_callback(self._on_manager_changed)
        except Exception as e:
            print(f'[自选] 注册 manager 变化回调失败: {e}', flush=True)
        # 延迟到事件循环启动后再加载行情，避免初始化阶段线程崩溃
        QTimer.singleShot(100, self.refresh)
        # 每30秒刷新
        self.start_refresh(30000)

    def _on_manager_changed(self):
        """manager 单例数据变化时（其他UI增删自选），重新引用并刷新表格"""
        def _sync():
            try:
                self._watchlist = self.watchlist_manager.stocks
                for item in self._watchlist:
                    item['code'] = str(item.get('code', '')).strip()
                    if not item.get('name'):
                        item['name'] = self._code_to_name.get(item['code'], item['code'])
                self._update_title_count()
                self._populate_table(self._last_quotes)
                self.refresh()
            except Exception as e:
                print(f'[自选] 同步 manager 变化失败: {e}', flush=True)
        QTimer.singleShot(0, _sync)

    # ----------------------------------------------------------
    # 数据持久化
    # ----------------------------------------------------------
    def _load_stock_names(self):
        """加载股票名称→代码映射，并构建代码→名称反向映射
        支持两种JSON格式：
        1. 带metadata包装: {"timestamp":..., "stock_names": {"名称": "代码", ...}}
        2. 直接映射: {"名称": "代码", ...} 或 {"代码": "名称", ...}
        """
        self._stock_names = {}
        self._code_to_name = {}
        try:
            if os.path.exists(STOCK_NAMES_CACHE_PATH):
                with open(STOCK_NAMES_CACHE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 提取实际的映射字典
                if isinstance(data, dict) and 'stock_names' in data:
                    raw = data['stock_names']
                elif isinstance(data, dict):
                    raw = data
                else:
                    raw = {}
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        name = str(k).strip()
                        code = str(v).strip()
                        if not name or not code:
                            continue
                        # 判断方向：key是6位数字则为代码，否则为名称
                        if len(name) == 6 and name.isdigit():
                            # code -> name 格式
                            self._code_to_name[name] = code
                            self._stock_names[code] = name
                        else:
                            # name -> code 格式（同时补全反向映射 code->name）
                            self._stock_names[name] = code
                            self._code_to_name[code] = name
        except Exception as e:
            print(f'[自选] 股票名称缓存加载失败: {e}', flush=True)
            self._stock_names = {}
            self._code_to_name = {}
        print(f'[自选] 名称缓存: name->code={len(self._stock_names)}, '
              f'code->name={len(self._code_to_name)}', flush=True)

    def _load_watchlist(self):
        """从 manager 单例加载自选股（manager 已从 data/watchlist.json 读入）"""
        try:
            # 与 manager 单例保持同一 list 引用
            self._watchlist = self.watchlist_manager.stocks
            # 确保每条有 code 和 name，并补全缺失的 name
            for item in self._watchlist:
                item['code'] = str(item.get('code', '')).strip()
                if not item.get('name'):
                    item['name'] = self._code_to_name.get(item['code'], item['code'])
            print(f'[自选] 加载完成: 共 {len(self._watchlist)} 只, 路径={WATCHLIST_PATH}',
                  flush=True)
            for it in self._watchlist:
                print(f'[自选]   - {it.get("code")} {it.get("name")}', flush=True)
        except Exception as e:
            print(f'[自选] 自选股加载失败: {e}', flush=True)
            self._watchlist = []

    def _save_watchlist(self, notify=True):
        """保存自选股到本地（通过 manager 单例写文件，避免双实例互相覆盖）"""
        try:
            # 让 manager.stocks 指向最新的 self._watchlist（顺序/删除已直接作用其上）
            if self.watchlist_manager.stocks is not self._watchlist:
                self.watchlist_manager.stocks = self._watchlist
            os.makedirs(os.path.dirname(WATCHLIST_PATH), exist_ok=True)
            with open(WATCHLIST_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._watchlist, f, indent=2, ensure_ascii=False)
            print(f'[自选] 保存成功: 共 {len(self._watchlist)} 只 -> {WATCHLIST_PATH}',
                  flush=True)
            for it in self._watchlist:
                print(f'[自选]   - {it.get("code")} {it.get("name")}', flush=True)
            # 通知其他 UI（如"自选评分"Tab）刷新
            if notify:
                try:
                    self.watchlist_manager._notify_change()
                except Exception:
                    pass
        except Exception as e:
            print(f'[自选] 保存失败: {e}', flush=True)
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, '自选股保存失败',
                                    f'写入 {WATCHLIST_PATH} 失败:\n{e}')
            except Exception:
                pass

    # ----------------------------------------------------------
    # UI构建
    # ----------------------------------------------------------
    def _build_content(self):
        # 操作栏
        op_bar = QHBoxLayout()
        op_bar.setSpacing(6)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText('输入代码/名称，如 002838 或 道恩')
        self.code_input.setFixedHeight(26)
        self.code_input.setStyleSheet(f"""
            QLineEdit{{background:{BC.BG_HEADER};color:{BC.TEXT};
            border:1px solid {BC.BORDER};border-radius:5px;padding:0 8px;font-size:12px;}}
            QLineEdit:focus{{border:1px solid {BC.BLUE};}}
        """)
        self.code_input.returnPressed.connect(self._on_add)
        # 自动补全
        completer_items = []
        for name, code in self._stock_names.items():
            completer_items.append(f'{code} {name}')
        completer = QCompleter(completer_items)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.code_input.setCompleter(completer)

        self.add_btn = QPushButton('＋ 添加')
        self.add_btn.setFixedHeight(26)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(f"""
            QPushButton{{background:{BC.BLUE};color:white;border:none;border-radius:5px;
            padding:0 12px;font-size:12px;font-weight:bold;}}
            QPushButton:hover{{background:#3B82F6;}}
        """)
        self.add_btn.clicked.connect(self._on_add)

        self.del_btn = QPushButton('－ 删除')
        self.del_btn.setFixedHeight(26)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setStyleSheet(f"""
            QPushButton{{background:{BC.BG_HEADER};color:{BC.TEXT2};
            border:1px solid {BC.BORDER};border-radius:5px;padding:0 12px;font-size:12px;}}
            QPushButton:hover{{background:{BC.RED};color:white;border-color:{BC.RED};}}
        """)
        self.del_btn.clicked.connect(self._on_delete)

        # 上移/下移按钮（样式与删除按钮一致）
        btn_style = f"""
            QPushButton{{background:{BC.BG_HEADER};color:{BC.TEXT2};
            border:1px solid {BC.BORDER};border-radius:5px;padding:0 10px;font-size:12px;}}
            QPushButton:hover:enabled{{background:{BC.BLUE};color:white;border-color:{BC.BLUE};}}
            QPushButton:disabled{{color:{BC.TEXT3 if hasattr(BC,'TEXT3') else '#999'};
            background:{BC.BG_HEADER};border:1px solid {BC.BORDER};}}
        """
        self.up_btn = QPushButton('↑ 上移')
        self.up_btn.setFixedHeight(26)
        self.up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.up_btn.setStyleSheet(btn_style)
        self.up_btn.clicked.connect(self._move_up)

        self.down_btn = QPushButton('↓ 下移')
        self.down_btn.setFixedHeight(26)
        self.down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.down_btn.setStyleSheet(btn_style)
        self.down_btn.clicked.connect(self._move_down)

        op_bar.addWidget(self.code_input, 1)
        # 按钮全部改成右键菜单，节省空间
        self.content_layout.addLayout(op_bar)

        # 表格
        self.table = make_table(8, HEADER_LABELS)
        # 列宽按「表头 + 典型内容」的真实像素给量（不再写死偏宽的数字列），
        # 省下来的宽度全部给「题材」列（COL_THEME 是 Stretch），让它多显示几个字。
        self.table.setColumnWidth(0, 78)     # 股票名称（4~5 字）
        self.table.setColumnWidth(1, 62)     # 股票代码（6 位）
        self.table.setColumnWidth(2, 56)     # 现价
        self.table.setColumnWidth(3, 68)     # 涨幅（+10.03%）
        self.table.setColumnWidth(4, 68)     # 振幅（+10.03%）
        self.table.setColumnWidth(5, 62)     # 市值（338亿）
        self.table.setColumnWidth(6, 96)     # 题材（还会被 Stretch 拉宽）
        self.table.setColumnWidth(COL_CTRL, 66)   # 控盘（99候选）
        # 「控盘」插到末尾后不能再让末列自动拉伸（会把它撑开），
        # 改成指定「题材」列吃剩余宽度
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            COL_THEME, QHeaderView.ResizeMode.Stretch)
        # 确保垂直滚动条在需要时自动出现，支持无限制添加自选
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 列头排序：点击表头触发三态切换（降序->升序->取消）
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        # 不使用 QTableWidget 内置自动排序（数字/中文拼音需自定义 key）
        self.table.setSortingEnabled(False)

        # 仅点击"股票名称"单元格跳转个股分析，其他单元格不跳转
        self.table.cellClicked.connect(self._on_cell_clicked)

        # 拖拽排序（内部移动）：仅在无列头排序时有意义
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.viewport().setAcceptDrops(True)
        # 用 eventFilter 拦截 table 的 Drop 事件（table 是子控件，直接重写本类 dropEvent 无效）
        self.table.installEventFilter(self)

        # 右键菜单：删除自选
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        # 选中变化时刷新上下移按钮可用状态
        self.table.itemSelectionChanged.connect(self._update_move_buttons_enabled)

        self.content_layout.addWidget(self.table, 1)

        self._update_title_count()
        self._update_move_buttons_enabled()

    def _update_title_count(self):
        self.title_label.setText(f'★ 我的自选（{len(self._watchlist)}只）')

    # ----------------------------------------------------------
    # 表头标签（带排序箭头）
    # ----------------------------------------------------------
    def _refresh_header_labels(self):
        labels = list(HEADER_LABELS)
        if self._sort_state is not None:
            col, order = self._sort_state
            arrow = '↓' if order == Qt.SortOrder.DescendingOrder else '↑'
            if 0 <= col < len(labels):
                labels[col] = f'{labels[col]} {arrow}'
        self.table.setHorizontalHeaderLabels(labels)

    # ----------------------------------------------------------
    # 列头排序
    # ----------------------------------------------------------
    def _on_header_clicked(self, col):
        """三态切换：降序 -> 升序 -> 取消"""
        if col in _NON_SORT_COLS:
            return  # 按钮列不排序
        if self._sort_state is None:
            self._sort_state = (col, Qt.SortOrder.DescendingOrder)
        else:
            cur_col, cur_order = self._sort_state
            if col != cur_col:
                self._sort_state = (col, Qt.SortOrder.DescendingOrder)
            else:
                if cur_order == Qt.SortOrder.DescendingOrder:
                    self._sort_state = (col, Qt.SortOrder.AscendingOrder)
                else:
                    self._sort_state = None  # 第三次点击取消
        self._refresh_header_labels()
        # 立即用缓存行情重渲染，不重新拉网络
        self._populate_table(self._last_quotes)
        self._update_move_buttons_enabled()

    def _get_display_order(self):
        """根据 _sort_state 计算 self._watchlist 索引的显示顺序列表。
        不修改 self._watchlist 本身。"""
        n = len(self._watchlist)
        order = list(range(n))
        if self._sort_state is None or n == 0:
            return order
        col, sort_order = self._sort_state
        reverse = (sort_order == Qt.SortOrder.DescendingOrder)

        def key_fn(idx):
            item = self._watchlist[idx]
            code = item.get('code', '')
            q = self._last_quotes.get(code, {}) if self._last_quotes else {}
            if col == COL_NAME:
                s = _name_sort_key(item.get('name', ''))
                return (0, _reverse_str(s) if reverse else s, 0)
            if col == COL_CODE:
                s = str(code)
                return (0, _reverse_str(s) if reverse else s, 0)
            if col == COL_THEME:
                s = _name_sort_key(self._themes.get(code, '') if self._themes else '')
                return (0, _reverse_str(s) if reverse else s, 0)
            # 数值列：None 永远排最后
            if col == COL_PRICE:
                v = q.get('price')
            elif col == COL_AMP:
                v = q.get('amplitude')
            elif col == COL_MV:
                v = q.get('total_mv')
            elif col == COL_PCT:
                v = q.get('pct_chg')
            elif col == COL_CTRL:
                v = (q.get('ctrl') or {}).get('score')
            else:
                v = 0
            if v is None:
                return (1, 0.0, 0)  # None 永远最后
            try:
                fv = float(v)
            except (TypeError, ValueError):
                return (1, 0.0, 0)
            # 用升序比较：降序时取负
            return (0, -fv if reverse else fv, 0)

        # 稳定排序：相同 key 保持原相对顺序（自定义顺序）
        order.sort(key=key_fn)
        return order

    # ----------------------------------------------------------
    # 表格渲染
    # ----------------------------------------------------------
    def _populate_table(self, quotes):
        """根据当前排序状态把 self._watchlist 渲染到表格。
        quotes: {code: {price, pct_chg, name, ...}} 或 None（失败时）
        """
        self._loading = True
        try:
            n = len(self._watchlist)
            self.table.setRowCount(n)
            if n == 0:
                self._refresh_header_labels()
                return

            display_order = self._get_display_order()
            for view_row, data_idx in enumerate(display_order):
                item = self._watchlist[data_idx]
                code = item['code']
                name = item['name']
                q = (quotes or {}).get(code, {}) or {}
                price = q.get('price')
                pct = q.get('pct_chg')
                # 名称优先用行情返回的
                if q.get('name') and q['name'] != code:
                    name = q['name']
                    item['name'] = name

                set_table_item(self.table, view_row, COL_NAME, name, BC.TEXT, bold=True)
                # 把数据索引和 code 存在 item 上，方便反查
                self.table.item(view_row, COL_NAME).setData(
                    Qt.ItemDataRole.UserRole, data_idx)
                self.table.item(view_row, COL_NAME).setData(
                    Qt.ItemDataRole.UserRole + 1, code)

                set_table_item(self.table, view_row, COL_CODE, code, '#000000',
                               align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if price is not None:
                    set_table_item(self.table, view_row, COL_PRICE, f'{price:.2f}',
                                   '#000000',
                                   align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                else:
                    set_table_item(self.table, view_row, COL_PRICE, '未取得', BC.TEXT3,
                                   align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                set_table_item(self.table, view_row, COL_PCT, format_pct(pct),
                               pct_color(pct), bold=True,
                               align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

                # 振幅：(最高-最低)/昨收*100%，腾讯已直接给出
                amp = q.get('amplitude')
                if amp is not None and amp != '':
                    try:
                        set_table_item(self.table, view_row, COL_AMP, f'{float(amp):.2f}%',
                                       '#000000',
                                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                    except (TypeError, ValueError):
                        set_table_item(self.table, view_row, COL_AMP, '--', '#000000',
                                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                else:
                    set_table_item(self.table, view_row, COL_AMP, '--', '#000000',
                                   align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

                # 市值（总市值，亿）
                mv = q.get('total_mv')
                try:
                    mv = float(mv)
                except (TypeError, ValueError):
                    mv = 0.0
                if mv > 0:
                    set_table_item(self.table, view_row, COL_MV, f'{mv:.0f}亿', '#000000',
                                   align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                else:
                    set_table_item(self.table, view_row, COL_MV, '--', '#000000',
                                   align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

                # 题材（选股雷达同源）
                theme = (self._themes or {}).get(code, '--') or '--'
                _tit = set_table_item(self.table, view_row, COL_THEME, theme, BC.RED, bold=True)
                _tit.setToolTip(theme)   # 题材常超过 20 字，列再宽也放不下 → 悬停看全文

                # 控盘（新增列）：'98·候选' / '80·出货' / '97·洗盘' / '71' / '--'
                from services.control_profile import ctrl_cell, ctrl_tooltip
                _ci = q.get('ctrl')
                _ct, _cc = ctrl_cell(_ci)
                _cit = set_table_item(self.table, view_row, COL_CTRL, _ct, _cc,
                                      align=Qt.AlignmentFlag.AlignVCenter
                                      | Qt.AlignmentFlag.AlignCenter)
                _cit.setToolTip(ctrl_tooltip(_ci))
            self._refresh_header_labels()
        finally:
            self._loading = False

    def _selected_data_index(self):
        """当前选中行在 self._watchlist 中的数据索引（考虑列头排序后的视图映射）。
        未选中返回 -1。"""
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount():
            return -1
        item = self.table.item(row, COL_NAME)
        if item is None:
            return -1
        idx = item.data(Qt.ItemDataRole.UserRole)
        try:
            idx = int(idx)
        except Exception:
            return -1
        if 0 <= idx < len(self._watchlist):
            return idx
        return -1

    def _selected_code(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount():
            return ''
        it = self.table.item(row, COL_CODE)
        return it.text() if it else ''

    def _update_move_buttons_enabled(self):
        """根据当前选中行位置更新上移/下移按钮可用性"""
        if self._loading:
            return
        idx = self._selected_data_index()
        n = len(self._watchlist)
        if idx < 0 or n <= 1:
            self.up_btn.setEnabled(False)
            self.down_btn.setEnabled(False)
            return
        self.up_btn.setEnabled(idx > 0)
        self.down_btn.setEnabled(idx < n - 1)

    # ----------------------------------------------------------
    # 手动上下排序
    # ----------------------------------------------------------
    def _move_up(self):
        idx = self._selected_data_index()
        if idx <= 0 or idx >= len(self._watchlist):
            return
        self._watchlist[idx - 1], self._watchlist[idx] = \
            self._watchlist[idx], self._watchlist[idx - 1]
        self._save_watchlist()
        # 手动排序优先级最高：取消列头临时排序
        self._sort_state = None
        self._refresh_header_labels()
        # 用旧行情立即重渲染，再异步拉新行情
        self._populate_table(self._last_quotes)
        self.refresh()
        self._update_move_buttons_enabled()

    def _move_down(self):
        idx = self._selected_data_index()
        if idx < 0 or idx >= len(self._watchlist) - 1:
            return
        self._watchlist[idx + 1], self._watchlist[idx] = \
            self._watchlist[idx], self._watchlist[idx + 1]
        self._save_watchlist()
        self._sort_state = None
        self._refresh_header_labels()
        self._populate_table(self._last_quotes)
        self.refresh()
        self._update_move_buttons_enabled()

    # ----------------------------------------------------------
    # 添加/删除
    # ----------------------------------------------------------
    def _on_add(self):
        text = self.code_input.text().strip()
        if not text:
            return
        # 解析代码：可能是 "002838 道恩股份" 或 "002838" 或 "道恩股份"
        code = ''
        name = ''
        parts = text.split()
        if parts and parts[0].isdigit() and len(parts[0]) == 6:
            code = parts[0]  # 字符串保留前导零
            name = ' '.join(parts[1:]) if len(parts) > 1 else ''
            # 未手动输入名称时，从缓存查询；查不到也允许添加（后续行情会补全名称）
            if not name:
                name = self._code_to_name.get(code, '')
                if not name:
                    # 再尝试从 name->code 反向查
                    for n, c in self._stock_names.items():
                        if str(c) == code:
                            name = n
                            break
                if not name:
                    print(f'[自选] 缓存中未找到 {code} 的名称，先以代码作为名称添加',
                          flush=True)
                    name = code
        else:
            # 按名称搜索：所有比较前转字符串，避免float/in崩溃
            text_str = str(text)
            for n, c in self._stock_names.items():
                n_str = str(n).strip()
                c_str = str(c).strip()
                if not n_str or not c_str:
                    continue
                if text_str in n_str or n_str in text_str:
                    code = c_str
                    name = n_str
                    break

        if not code:
            self._flash_input_error('未找到该股票')
            return

        # 查名称（输入代码但未带名称时）
        if not name:
            name = self._code_to_name.get(code, code)

        # 去重
        if any(str(item.get('code', '')) == code for item in self._watchlist):
            self._flash_input_error('已在自选列表中')
            self.code_input.clear()
            return

        # 恢复正常样式
        self._reset_input_style()

        self._watchlist.append({'code': code, 'name': name})
        self._save_watchlist()
        self._update_title_count()
        self.code_input.clear()
        self.refresh()

    def _flash_input_error(self, msg):
        """输入框红色提示（2秒后自动恢复）"""
        self.code_input.setStyleSheet(f"""
            QLineEdit{{background:{BC.BG_HEADER};color:{BC.RED};
            border:1px solid {BC.RED};border-radius:5px;padding:0 8px;font-size:12px;}}
        """)
        original_ph = self.code_input.placeholderText()
        self.code_input.setPlaceholderText(msg)
        QTimer.singleShot(2000, lambda: self._reset_input_style(original_ph))

    def _reset_input_style(self, placeholder=None):
        """恢复输入框正常样式"""
        self.code_input.setStyleSheet(f"""
            QLineEdit{{background:{BC.BG_HEADER};color:{BC.TEXT};
            border:1px solid {BC.BORDER};border-radius:5px;padding:0 8px;font-size:12px;}}
            QLineEdit:focus{{border:1px solid {BC.BLUE};}}
        """)
        if placeholder:
            self.code_input.setPlaceholderText(placeholder)
        else:
            self.code_input.setPlaceholderText('输入代码/名称，如 002838 或 道恩')

    def _on_delete(self):
        idx = self._selected_data_index()
        if idx < 0 or idx >= len(self._watchlist):
            return
        del self._watchlist[idx]
        self._save_watchlist()
        self._update_title_count()
        # 删除后若有列头排序，保留排序状态但用缓存立即重渲染
        self._populate_table(self._last_quotes)
        self.refresh()
        self._update_move_buttons_enabled()

    # ----------------------------------------------------------
    # 行情刷新
    # ----------------------------------------------------------
    def refresh(self):
        if not self._watchlist:
            self._last_quotes = {}
            self.table.setRowCount(0)
            self.set_status('暂无自选')
            return
        self.set_status('加载中...')
        codes = [item['code'] for item in self._watchlist]
        self.run_async(
            self._fetch_quotes,
            self._on_quotes_loaded,
            self._on_quotes_failed,
            codes,
        )

    @staticmethod
    def _fetch_quotes(codes):
        from utils.http_market_data import get_realtime_quotes_http
        quotes = get_realtime_quotes_http(codes)
        # 题材：和选股雷达一致，从涨停原因数据库取
        from data.limit_up_reason_db import get_last_limit_up_reason
        themes = {}
        for c in codes:
            reason, _, _, industry = get_last_limit_up_reason(c)
            if reason:
                tags = []
                for t in reason.split('+'):
                    t = t.strip()
                    if t and not t.endswith('板') and len(t) > 2:
                        tags.append(t)
                themes[c] = '+'.join(tags) if tags else reason
            else:
                themes[c] = industry or '--'
        # 控盘度：只读本地 kline_cache，无网络兜底（在 run_async 线程里跑）
        from services.control_profile import get_ctrl_map
        _cm = get_ctrl_map([str(c) for c in codes])
        for _c, _q in (quotes or {}).items():
            if isinstance(_q, dict):
                _q['ctrl'] = _cm.get(str(_c))
        return quotes, themes

    def _on_quotes_loaded(self, result):
        quotes, themes = (result if isinstance(result, tuple) else (result, {}))
        self._last_quotes = quotes or {}
        self._themes = themes or {}
        self._populate_table(self._last_quotes)
        self.set_update_time()
        self._update_move_buttons_enabled()

    def _show_context_menu(self, pos):
        """右键菜单：删除自选/上移/下移"""
        from PyQt6.QtWidgets import QMenu
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self.table)
        del_action = menu.addAction('🗑️ 从自选删除')
        up_action = menu.addAction('⬆ 上移')
        down_action = menu.addAction('⬇ 下移')
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == del_action:
            self.table.selectRow(row)
            self._on_delete()
        elif action == up_action:
            self.table.selectRow(row)
            self._move_up()
        elif action == down_action:
            self.table.selectRow(row)
            self._move_down()

    def _on_cell_clicked(self, row, col):
        """仅点击股票名称单元格跳转个股分析，其他列不跳转"""
        if col != COL_NAME:
            return
        it = self.table.item(row, COL_CODE)
        code = it.text() if it else ''
        nit = self.table.item(row, COL_NAME)
        name = nit.text() if nit else code
        if code:
            self.stock_clicked.emit(code, name)

    def _on_quotes_failed(self, err):
        self.set_status('数据超时')
        # 仍显示名称和代码，价格标未取得；保留上次缓存
        self._populate_table(self._last_quotes)

    # ----------------------------------------------------------
    # 拖拽排序：drop 完成后按当前表格视图顺序重建 self._watchlist
    # ----------------------------------------------------------
    def eventFilter(self, obj, event):
        # 仅拦截 table 及其 viewport 的 Drop 事件
        if obj is self.table or obj is getattr(self.table, 'viewport', lambda: None)():
            if event.type() == QEvent.Type.Drop:
                # 仅在无列头排序时允许拖拽重排（否则数据顺序与视图不一致）
                if self._sort_state is not None:
                    event.ignore()
                    return True
                # 先让 QTableWidget 处理内部移动
                ret = super().eventFilter(obj, event)
                # 读取视图中每一行的代码，重建自定义顺序
                try:
                    new_order_codes = []
                    for r in range(self.table.rowCount()):
                        it = self.table.item(r, COL_CODE)
                        if it is not None and it.text():
                            new_order_codes.append(it.text())
                    if len(new_order_codes) == len(self._watchlist):
                        # 按视图顺序重建；保留原 item 的 name 字段
                        by_code = {str(x.get('code', '')): x for x in self._watchlist}
                        rebuilt = []
                        for c in new_order_codes:
                            if c in by_code:
                                rebuilt.append(by_code[c])
                        if len(rebuilt) == len(self._watchlist):
                            self._watchlist = rebuilt
                            self._save_watchlist()
                except Exception as e:
                    print(f'[自选] 拖拽排序保存失败: {e}', flush=True)
                # 重新渲染（用缓存行情）
                self._populate_table(self._last_quotes)
                self._update_move_buttons_enabled()
                return True
        return super().eventFilter(obj, event)
