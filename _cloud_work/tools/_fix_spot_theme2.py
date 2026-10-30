# -*- coding: utf-8 -*-
"""行业兜底改为缓存方案：clist 成功时缓存全市场 code→行业(内存+文件)，缺源时读缓存，最后才试东财单股接口。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:60].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# ========== 1. 行业缓存（插在 _sec_clean 之前） ==========
rep("def _sec_clean(sec):",
    """_IND_CACHE = {}
_IND_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ind_cache.json')


def _ind_cache_load():
    try:
        with open(_IND_CACHE_PATH, encoding='utf-8') as f:
            _IND_CACHE.update(json.load(f))
    except Exception:
        pass


def _ind_cache_save():
    try:
        with open(_IND_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_IND_CACHE, f, ensure_ascii=False)
    except Exception:
        pass


def _stock_industry(code):
    \"\"\"单股行业兜底：缓存(内存→文件) → 东财单股接口。sec='其他'/空 时用，失败返回 ''。\"\"\"
    c = str(code)
    if _IND_CACHE.get(c):
        return _IND_CACHE[c]
    try:
        mk = '1' if c.startswith('6') else '0'
        url = ('https://push2.eastmoney.com/api/qt/stock/get?secid=' + mk + '.' + c + '&fields=f57,f58,f127')
        txt, ok = _getm(url, 'stock_ind')
        if ok and txt:
            dd = json.loads(txt).get('data') or {}
            ind = str(dd.get('f127') or '').strip()
            if ind:
                _cl = _sec_clean(ind)
                if _cl:
                    _IND_CACHE[c] = _cl
                    _ind_cache_save()
                    return _cl
    except Exception:
        pass
    return ''


def _today_top(d):
    \"\"\"今日主线名单：涨停板块 TOP6 + 题材热度 TOP，去重拼接。供单股卡判断主线归属。\"\"\"
    names = []
    for sec in (d.get('sectors') or {}).keys():
        if sec not in names:
            names.append(sec)
    for nm in (d.get('themes') or {}).keys():
        if nm not in names:
            names.append(nm)
    return '、'.join(names[:6]) or '（今日暂无明确主线）'


def _sec_clean(sec):""")

# ========== 2. clist 成功时写缓存 ==========
rep("""            except Exception:
                continue
        return rows
    except Exception as e:
        print('[auction] clist 解析异常:', e)
        return []""",
    """            except Exception:
                continue
        for x in rows:
            if x.get('industry') and x['industry'] != '其他':
                _IND_CACHE[str(x['code'])] = x['industry']
        if _IND_CACHE:
            _ind_cache_save()
        return rows
    except Exception as e:
        print('[auction] clist 解析异常:', e)
        return []""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
