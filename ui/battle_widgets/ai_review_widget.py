# -*- coding: utf-8 -*-
"""AI 复盘页：本地 Ollama 模型 + 市场看板数据快照 → 一段中文盘后复盘。"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QPlainTextEdit,
                             QPushButton)

from .base import BC, L, BattleModuleBase


class AiReviewWidget(BattleModuleBase):

    def __init__(self, parent=None):
        super().__init__('AI 复盘（本地模型）', parent)
        row = QHBoxLayout()
        row.addWidget(L('模型', BC.TEXT2, 11))
        self._model = QComboBox()
        from services.ai_review_service import list_models, DEFAULT_MODEL
        ms = list_models()
        self._model.addItems(ms or [DEFAULT_MODEL])
        if DEFAULT_MODEL in ms:
            self._model.setCurrentText(DEFAULT_MODEL)
        row.addWidget(self._model)
        self._btn = QPushButton('生成本日复盘')
        self._btn.clicked.connect(self._run)
        row.addWidget(self._btn)
        row.addStretch()
        self.content_layout.addLayout(row)

        self._out = QPlainTextEdit()
        self._out.setReadOnly(True)
        self._out.setStyleSheet('background:%s;color:%s;font-size:13px;line-height:1.6;'
                                'font-family:"Microsoft YaHei","PingFang SC";'
                                % (BC.BG_CARD, BC.TEXT))
        self._out.setPlaceholderText('点「生成本日复盘」，用本地 Ollama 模型基于今日真实盘面数据写一段复盘。\n'
                                     '首次调用会加载模型，约 20~60 秒。')
        self.content_layout.addWidget(self._out, 1)
        if not ms:
            self.set_status('⚠ 未连接到 Ollama（http://localhost:11434），请先启动 ollama serve')

    def _run(self):
        model = self._model.currentText()
        self._btn.setEnabled(False)
        self.set_status('本地模型 %s 生成中，约 20~60 秒…' % model)
        self.run_async(lambda: self._job(model),
                       self._done, lambda e: self._fail(e))

    def _job(self, model):
        from services.ai_review_service import generate_review
        return generate_review(model)

    def _done(self, res):
        self._btn.setEnabled(True)
        text, snap = res
        self._out.setPlainText(text)
        self.set_status('复盘已生成（%d 字）' % len(text))

    def _fail(self, err):
        self._btn.setEnabled(True)
        self.set_status('生成失败: %s' % err)
