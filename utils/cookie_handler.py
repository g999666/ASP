def convert_cookie_editor_to_playwright(cookies_from_editor, logger=None):
    """
    将从 Cookie-Editor 插件导出的 Cookie 列表转换为 Playwright 兼容的格式。
    """
    playwright_cookies = []
    allowed_keys = {'name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite'}

    for cookie in cookies_from_editor:
        pw_cookie = {}
        for key in ['name', 'value', 'domain', 'path', 'httpOnly', 'secure']:
            if key in cookie:
                pw_cookie[key] = cookie[key]
        if cookie.get('session', False):
            pw_cookie['expires'] = -1
        elif 'expirationDate' in cookie:
            if cookie['expirationDate'] is not None:
                pw_cookie['expires'] = int(cookie['expirationDate'])
            else:
                pw_cookie['expires'] = -1

        if 'sameSite' in cookie:
            same_site_value = str(cookie['sameSite']).lower()
            if same_site_value == 'no_restriction':
                pw_cookie['sameSite'] = 'None'
            elif same_site_value in ['lax', 'strict']:
                pw_cookie['sameSite'] = same_site_value.capitalize()
            elif same_site_value == 'unspecified':
                pw_cookie['sameSite'] = 'Lax'

        if all(key in pw_cookie for key in ['name', 'value', 'domain', 'path']):
            playwright_cookies.append(pw_cookie)
        else:
            if logger:
                logger.warning(f"跳过一个格式不完整的 Cookie: {cookie}")

    return playwright_cookies


def convert_kv_to_playwright(kv_string, default_domain=".google.com", logger=None):
    """
    将键值对格式的 Cookie 字符串转换为 Playwright 兼容的格式。

    Args:
        kv_string (str): 包含 Cookie 的键值对字符串，格式为 "name1=value1; name2=value2; ..."
        default_domain (str): 默认域名，默认为".google.com"
        logger: 日志记录器

    Returns:
        list: Playwright 兼容的 Cookie 列表
    """
    import re

    playwright_cookies = []

    # 按分号分割 Cookie
    cookie_pairs = kv_string.split(';')

    for pair in cookie_pairs:
        pair = pair.strip()  # 去除首尾空白字符

        if not pair:  # 跳过空字符串
            continue

        # 跳过无效的 Cookie（不包含等号）
        if '=' not in pair:
            if logger:
                logger.warning(f"跳过无效的 Cookie 格式: '{pair}'")
            continue

        # 分割name和value
        name, value = pair.split('=', 1)  # 只分割第一个等号
        name = name.strip()
        value = value.strip()

        if not name:  # 跳过空名称
            if logger:
                logger.warning(f"跳过空名称的 Cookie: '{pair}'")
            continue

        # 构造 Playwright 格式的 Cookie
        pw_cookie = {
            'name': name,
            'value': value,
            'domain': default_domain,
            'path': '/',
            'expires': -1,  # 默认为会话 Cookie
            'httpOnly': False,  # KV 格式无法确定 httpOnly 状态，默认为 False
            'secure': True,     # 假设为安全 Cookie
            'sameSite': 'Lax'   # 默认 SameSite 策略
        }

        playwright_cookies.append(pw_cookie)

        if logger:
            logger.debug(f"成功转换 Cookie: {name} -> domain={default_domain}")

    return playwright_cookies