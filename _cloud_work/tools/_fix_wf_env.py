# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\.github\workflows\daily-review2.yml'
s = io.open(P, encoding='utf-8').read()
old = """      - name: 判定时段并推送
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          MODELSCOPE_API_KEY: ${{ secrets.MODELSCOPE_API_KEY }}
          PUSHPLUS_TOKEN: ${{ secrets.PUSHPLUS_TOKEN }}"""
new = """      - name: 判定时段并推送
        env:
          MODELSCOPE_API_KEY: ${{ secrets.MODELSCOPE_API_KEY }}
          PUSHPLUS_TOKEN: ${{ secrets.PUSHPLUS_TOKEN }}"""
assert old in s, 'workflow anchor not found'
s = s.replace(old, new)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('workflow updated')
