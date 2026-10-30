# -*- coding: utf-8 -*-
"""FIX20：V4 LLM 输出截断（max_tokens 3000 不够 V4 长 schema）三修
①_max_tokens 按 purpose：zforce_radar→6000
②ZSYS 末尾加输出完整性铁律（禁截断+字段限字）
③解析层加 _repair_json 截断容错 + _extract_zscan_lists 提取复用"""
import io, sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\tools\cloud_daily_review.py'
src = io.open(P, encoding='utf-8').read()
orig = src

def rep(old, new, tag):
    global src
    assert old in src, 'NOT FOUND: ' + tag
    assert src.count(old) == 1, 'AMBIG: ' + tag + ' count=%d' % src.count(old)
    src = src.replace(old, new, 1)
    print('[OK]', tag)

# 1. max_tokens 按 purpose
rep("""            body = json.dumps({'model': m, 'messages': msgs,
                              'temperature': 0.5, 'max_tokens': 3000}).encode('utf-8')""",
    """            body = json.dumps({'model': m, 'messages': msgs,
                              'temperature': 0.5,
                              'max_tokens': (6000 if purpose == 'zforce_radar' else 3000)}).encode('utf-8')""",
    'max_tokens_by_purpose')

# 2. ZSYS 末尾追加输出完整性铁律
rep("""- 全池证据不足时 radar 输出空数组，但 meta 和 judged_all 要说明缺口，不许硬凑。\"\"\"""",
    """- 全池证据不足时 radar 输出空数组，但 meta 和 judged_all 要说明缺口，不许硬凑。
【七、输出完整性铁律（违反即整段作废）】
1. 输出必须是完整闭合的 JSON 对象，以 } 结尾，禁止截断。宁可大幅精简字段说明文字，也不允许 JSON 不完整。
2. 单条文本字段控制在 40 字以内（bottom_logic 可放宽到 60 字）；radar 最多 5 只、judged_all 全池，全篇总量务必控制在 2000 字以内。
3. 输出前自查：radar/judged_all/excluded 数组括号全部配平、以 } 完整闭合。截断即降级视为失败。
\"\"\"""",
    'zsys_completeness')

# 3. 解析层：_repair_json + _extract_zscan_lists（放在 _divergence_label 前）
rep("""def _divergence_label(hh, theme, sec_map, hot_board):""",
    """def _repair_json(s):
    \"\"\"截断 JSON 容错：剥掉尾部残缺 token → 按括号深度补全 → 解析。成功返回对象，失败返回 None。\"\"\"
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    def _try(cand):
        try:
            return json.loads(cand)
        except Exception:
            return None
    # 第一遍：原样补全
    r = _try(s)
    if r is not None:
        return r
    # 第二遍：剥到最后一个逗号（丢掉残缺 token）再补全
    for _attempt in range(2):
        cut = s.rfind(',')
        if cut <= 0:
            break
        s = s[:cut]
        r = _try(s)
        if r is not None:
            return r
        stack = []
        in_str, esc = False, False
        for ch in s:
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in '{[':
                stack.append('}' if ch == '{' else ']')
            elif ch in '}]' and stack:
                stack.pop()
        out = s
        for _ in range(len(stack) + 2):
            r = _try(out)
            if r is not None:
                return r
            if stack:
                out += stack.pop()
            else:
                break
    return None


def _extract_zscan_lists(_j):
    \"\"\"从 LLM JSON 对象提取 (radar, judged_all, excluded, meta)，兼容 V4 主结构与旧嵌套结构。\"\"\"
    radar = [x for x in (_j.get('radar') or _j.get('radar_data') or _j.get('stocks') or _j.get('analysis_items')
                         or _j.get('selected_stocks') or []) if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
    judged_all = [x for x in (_j.get('judged_all') or []) if isinstance(x, dict)] if isinstance(_j.get('judged_all'), list) else []
    excluded = [x for x in (_j.get('excluded') or []) if isinstance(x, dict)] if isinstance(_j.get('excluded'), list) else []
    meta = _j.get('meta') if isinstance(_j.get('meta'), dict) else {}
    _rr = _j.get('radar_report') if isinstance(_j.get('radar_report'), dict) else {}
    if not radar:
        radar = [x for x in (_rr.get('selected_stocks') or _rr.get('stocks') or [])
                 if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
    if not radar:
        for _v in _j.values():
            if isinstance(_v, list) and _v and isinstance(_v[0], dict) and ('code' in _v[0] or 'stock_code' in _v[0]):
                radar = [x for x in _v if isinstance(x, dict)]
                break
            if isinstance(_v, dict):
                for _v2 in _v.values():
                    if isinstance(_v2, list) and _v2 and isinstance(_v2[0], dict) and ('code' in _v2[0] or 'stock_code' in _v2[0]):
                        radar = [x for x in _v2 if isinstance(x, dict)]
                        break
                if radar:
                    break
    return radar, judged_all, excluded, meta


def _divergence_label(hh, theme, sec_map, hot_board):""",
    'repair_json')

# 4. 解析段改用 _extract_zscan_lists + 截断修复分支
rep("""                if _i >= 0 and _j2 > _i:
                    _st = _st[_i:_j2 + 1]
                _j = json.loads(_st)
                _rr = _j.get('radar_report') if isinstance(_j.get('radar_report'), dict) else {}
                raw = (_j.get('radar') or _j.get('radar_data') or _j.get('stocks') or _j.get('analysis_items')
                       or _j.get('selected_stocks') or _rr.get('selected_stocks') or _rr.get('stocks') or [])
                radar = [x for x in raw if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
                _judged_all = [x for x in (_j.get('judged_all') or []) if isinstance(x, dict)] if isinstance(_j.get('judged_all'), list) else []
                _excluded = [x for x in (_j.get('excluded') or []) if isinstance(x, dict)] if isinstance(_j.get('excluded'), list) else []
                _meta = _j.get('meta') if isinstance(_j.get('meta'), dict) else {}
                # 通用兜底：递归两层找含 code/stock_code 的数组（LLM 结构多变，兜底不降级）
                if not radar:
                    for _v in _j.values():
                        if isinstance(_v, list) and _v and isinstance(_v[0], dict) and ('code' in _v[0] or 'stock_code' in _v[0]):
                            radar = [x for x in _v if isinstance(x, dict)]
                            break
                        if isinstance(_v, dict):
                            for _v2 in _v.values():
                                if isinstance(_v2, list) and _v2 and isinstance(_v2[0], dict) and ('code' in _v2[0] or 'stock_code' in _v2[0]):
                                    radar = [x for x in _v2 if isinstance(x, dict)]
                                    break
                            if radar:
                                break
        except Exception as e:
            print('[zscan] radar JSON 解析失败:', str(e)[:80])""",
    """                if _i >= 0 and _j2 > _i:
                    _st = _st[_i:_j2 + 1]
                _j = json.loads(_st)
                radar, _judged_all, _excluded, _meta = _extract_zscan_lists(_j)
        except Exception as e:
            print('[zscan] radar JSON 解析失败:', str(e)[:80])
            # FIX20 容错：截断 JSON 修复（V4 长 schema 易被 max_tokens 截断）
            _jf = _repair_json(_t)
            if _jf is not None:
                print('[zscan] 截断JSON修复成功（保留已解析部分）')
                _j = _jf
                radar, _judged_all, _excluded, _meta = _extract_zscan_lists(_j)""",
    'parse_repair')

io.open(P, 'w', encoding='utf-8', newline='').write(src)
print('patched, delta=%d' % (len(src) - len(orig)))
