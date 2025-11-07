import os
import threading
import multiprocessing
import signal
import sys
import time

from browser.instance import run_browser_instance
from utils.logger import setup_logging
from utils.paths import cookies_dir, logs_dir
from utils.cookie_manager import CookieManager
from utils.common import clean_env_value, ensure_dir

# 全局变量
browser_processes = []
app_running = False
flask_app = None


def load_instance_configurations(logger):
    """
    使用CookieManager解析环境变量和cookies目录，为每个cookie来源创建独立的浏览器实例配置。
    """
    # 1. 读取所有实例共享的URL
    shared_url = clean_env_value(os.getenv("CAMOUFOX_INSTANCE_URL"))
    if not shared_url:
        logger.error("错误: 缺少环境变量 CAMOUFOX_INSTANCE_URL。所有实例需要一个共享的目标URL。")
        return None, None

    # 2. 读取全局设置
    global_settings = {
        "headless": clean_env_value(os.getenv("CAMOUFOX_HEADLESS")) or "virtual",
        "url": shared_url  # 所有实例都使用这个URL
    }

    proxy_value = clean_env_value(os.getenv("CAMOUFOX_PROXY"))
    if proxy_value:
        global_settings["proxy"] = proxy_value

    # 3. 使用CookieManager检测所有cookie来源
    cookie_manager = CookieManager(logger)
    sources = cookie_manager.detect_all_sources()

    # 检查是否有任何cookie来源
    if not sources:
        logger.error("错误: 未找到任何cookie来源（既没有JSON文件，也没有环境变量cookie）。")
        return None, None

    # 4. 为每个cookie来源创建实例配置
    instances = []
    for source in sources:
        if source.type == "file":
            instances.append({
                "cookie_file": source.identifier,
                "cookie_source": source
            })
        elif source.type == "env_var":
            # 从环境变量名中提取索引，如 "USER_COOKIE_1" -> 1
            env_index = source.identifier.split("_")[-1]
            instances.append({
                "cookie_file": None,
                "env_cookie_index": int(env_index),
                "cookie_source": source
            })

    logger.info(f"将启动 {len(instances)} 个浏览器实例")

    return global_settings, instances

def start_browser_instances():
    """启动浏览器实例的核心逻辑"""
    global browser_processes, app_running

    log_dir = logs_dir()
    logger = setup_logging(str(log_dir / 'app.log'))
    logger.info("---------------------Camoufox 实例管理器开始启动---------------------")

    global_settings, instance_profiles = load_instance_configurations(logger)
    if not instance_profiles:
        logger.error("错误: 环境变量中未找到任何实例配置。")
        return

    for i, profile in enumerate(instance_profiles, 1):
        if not app_running:
            break

        final_config = global_settings.copy()
        final_config.update(profile)

        if 'url' not in final_config:
            logger.warning(f"警告: 跳过一个无效的配置项 (缺少 url): {profile}")
            continue

        cookie_source = final_config.get('cookie_source')

        if cookie_source:
            if cookie_source.type == "file":
                logger.info(
                    f"正在启动第 {i}/{len(instance_profiles)} 个浏览器实例 (file: {cookie_source.display_name})..."
                )
            elif cookie_source.type == "env_var":
                logger.info(
                    f"正在启动第 {i}/{len(instance_profiles)} 个浏览器实例 (env: {cookie_source.display_name})..."
                )
        else:
            logger.error(f"错误: 配置中缺少cookie_source对象")
            continue

        process = multiprocessing.Process(target=run_browser_instance, args=(final_config,))
        browser_processes.append(process)
        process.start()

        # 如果不是最后一个实例，等待30秒再启动下一个实例，避免并发启动导致的高CPU占用
        if i < len(instance_profiles):
            logger.info(f"等待 30 秒后启动下一个实例...")
            time.sleep(30)

    # 等待所有进程
    try:
        while app_running and browser_processes:
            for process in browser_processes[:]:
                if not process.is_alive():
                    browser_processes.remove(process)
                else:
                    process.join(timeout=1)
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("捕获到终止信号，正在关闭所有浏览器进程...")
        for process in browser_processes:
            process.terminate()
            process.join()

def run_standalone_mode():
    """独立模式"""
    global app_running
    app_running = True

    start_browser_instances()

def run_server_mode():
    """服务器模式"""
    global app_running, flask_app

    log_dir = logs_dir()
    server_logger = setup_logging(str(log_dir / 'app.log'), prefix="server")

    # 动态导入 Flask（只在需要时）
    try:
        from flask import Flask, jsonify
        flask_app = Flask(__name__)
    except ImportError:
        server_logger.error("错误: 服务器模式需要 Flask，请安装: pip install flask")
        return

    app_running = True

    # 在后台线程中启动浏览器实例
    browser_thread = threading.Thread(target=start_browser_instances, daemon=True)
    browser_thread.start()

    # 定义路由
    @flask_app.route('/health')
    def health_check():
        """健康检查端点"""
        running_count = sum(1 for p in browser_processes if p.is_alive())
        return jsonify({
            'status': 'healthy',
            'browser_instances': len(browser_processes),
            'running_instances': running_count,
            'message': f'Application is running with {running_count} active browser instances'
        })

    @flask_app.route('/')
    def index():
        """主页端点"""
        running_count = sum(1 for p in browser_processes if p.is_alive())
        return jsonify({
            'status': 'running',
            'browser_instances': len(browser_processes),
            'running_instances': running_count,
            'run_mode': 'server',
            'message': 'Camoufox Browser Automation is running in server mode'
        })

    # 禁用 Flask 的默认日志
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # 启动 Flask 服务器
    try:
        flask_app.run(host='0.0.0.0', port=7860, debug=False)
    except KeyboardInterrupt:
        server_logger.info("服务器正在关闭...")

def signal_handler(signum, frame):
    """统一的信号处理器"""
    global app_running
    logger = setup_logging(str(logs_dir() / 'app.log'), prefix="signal")
    logger.info(f"接收到信号 {signum}，正在关闭应用...")
    app_running = False

    # 关闭所有浏览器进程
    for process in browser_processes:
        if process.is_alive():
            process.terminate()
            try:
                process.join(timeout=5)
            except:
                process.kill()

    logger.info("所有进程已关闭")
    sys.exit(0)

def main():
    """主入口函数"""
    # 初始化必要的目录
    ensure_dir(logs_dir())
    ensure_dir(cookies_dir())

    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 检查运行模式环境变量
    hg_mode = os.getenv('HG', '').lower()

    if hg_mode == 'true':
        run_server_mode()
    else:
        run_standalone_mode()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
