# -*- coding: utf-8 -*-
"""恢复到「0924 稳定版」——按备份目录名精确恢复，不依赖编号。

用法：
    python scripts\\restore_stable.py            # 交互确认
    python scripts\\restore_stable.py --yes      # 非交互
"""
import os, shutil, sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_ROOT = os.path.join(PROJECT_ROOT, 'backups')

STABLE_NAME = 'backup_20260924_170012'
STABLE_LABEL = '0924 稳定版'
STABLE_GIT = 'f2d3bcd'


def main():
    src = os.path.join(BACKUP_ROOT, STABLE_NAME)
    if not os.path.isdir(src):
        print('找不到稳定版快照: %s' % src)
        print('请先确认 backups\\ 下是否存在该目录。')
        return 1

    print('将把项目恢复到 [%s]' % STABLE_LABEL)
    print('  快照目录: %s' % src)
    print('  对应Git提交: %s' % STABLE_GIT)
    print('  覆盖前会自动先备份当前状态。')
    if '--yes' not in sys.argv:
        ans = input('确认恢复? [y/N]: ').strip().lower()
        if ans != 'y':
            print('已取消。')
            return 0

    # 覆盖前先备份当前状态
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backup import make_backup
    make_backup()

    restored = []
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(PROJECT_ROOT, item)
        if os.path.isdir(s):
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
        restored.append(item)

    print('恢复完成，共 %d 项：' % len(restored))
    print('  ' + ', '.join(sorted(restored)))
    print('请重启主程序。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
