#!/bin/bash
# ============================================================
# 密钥配置模板（魔搭服务器版）
# 用法：
#   1) 把本文件里的两个密钥替换为你的真实值
#   2) 执行: chmod 600 env.sh
#   3) scheduler.sh 会自动 source 本文件
# 密钥来源：
#   - PUSHPLUS_TOKEN      ：PushPlus 官网 https://www.pushplus.plus/ 登录后「一对一推送」中的 token
#   - MODELSCOPE_API_KEY  ：魔搭 https://modelscope.cn 登录后「个人中心 → 访问令牌」（形如 ms-xxxxxxxx）
# 警告：本文件含密钥，禁止提交到 git / 禁止外传；服务器上仅本人可读（chmod 600）。
# ============================================================
export PUSHPLUS_TOKEN="在这里填PushPlus的token"
export MODELSCOPE_API_KEY="在这里填魔搭的api_key"
# 可选：指定模型（默认即可，无需改动）
# export MODELSCOPE_MODEL="qwen-plus"
