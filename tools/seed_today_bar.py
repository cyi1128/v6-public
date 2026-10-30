# -*- coding: utf-8 -*-
"""盘中当日K线补齐器（CLI，可重复运行）。

底层是 services.kline_cache_service.seed_today_bar()，控盘选股页「补当日K线」开关
走的是同一个函数 —— 这里只是命令行入口。

为什么需要：日线接口逐个代码抓时 —— pytdx 服务器可连但无数据；新浪日线不含当天未收盘 bar；
腾讯日线有当天 bar 但批量高频请求会被 WAF 限流；东财连接被断。于是盘中 K 线缓存
常常只有「上一交易日」的 bar，控盘选股/日K建仓 的数据日因此停在昨天。
本脚本走腾讯**批量实时行情**（80 只/请求，全市场约 56 个请求、1 分钟内跑完），
用当日快照拼出今天这根未收盘 bar 写进缓存（volume 手→股、ON CONFLICT 更新，
收盘后正规增量会自然覆盖成正式数据）。

用法：
    python tools\\seed_today_bar.py                      # 全市场（仅在交易时段执行）
    python tools\\seed_today_bar.py --codes 600519,000811
    python tools\\seed_today_bar.py --force-anytime       # 非交易时段也照跑（复盘/核对用）
"""
import argparse
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--codes', default='', help='只补指定代码，逗号分隔；默认缓存内全部')
    ap.add_argument('--force-anytime', action='store_true',
                    help='忽略「仅交易时段」限制，非交易时段也执行')
    a = ap.parse_args()

    from services.kline_cache_service import seed_today_bar

    codes = [c.strip() for c in a.codes.split(',') if c.strip()] or None
    t0 = time.time()

    def _p(done, total, msg):
        if done >= total or done % 800 < 80:
            print('  [%4.0fs] %s' % (time.time() - t0, msg), flush=True)

    r = seed_today_bar(codes=codes, progress_cb=_p, only_in_session=not a.force_anytime)
    print('=' * 70)
    if r.get('ok'):
        print('今日 bar(%s) 覆盖代码数: %d → %d / %d 只（写入 %d 行，%.1fs）'
              % (r.get('today'), r.get('before', 0), r.get('after', 0),
                 r.get('requested', 0), r.get('written', 0), time.time() - t0))
    else:
        print('未写入：%s（请求 %d 只，拿到行情 %d 只，%.1fs）'
              % (r.get('reason') or '-', r.get('requested', 0), r.get('quotes', 0),
                 time.time() - t0))
    print('行情无效跳过 %d 只（停牌/无成交）' % r.get('skipped_quote', 0))
    print('=' * 70)


if __name__ == '__main__':
    main()
