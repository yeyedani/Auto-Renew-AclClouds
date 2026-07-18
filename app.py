# -*- coding: utf-8 -*-
"""
ACLClouds 自动登录与续期脚本 (智能升级版)
特别优化：完美兼容 Cookie-Editor 导出的完整 JSON 数组，彻底解决 3000+ 长度导致的无法写入问题。
"""

import os
import re
import time
import json
import requests
from seleniumbase import SB

# ==================== 全局配置 ====================
BASE_URL = "https://aclclouds.com"
LOGIN_URL = f"{BASE_URL}/login"
USER_URL = f"{BASE_URL}/user"

# 从环境变量获取参数
COOKIE_VALUE = os.getenv('COOKIE_VALUE', '').strip()
USERNAME = os.getenv('USERNAME', '').strip()
PASSWORD = os.getenv('PASSWORD', '').strip()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()


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
    current_url = sb.get_current_url()
    # 如果处于用户中心或排除登录页后存在退出按钮/用户特征，则认为已登录
    if "/user" in current_url or "/dashboard" in current_url:
        return True
    try:
        # 检查页面是否存在常见的登录后元素（如：退出登录、用户头像等）
        if sb.is_element_visible('a[href*="/logout"]') or sb.is_text_visible("退出"):
            return True
    except Exception:
        pass
    return False


def try_remember_cookie_login(sb):
    """
    智能解析并写入 Cookie 登录
    兼容：1. Cookie-Editor 插件导出的 JSON 数组 (解决 3306 字符超长崩溃问题)
          2. name=val; name=val 格式的字符串
          3. 单一 Value 纯文本
    """
    if not COOKIE_VALUE:
        print("⏭️ 未配置 COOKIE_VALUE 环境变量，跳过 Cookie 登录。")
        return False

    print(f"📋 开始尝试 Cookie 自动登录，读取到原始数据长度: {len(COOKIE_VALUE)}")
    
    # 【核心前提】必须先打开目标域名建立同源上下文，浏览器才允许写入对应的 Cookie
    sb.open(BASE_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(2)

    cookies_to_add = []

    # 1. 自动兼容：解析 JSON 数组格式（完美匹配 Cookie-Editor 导出数据）
    if COOKIE_VALUE.startswith('[') and COOKIE_VALUE.endswith(']'):
        try:
            raw_list = json.loads(COOKIE_VALUE)
            for c in raw_list:
                if not isinstance(c, dict) or 'name' not in c or 'value' not in c:
                    continue
                clean_c = {
                    'name': c['name'],
                    'value': c['value'],
                    'path': c.get('path', '/'),
                    'secure': c.get('secure', True),
                }
                # 如果不是 __Host- 开头且存在 domain，清洗 domain 格式
                if not clean_c['name'].startswith('__Host-') and 'domain' in c:
                    clean_c['domain'] = c['domain'].lstrip('.')
                if 'httpOnly' in c:
                    clean_c['httpOnly'] = c['httpOnly']
                # 自动将 Chrome 插件的 expirationDate 映射为 Selenium 认的 expiry
                if 'expirationDate' in c:
                    clean_c['expiry'] = int(c['expirationDate'])
                elif 'expiry' in c:
                    clean_c['expiry'] = int(c['expiry'])
                cookies_to_add.append(clean_c)
            print(f"📦 识别为 JSON 数组格式，成功提取 {len(cookies_to_add)} 个有效 Cookie")
        except Exception as e:
            print(f"⚠️ JSON 解析遇到未知格式，尝试进入常规分段解析: {e}")

    # 2. 自动兼容：分段键值对格式 (name1=val1; name2=val2)
    if not cookies_to_add:
        parts = [p.strip() for p in COOKIE_VALUE.split(';') if p.strip()]
        for part in parts:
            if '=' in part:
                name, val = part.split('=', 1)
                name = name.strip()
                val = val.strip().strip('"').strip("'")
                c = {
                    'name': name,
                    'value': val,
                    'path': '/',
                    'secure': True
                }
                if not name.startswith('__Host-'):
                    c['domain'] = '.aclclouds.com'
                cookies_to_add.append(c)
            elif len(parts) == 1:
                # 3. 自动兼容：旧版单纯 Value 格式
                print("📌 识别为单一字符串，将直接绑定至 remember_web 默认会话")
                cookies_to_add.append({
                    'name': 'remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d',
                    'value': part,
                    'domain': '.aclclouds.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': True
                })

    # 循环安全注入 Cookie
    success_count = 0
    for c in cookies_to_add:
        try:
            sb.add_cookie(c)
            success_count += 1
        except Exception as e:
            # 兼容性降级：如果带 domain 写入失败（如 __Host- 前缀冲突），移除 domain 后重试
            if 'domain' in c:
                c.pop('domain', None)
                try:
                    sb.add_cookie(c)
                    success_count += 1
                    continue
                except Exception as e2:
                    print(f"⚠️ 写入 Cookie [{c['name']}] 失败: {e2}")
            else:
                print(f"⚠️ 写入 Cookie [{c['name']}] 失败: {e}")

    print(f"💉 成功注入 {success_count}/{len(cookies_to_add)} 个 Cookie！正在刷新页面校验状态...")
    sb.open(USER_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(3)

    if is_logged_in(sb):
        print(f"✅ Cookie 登录成功！当前页面: {sb.get_title()}")
        return True

    print("❌ Cookie 登录失效或会话已过期，将尝试账号密码登录。")
    return False


def try_password_login(sb):
    """账号密码登录 fallback"""
    if not USERNAME or not PASSWORD:
        print("❌ 未配置 USERNAME / PASSWORD 环境变量，无法进行密码登录。")
        return False

    print("🔑 正在尝试使用账号和密码登录...")
    sb.open(LOGIN_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(2)

    try:
        # 填写账号与密码 (尝试匹配常见的输入框定位器)
        sb.type('input[name="email"], input[name="username"], input[type="text"]', USERNAME)
        sb.type('input[name="password"], input[type="password"]', PASSWORD)
        sb.sleep(1)

        # 如果遇到 Cloudflare Turnstile 人机验证，尝试自动点击
        try:
            if sb.is_element_visible('iframe[src*="turnstile"], iframe[src*="cloudflare"]'):
                print("🛡️ 检测到 Cloudflare Turnstile 验证码，尝试处理...")
                sb.switch_to_frame('iframe[src*="turnstile"], iframe[src*="cloudflare"]')
                sb.click('input[type="checkbox"], .ctp-checkbox-label, #challenge-stage', timeout=5)
                sb.switch_to_default_content()
                sb.sleep(3)
        except Exception as e:
            print(f"ℹ️ 验证码检测及跳过提示: {e}")
            sb.switch_to_default_content()

        # 点击登录按钮
        sb.click('button[type="submit"], input[type="submit"], .btn-primary', timeout=5)
        sb.sleep(5)

        if is_logged_in(sb):
            print("✅ 账号密码登录成功！")
            return True
        else:
            print("❌ 登录可能失败，当前页面仍非用户中心。")
            return False
    except Exception as e:
        print(f"❌ 账号密码登录过程发生异常: {e}")
        return False


def perform_renewal_task(sb):
    """执行面板续期/签到/延长操作"""
    print("🔄 开始执行业务续期检查...")
    sb.open(USER_URL)
    sb.wait_for_ready_state_complete()
    sb.sleep(3)

    # ==================== 自定义业务续期逻辑 ====================
    # 注意：此处自动尝试查找常见的“续期/延长/签到”按钮
    # 您也可以根据实际目标界面的元素 selector 在此处微调
    try:
        # 匹配文本包含 "延长", "续期", "签到", "Renew" 的按钮或链接
        renew_buttons = sb.find_elements('button:contains("延长"), a:contains("延长"), button:contains("续期"), a:contains("续期"), button:contains("签到"), button:contains("Renew")')
        
        if not renew_buttons:
            print("ℹ️ 页面未检测到可以直接点击的续期/签到按钮（可能尚未到续期时间或无需操作）。")
            return "登录成功，但当前没有检测到可执行的续期按钮。"

        for idx, btn in enumerate(renew_buttons):
            try:
                print(f"👆 尝试点击第 {idx+1} 个操作按钮...")
                btn.click()
                sb.sleep(2)
                # 处理可能弹出的二次确认框
                if sb.is_element_visible('.modal, .sweet-alert, .el-message-box'):
                    sb.click('.modal button.btn-primary, .el-message-box .el-button--primary', timeout=3)
                    sb.sleep(2)
            except Exception as click_err:
                print(f"⚠️ 点击处理异常: {click_err}")

        print("🎉 自动处理流程执行完毕！")
        return "成功完成自动登录，并已触发续期/签到流程检查。"
    except Exception as e:
        print(f"⚠️ 业务续期执行逻辑出现提示: {e}")
        return f"登录成功，在执行页面点击检查时提示: {str(e)}"


def main():
    print("=" * 50)
    print("🚀 启动 ACLClouds 自动化守护脚本")
    print("=" * 50)

    # 启用 SeleniumBase 的 uc (Undetected-Chromium) 模式以绕过检测
    # 如果是在本地桌面调试，可将 headless=True 改为 headless=False
    with SB(uc=True, headless=True, page_load_strategy="normal") as sb:
        try:
            login_success = False

            # 1. 优先尝试智能 Cookie 登录
            if COOKIE_VALUE:
                login_success = try_remember_cookie_login(sb)

            # 2. 如果 Cookie 登录失败，尝试使用账号密码 fallback
            if not login_success and USERNAME and PASSWORD:
                login_success = try_password_login(sb)

            # 3. 如果通过任意方式顺利登录，执行业务操作
            if login_success:
                result_msg = perform_renewal_task(sb)
                send_telegram_notify(f"✅ 执行结果: {result_msg}")
            else:
                err_msg = "❌ 自动化执行失败：通过 Cookie 和账号密码均未顺利登录，请检查凭证是否有效。"
                print(err_msg)
                send_telegram_notify(err_msg)
                
        except Exception as e:
            fatal_err = f"🚨 脚本发生全局致命异常: {str(e)}"
            print(fatal_err)
            send_telegram_notify(fatal_err)
            raise e
        finally:
            print("🛑 任务执行结束，自动退出浏览器。")
            print("=" * 50)


if __name__ == "__main__":
    main()
