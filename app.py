# -*- coding: utf-8 -*-
"""
ACLClouds 自动化守护脚本 (完整版)
功能：支持 Cookie/密码登录，自动续期，Telegram 通知
配置：已同步所有 GitHub Secrets 环境变量
"""

import os
import time
import json
import requests
from seleniumbase import SB

# ==================== 全局配置 ====================
BASE_URL = "https://aclclouds.com"
LOGIN_URL = "https://aclclouds.com/auth/login"
PROJECTS_URL = "https://aclclouds.com/dashboard/projects"

# 获取环境变量 (确保与 GitHub Secrets 名称一致)
COOKIE_VALUE = os.getenv('COOKIE_VALUE', '').strip()
EMAIL = os.getenv('EMAIL', '').strip()
PASSWORD = os.getenv('PASSWORD', '').strip()
NODE_LINK = os.getenv('NODE_LINK', '').strip()
TELEGRAM_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID', '').strip()


def send_telegram_notify(message):
    """发送 Telegram 消息通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("🔕 未配置 Telegram 通知参数，跳过发送通知。")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🤖 [ACLClouds 自动化通知]\n\n{message}",
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("📲 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败，状态码: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Telegram 通知发送异常: {e}")


def is_logged_in(sb):
    """判断当前是否处于已登录状态"""
    # 通过查找特定的登出链接或用户中心特征判断登录状态
    try:
        if sb.is_element_visible('a[href*="/logout"]') or sb.is_text_visible("退出") or sb.is_element_visible('.nav-item'):
            return True
    except:
        pass
    return False


def try_remember_cookie_login(sb):
    """智能解析并写入 Cookie 登录"""
    if not COOKIE_VALUE:
        print("⏭️ 未配置 COOKIE_VALUE，跳过 Cookie 登录。")
        return False

    print(f"📋 开始尝试 Cookie 自动登录...")
    sb.open(BASE_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(2)

    cookies_to_add = []
    # 尝试解析 JSON 格式
    if COOKIE_VALUE.startswith('[') and COOKIE_VALUE.endswith(']'):
        try:
            raw_list = json.loads(COOKIE_VALUE)
            for c in raw_list:
                clean_c = {'name': c['name'], 'value': c['value'], 'path': c.get('path', '/'), 'secure': c.get('secure', True)}
                if not clean_c['name'].startswith('__Host-') and 'domain' in c:
                    clean_c['domain'] = c['domain'].lstrip('.')
                if 'expirationDate' in c: clean_c['expiry'] = int(c['expirationDate'])
                cookies_to_add.append(clean_c)
        except: pass

    for c in cookies_to_add:
        try: sb.add_cookie(c)
        except: pass

    # 登录后跳转至项目页进行验证
    sb.open(PROJECTS_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(3)

    if is_logged_in(sb):
        print("✅ Cookie 登录成功！")
        return True
    return False


def try_password_login(sb):
    """账号密码登录 fallback"""
    if not EMAIL or not PASSWORD:
        print("❌ 未配置 EMAIL / PASSWORD，无法进行密码登录。")
        return False

    print("🔑 正在尝试使用账号和密码登录...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(2)

    try:
        # 宽泛选择器以兼容可能的页面布局变动
        sb.type('input[name="email"], input[name="username"], input[type="email"], input[type="text"]', EMAIL)
        sb.type('input[name="password"], input[type="password"]', PASSWORD)
        sb.click('button[type="submit"], input[type="submit"]')
        sb.sleep(5)
        
        # 登录后跳转至项目页
        sb.open(PROJECTS_URL)
        sb.wait_for_ready_state_complete()
        
        if is_logged_in(sb):
            print("✅ 账号密码登录成功！")
            return True
        return False
    except Exception as e:
        print(f"❌ 登录异常: {e}")
        return False


def perform_renewal_task(sb):
    """执行面板续期/签到/延长操作"""
    print("🔄 开始执行业务续期检查...")
    sb.open(PROJECTS_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(3)

    try:
        # 如果需要跳转到 NODE_LINK，可在此处添加访问逻辑
        if NODE_LINK:
            print(f"🔗 检测到节点链接，准备访问: {NODE_LINK}")
        
        # 查找页面上的“续期”相关按钮
        renew_buttons = sb.find_elements('button:contains("Renew"), button:contains("延长"), button:contains("续期"), a:contains("Renew")')
        
        if not renew_buttons:
            print("ℹ️ 当前未发现可点击的续期按钮。")
            return "登录成功，但未发现可点击的续期/延长按钮（可能未到期）。"

        for btn in renew_buttons:
            btn.click()
            sb.sleep(2)

        return "续期操作流程已执行。"
    except Exception as e:
        return f"执行业务逻辑时出错: {str(e)}"


def main():
    print("🚀 启动 ACLClouds 自动化守护脚本")
    # 默认 headless=True，如需本地调试可见窗口，可改为 False
    with SB(uc=True, headless=True) as sb:
        try:
            login_success = False
            
            # 1. 优先尝试 Cookie
            if COOKIE_VALUE:
                login_success = try_remember_cookie_login(sb)
            
            # 2. 备用密码登录
            if not login_success and EMAIL and PASSWORD:
                login_success = try_password_login(sb)

            # 3. 执行业务
            if login_success:
                result_msg = perform_renewal_task(sb)
                send_telegram_notify(f"✅ 执行结果: {result_msg}")
            else:
                send_telegram_notify("❌ 自动化执行失败：登录未成功。")
        finally:
            print("🛑 任务结束。")

if __name__ == "__main__":
    main()
