from flask import Blueprint, request, session, render_template, redirect, url_for
from datetime import datetime
from app.utils.decorators import require_auth
from app.container.analyzer import get_analyzer
from app.logger import logger

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    analyzer = get_analyzer()
    auth_enabled = analyzer.config.web_auth.enabled

    if not auth_enabled:
        return redirect(url_for('auth.index'))  # 注意 endpoint 加了蓝图名

    if request.method == 'POST':
        password = request.form.get('password', '')
        config_password = analyzer.config.web_auth.password

        if not config_password:
            return render_template(
                "main.html",
                error="系统未设置访问密码，请联系管理员配置",
                session_timeout=analyzer.config.web_auth.session_timeout // 60
            )

        if password == config_password:
            session['authenticated'] = True
            session['login_time'] = datetime.now().isoformat()
            logger.info("用户登录成功")
            return redirect(url_for('auth.index'))
        else:
            logger.warning("用户登录失败：密码错误")
            return render_template(
                "main.html",
                error="密码错误，请重试",
                session_timeout=analyzer.config.web_auth.session_timeout // 60
            )

    return render_template(
        "main.html",
        session_timeout=analyzer.config.web_auth.session_timeout // 60
    )

@auth_bp.route('/logout')
def logout():
    session.pop('authenticated', None)
    session.pop('login_time', None)
    logger.info("用户退出登录")
    return redirect(url_for('auth.login'))

@auth_bp.route('/')
@require_auth
def index():
    analyzer = get_analyzer()
    auth_enabled = analyzer.config.web_auth.enabled
    return render_template("main.html", auth_enabled=auth_enabled)
