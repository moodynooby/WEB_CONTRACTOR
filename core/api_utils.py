"""
Minimal API Utilities for internal tools
"""

from datetime import datetime
from typing import Dict, Any, Tuple
from flask import jsonify


class APIError(Exception):
    """Custom API error"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


def handle_api_error(error: APIError) -> Tuple[Dict, int]:
    """Handle API errors"""
    return jsonify(
        {
            "error": True,
            "message": error.message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    ), error.status_code


def handle_general_error(error: Exception) -> Tuple[Dict, int]:
    """Handle unexpected errors"""
    return jsonify(
        {
            "error": True,
            "message": "Internal server error",
            "timestamp": datetime.utcnow().isoformat(),
        }
    ), 500


def success_response(data: Any = None, message: str = None) -> Tuple[Dict, int]:
    """Create success response"""
    response = {"success": True, "timestamp": datetime.utcnow().isoformat()}
    if data is not None:
        response["data"] = data
    if message:
        response["message"] = message
    return jsonify(response), 200
