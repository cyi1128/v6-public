# -*- coding: utf-8 -*-
"""回滚脚本：列出 backups/ 下的备份，选择编号后把内容覆盖回项目。
覆盖前自动备份当前状态。支持 --list / --pick N / --yes 供 UI 调用。
用法：
    python scripts/restore.py              # 交互式
    python scripts/restore.py --list       # 仅列出备份
    python scripts/restore.py --pick 1 --yes   # 恢复编号1（非交互）
"""
import os, shutil, sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_ROOT = os.path.join(PROJECT_ROOT, 'backups')


def list_backups():
    if not os.path.isdir(BACKUP_ROOT):
        return []
    return sorted([x for x in os.listdir(BACKUP_ROOT) if x.startswith('backup_')], reverse=True)


def backup_current():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from backup import make_backup
    make_backup()


def do_restore(pick_name):
    src = os.path.join(BACKUP_ROOT, pick_name)
    if not os.path.isdir(src):
        return False, '备份不存在: ' + pick_name
    backup_current()
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
    return True, '恢复完成，请重启程序'


def main():
    backups = list_backups()
    if not backups:
        print('未找到任何备份，请先运行 python scripts/backup.py')
        return
    if '--list' in sys.argv:
        for i, b in enumerate(backups, 1):
            print('%d. %s' % (i, b))
        return
    pick = None
    if '--pick' in sys.argv:
        idx = sys.argv.index('--pick') + 1
        if idx < len(sys.argv):
            try:
                n = int(sys.argv[idx])
                pick = backups[n - 1] if 1 <= n <= len(backups) else None
            except ValueError:
                pick = None
    else:
        print('可用的备份：')
        for i, b in enumerate(backups, 1):
            print('%d. %s' % (i, b))
        try:
            n = int(input('请输入要恢复的备份编号: ').strip())
            pick = backups[n - 1] if 1 <= n <= len(backups) else None
        except (ValueError, EOFError):
            pick = None
    if not pick:
        print('无效的备份编号，已取消。')
        return
    if '--yes' not in sys.argv:
        ans = input('将用 [%s] 覆盖当前代码（覆盖前会自动备份当前状态），确认? [y/N]: ' % pick).strip().lower()
        if ans != 'y':
            print('已取消。')
            return
    ok, msg = do_restore(pick)
    print(msg if ok else '恢复失败: ' + msg)


if __name__ == '__main__':
    main()
