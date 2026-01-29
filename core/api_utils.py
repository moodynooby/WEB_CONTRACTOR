"""
API Utilities for enhanced security, validation, and logging
"""

import time
import json
from datetime import datetime
from functools import wraps
from typing import Dict, Any, Optional, Tuple
from flask import request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from marshmallow import Schema, fields, ValidationError
from loguru import logger

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

class APIError(Exception):
    """Custom API error class"""
    def __init__(self, message: str, status_code: int = 400, payload: Optional[Dict] = None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload

class ValidationError(APIError):
    """Validation specific error"""
    def __init__(self, message: str, payload: Optional[Dict] = None):
        super().__init__(message, 422, payload)

# Request logging middleware
def log_request():
    """Log API requests with details"""
    start_time = time.time()
    
    # Store start time for response logging
    g.start_time = start_time
    
    # Log request details
    logger.info(
        f"API Request: {request.method} {request.path} | "
        f"IP: {request.remote_addr} | "
        f"User-Agent: {request.headers.get('User-Agent', 'Unknown')} | "
        f"Content-Type: {request.content_type}"
    )

def log_response(response):
    """Log API responses with timing"""
    if hasattr(g, 'start_time'):
        duration = time.time() - g.start_time
        logger.info(
            f"API Response: {response.status_code} | "
            f"Duration: {duration:.3f}s | "
            f"Size: {len(response.get_data())} bytes"
        )
    return response

# Error handlers
def handle_api_error(error: APIError) -> Tuple[Dict, int]:
    """Handle custom API errors"""
    response = {
        'error': True,
        'message': error.message,
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path
    }
    
    if error.payload:
        response.update(error.payload)
    
    logger.warning(f"API Error: {error.message} | Path: {request.path} | IP: {request.remote_addr}")
    return jsonify(response), error.status_code

def handle_validation_error(error: ValidationError) -> Tuple[Dict, int]:
    """Handle validation errors"""
    response = {
        'error': True,
        'message': 'Validation failed',
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path,
        'validation_errors': error.messages
    }
    
    logger.warning(f"Validation Error: {error.messages} | Path: {request.path} | IP: {request.remote_addr}")
    return jsonify(response), 422

def handle_general_error(error: Exception) -> Tuple[Dict, int]:
    """Handle unexpected errors"""
    response = {
        'error': True,
        'message': 'Internal server error',
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path
    }
    
    logger.error(f"Unexpected Error: {str(error)} | Path: {request.path} | IP: {request.remote_addr}")
    return jsonify(response), 500

# Validation schemas
class ProcessStartSchema(Schema):
    process = fields.Str(required=True, validate=lambda x: x in [
        'full_pipeline', 'stage0', 'stage_a', 'stage_b', 'stage_c', 
        'quality_control', 'email_sender'
    ])

class ProcessStopSchema(Schema):
    process = fields.Str(required=True)

class LeadsQuerySchema(Schema):
    page = fields.Int(load_default=1, validate=lambda x: x >= 1)
    per_page = fields.Int(load_default=20, validate=lambda x: 1 <= x <= 100)
    status = fields.Str(load_default='')
    bucket = fields.Str(load_default='')

class ReviewActionSchema(Schema):
    campaignId = fields.Int(required=True)
    action = fields.Str(required=True, validate=lambda x: x in ['send', 'ignore'])
    body = fields.Str(load_default=None)

# Decorators
def validate_json(schema_class):
    """Validate JSON request body against schema"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                raise ValidationError('Content-Type must be application/json')
            
            try:
                schema = schema_class()
                data = schema.load(request.json)
                request.validated_json = data
            except ValidationError as e:
                raise ValidationError('Invalid request data', {'errors': e.messages})
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_query(schema_class):
    """Validate query parameters against schema"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                schema = schema_class()
                data = schema.load(request.args.to_dict())
                request.validated_query = data
            except ValidationError as e:
                raise ValidationError('Invalid query parameters', {'errors': e.messages})
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limit(limit: str):
    """Apply rate limiting to endpoint"""
    def decorator(f):
        return limiter.limit(limit)(f)
    return decorator

# Success response helper
def success_response(data: Any = None, message: str = None, status_code: int = 200) -> Tuple[Dict, int]:
    """Create standardized success response"""
    response = {
        'success': True,
        'timestamp': datetime.utcnow().isoformat(),
        'path': request.path
    }
    
    if data is not None:
        response['data'] = data
    
    if message:
        response['message'] = message
    
    logger.info(f"Success Response: {message or 'OK'} | Path: {request.path} | IP: {request.remote_addr}")
    return jsonify(response), status_code

# Security headers middleware
def add_security_headers(response):
    """Add security headers to responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response
