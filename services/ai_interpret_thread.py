# -*- coding: utf-8 -*-
"""
AI解读后台线程（QThread）
不阻塞主界面，后台调用DeepSeek网页版解读
"""
from PyQt6.QtCore import QThread, pyqtSignal
from services.deepseek_web_interpreter import DeepSeekWebInterpreter


class AIInterpretThread(QThread):
    """AI解读后台线程"""
    finished_signal = pyqtSignal(str, str)  # news_id, result_text
    error_signal = pyqtSignal(str)  # error_message

    def __init__(self, news_id, news_title, news_content=""):
        super().__init__()
        self.news_id = news_id
        self.news_title = news_title
        self.news_content = news_content
        self.interpreter = DeepSeekWebInterpreter()

    def run(self):
        """后台执行解读"""
        try:
            result = self.interpreter.interpret_news(self.news_title, self.news_content)
            self.finished_signal.emit(self.news_id, result)
        except Exception as e:
            self.error_signal.emit(f"解读失败: {str(e)}")
