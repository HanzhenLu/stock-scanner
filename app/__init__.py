from flask import Flask
from flask_cors import CORS
import secrets

def create_app():
    app = Flask(__name__)
    CORS(app)  # 允许跨域请求

    # 高并发优化配置
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
    app.config['JSON_SORT_KEYS'] = False

    # 生成随机的SECRET_KEY
    app.secret_key = secrets.token_hex(32)

    # 注册蓝图
    from app.routes.analyze_routers import analyzer_bp
    app.register_blueprint(analyzer_bp, url_prefix=f"/{analyzer_bp.name}")
    from app.routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp)
    from app.routes.sse_routes import sse_bp
    app.register_blueprint(sse_bp, url_prefix=f"/{sse_bp.name}")
    from app.routes.system_routes import status_bp
    app.register_blueprint(status_bp, url_prefix=f"/{status_bp.name}")
    from app.errors.handlers import errors_bp
    app.register_blueprint(errors_bp)

    print("\n=== Registered Routes ===")
    for rule in app.url_map.iter_rules():
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        print(f"{rule.rule:30s} -> {methods} -> {rule.endpoint}")
    
    return app
