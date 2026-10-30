# -*- coding: utf-8 -*-
"""改 workflow 调度：hourly 挪整点 + news/news2h 三档 case/cron。一次性。"""
import io

P = r'D:\QuantMonitorV6\.github\workflows\daily-review2.yml'
s = io.open(P, encoding='utf-8').read()
n0 = s.count("options: ['pre', 'auction', 'hourly', 'noon', 'eod', 'watch', 'warn', 'confirm', 'ext', 'news', 'evening']")
s = s.replace(
    "options: ['pre', 'auction', 'hourly', 'noon', 'eod', 'watch', 'warn', 'confirm', 'ext', 'news', 'evening']",
    "options: ['pre', 'auction', 'hourly', 'noon', 'eod', 'watch', 'warn', 'confirm', 'ext', 'news', 'evening', 'news2h']")
n1 = s.count("30 1,2,5,6 * * 1-5")
s = s.replace("cron: '30 1,2,5,6 * * 1-5'",
              "cron: '0 2,3,5,6 * * 1-5'")
n2 = s.count("0 4,8")
s = s.replace("    - cron: '0,10,20,30,40,50 1-6 * * 1-5'",
              "    - cron: '0,10,20,30,40,50 1-6 * * 1-5'\n"
              "    - cron: '0 4,8 * * 1-5'        # 12:00/16:00 北京 两小时市场消息汇总\n"
              "    - cron: '1 6 * * 1-5'          # 14:01 北京 两小时市场消息汇总（14:00整点让给hourly，错1分钟防撞车）\n"
              "    - cron: '35 7 * * 1-5'         # 15:35 北京 旧事件简报·尾盘档（15:10档复用watch的07:10点）")
n3 = s.count("13:3[6-9]|14:3[6-9]) T=ext")
s = s.replace("            01:30|02:30|05:30|06:30) T=hourly ;;  # 09:30/10:30/13:30/14:30（date +%H 带前导零，必须写 01/02/05/06）",
              "            02:00|03:00|05:00|06:00) T=hourly ;;  # 10:00/11:00/13:00/14:00 北京 整点（date +%H 带前导零）\n"
              "            03:4[0-4])      T=news ;;       # 11:40-11:44 北京 旧事件简报·午间档（吃watch 03:40点）\n"
              "            04:00|08:00)    T=news2h ;;     # 12:00/16:00 北京 两小时市场消息汇总\n"
              "            06:0[1-4])      T=news2h ;;     # 14:01-14:04 北京 两小时市场消息汇总（14:00整点让给hourly）\n"
              "            07:1[0-4])      T=news ;;       # 15:10-15:14 北京 旧事件简报·尾盘档（吃watch 07:10点；放07:*之前）\n"
              "            07:3[5-9])      T=news ;;       # 15:35-15:39 北京 旧事件简报·尾盘档（放07:*之前）")
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('replace counts: options=%d hourly=%d add=%d ext=%d' % (n0, n1, n2, n3))
