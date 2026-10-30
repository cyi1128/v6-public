# -*- coding: utf-8 -*-
"""备份脚本：把关键代码目录/文件快照到 backups/backup_<时间戳>/，保留最近10份。
用法：python scripts/backup.py
"""
import os, shutil, sys, datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_ROOT = os.path.join(PROJECT_ROOT, 'backups')
KEEP = 10

KEY_DIRS = ['ui', 'core', 'strategy', 'services', 'utils', 'config',
            'market', 'market_analysis', 'news_center', 'news_engine',
            'service', 'scripts', 'test', 'tests', 'tools', 'timed_report',
            'docs', 'assets']
# 这些目录只备份 .py 文件（目录里有几百 MB 的 duckdb / js / 大 json，不需要进快照）
PY_ONLY_DIRS = ['data']
KEY_FILES = ['main.py', 'AGENTS.md',
             '备份与回滚说明.md', 'README.md', 'requirements.txt',
             '盘后扫描_波段四模式.bat', '盘后扫描_波段四模式_自动.bat',
             '恢复到0924稳定版.bat', 'start.bat', '.gitignore',
    '灌创业板K线缓存.bat']

EXCLUDE_DIRS = {'__pycache__', 'backups', 'node_modules', 'browser_profile', '.git'}
EXCLUDE_SUFFIX = ('.pyc', '.pyo', '.log', '.duckdb', '.duckdb.wal')


def _ignore(dirpath, names):
    ig = set()
    for n in names:
        p = os.path.join(dirpath, n)
        if os.path.isdir(p):
            if n in EXCLUDE_DIRS or n.startswith('backup_'):
                ig.add(n)
        else:
            if n.endswith(EXCLUDE_SUFFIX):
                ig.add(n)
    return ig


def _py_only_ignore(dirpath, names):
    """只保留 .py，其余全部忽略（用于 data 这类混合目录）"""
    ig = set()
    for n in names:
        p = os.path.join(dirpath, n)
        if os.path.isdir(p):
            ig.add(n)
        elif not n.endswith('.py'):
            ig.add(n)
    return ig


def make_backup():
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    base = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    target = os.path.join(BACKUP_ROOT, 'backup_' + base)
    i = 2
    while os.path.exists(target):
        target = os.path.join(BACKUP_ROOT, 'backup_%s_%d' % (base, i))
        i += 1
    os.makedirs(target, exist_ok=True)
    copied = 0
    for d in KEY_DIRS:
        src = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(target, d), ignore=_ignore)
            copied += 1
    for d in PY_ONLY_DIRS:
        src = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(target, d), ignore=_py_only_ignore)
            copied += 1
    for f in KEY_FILES:
        src = os.path.join(PROJECT_ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(target, f))
            copied += 1
    backups = sorted([x for x in os.listdir(BACKUP_ROOT) if x.startswith('backup_')], reverse=True)
    for old in backups[KEEP:]:
        shutil.rmtree(os.path.join(BACKUP_ROOT, old), ignore_errors=True)
    print('备份完成 -> ' + target)


if __name__ == '__main__':
    make_backup()
