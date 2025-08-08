from datetime import datetime
from flask import session, redirect, url_for

from functools import wraps
from app.container.analyzer import get_analyzer

def require_auth(f):
    """鉴权装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        analyzer = get_analyzer()
        auth_enabled = analyzer.config.web_auth.enabled
        
        if not auth_enabled:
            return f(*args, **kwargs)
        
        # 检查session中是否已认证
        if session.get('authenticated'):
            # 检查session是否过期
            login_time = session.get('login_time')
            if login_time:
                session_timeout = analyzer.config.web_auth.session_timeout
                if (datetime.now() - datetime.fromisoformat(login_time)).total_seconds() < session_timeout:
                    return f(*args, **kwargs)
                else:
                    session.pop('authenticated', None)
                    session.pop('login_time', None)
        
        return redirect(url_for('auth.login'))
    
    return decorated_function