from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request, current_app
import redis
from extensions import db
import logging

def get_user_id():
    """Get user ID for rate limiting, fallback to IP address"""
    try:
        from flask_login import current_user
        if hasattr(current_user, 'id') and current_user.is_authenticated:
            return str(current_user.id)
    except:
        pass
    return get_remote_address()

def setup_rate_limiting(app):
    """Configure rate limiting for the application"""
    
    # Use Redis if available, otherwise memory storage
    redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379')
    
    try:
        limiter = Limiter(
            app,
            key_func=get_user_id,
            storage_uri=redis_url,
            default_limits=["1000 per hour"],
            headers_enabled=True
        )
        
        # Define rate limits for different endpoints
        @limiter.limit("5 per minute")
        @app.route('/auth/login', methods=['POST'])
        def login_rate_limit():
            pass
            
        @limiter.limit("3 per minute") 
        @app.route('/auth/register', methods=['POST'])
        def register_rate_limit():
            pass
            
        @limiter.limit("100 per hour")
        @app.route('/api/<path:path>')
        def api_rate_limit():
            pass
            
        @limiter.limit("10 per minute")
        @app.route('/projects/create', methods=['POST'])
        def project_create_rate_limit():
            pass
        
        app.logger.info("Rate limiting configured successfully")
        return limiter
        
    except Exception as e:
        app.logger.error(f"Failed to setup rate limiting: {str(e)}")
        # Fallback to basic memory-based limiting
        limiter = Limiter(
            app,
            key_func=get_user_id,
            default_limits=["200 per hour"]
        )
        return limiter

class SecurityMiddleware:
    """Custom security middleware for additional protection"""
    
    def __init__(self, app):
        self.app = app
        self.setup_security_headers()
        self.setup_input_validation()
    
    def setup_security_headers(self):
        """Add security headers to all responses"""
        @self.app.after_request
        def add_security_headers(response):
            # Prevent clickjacking
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            
            # Prevent MIME type sniffing
            response.headers['X-Content-Type-Options'] = 'nosniff'
            
            # XSS Protection
            response.headers['X-XSS-Protection'] = '1; mode=block'
            
            # Referrer Policy
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            # Content Security Policy
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "connect-src 'self' https://api.powerbi.com;"
            )
            
            return response
    
    def setup_input_validation(self):
        """Setup input validation middleware"""
        @self.app.before_request
        def validate_input():
            # Skip validation for static files
            if request.path.startswith('/static/'):
                return
            
            # Validate request size
            max_content_length = self.app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)  # 16MB
            if request.content_length and request.content_length > max_content_length:
                logging.warning(f"Request too large: {request.content_length} bytes from {get_remote_address()}")
                return "Request too large", 413
            
            # Basic SQL injection detection in query parameters
            dangerous_patterns = ['union', 'select', 'insert', 'update', 'delete', 'drop', 'exec', 'script']
            for arg in request.args.values():
                arg_lower = arg.lower()
                for pattern in dangerous_patterns:
                    if pattern in arg_lower:
                        logging.warning(f"Suspicious query parameter from {get_remote_address()}: {arg}")
                        return "Invalid request", 400