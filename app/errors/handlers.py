from flask import Blueprint, jsonify
from app.logger import logger
from app.utils.format_utils import clean_data_for_json

errors_bp = Blueprint('errors', __name__)

@errors_bp.app_errorhandler(404)
def not_found(error):
    logger.error(error)
    return jsonify({
        'success': False,
        'error': clean_data_for_json(error)
    }), 404

@errors_bp.app_errorhandler(500)
def internal_error(error):
    logger.error(error)
    return jsonify({
        'success': False,
        'error': clean_data_for_json(error)
    }), 500
