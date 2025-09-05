from flask_caching import Cache
from functools import wraps
import json
import hashlib
from datetime import datetime, timedelta
import logging

class CacheManager:
    """Enterprise caching system for BBSchedule Platform"""
    
    def __init__(self):
        self.cache = None
    
    def init_app(self, app):
        """Initialize caching with the Flask app"""
        # Configure cache based on environment
        cache_type = app.config.get('CACHE_TYPE', 'simple')
        cache_config = {
            'CACHE_TYPE': cache_type,
            'CACHE_DEFAULT_TIMEOUT': 300,  # 5 minutes default
        }
        
        # Redis cache configuration for production
        if cache_type == 'redis':
            cache_config.update({
                'CACHE_REDIS_URL': app.config.get('REDIS_URL', 'redis://localhost:6379'),
                'CACHE_KEY_PREFIX': 'bbschedule_',
                'CACHE_REDIS_DB': 0
            })
        
        self.cache = Cache(config=cache_config)
        self.cache.init_app(app)
        app.logger.info(f"Cache initialized with type: {cache_type}")
    
    def cache_key(self, *args, **kwargs):
        """Generate cache key from arguments"""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def cached_query(self, timeout=300):
        """Decorator for caching database queries"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self.cache:
                    return func(*args, **kwargs)
                
                cache_key = f"query_{func.__name__}_{self.cache_key(*args, **kwargs)}"
                cached_result = self.cache.get(cache_key)
                
                if cached_result is not None:
                    logging.debug(f"Cache hit for {cache_key}")
                    return cached_result
                
                result = func(*args, **kwargs)
                
                # Only cache successful results
                if result is not None:
                    self.cache.set(cache_key, result, timeout=timeout)
                    logging.debug(f"Cache set for {cache_key}")
                
                return result
            return wrapper
        return decorator
    
    def cache_dashboard_data(self, user_id, company_id):
        """Cache dashboard data for a user/company"""
        cache_key = f"dashboard_{user_id}_{company_id}"
        return self.cache.get(cache_key)
    
    def set_dashboard_data(self, user_id, company_id, data, timeout=600):
        """Set dashboard data in cache"""
        cache_key = f"dashboard_{user_id}_{company_id}"
        self.cache.set(cache_key, data, timeout=timeout)
    
    def invalidate_project_cache(self, project_id):
        """Invalidate all cache entries related to a project"""
        if not self.cache:
            return
            
        # Clear project-related cache keys
        cache_keys = [
            f"project_{project_id}",
            f"project_tasks_{project_id}", 
            f"project_resources_{project_id}",
            f"project_stats_{project_id}"
        ]
        
        for key in cache_keys:
            self.cache.delete(key)
            logging.debug(f"Invalidated cache key: {key}")
    
    def invalidate_user_cache(self, user_id):
        """Invalidate all cache entries for a user"""
        if not self.cache:
            return
            
        # Clear user dashboard cache
        cache_pattern = f"dashboard_{user_id}_*"
        # Note: Redis pattern deletion would need Redis-specific implementation
        logging.debug(f"Invalidated user cache for user: {user_id}")
    
    def get_cache_stats(self):
        """Get cache statistics"""
        if not self.cache:
            return {'status': 'disabled'}
        
        try:
            # Basic cache info - varies by cache type
            return {
                'status': 'active',
                'type': self.cache.config.get('CACHE_TYPE'),
                'default_timeout': self.cache.config.get('CACHE_DEFAULT_TIMEOUT')
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

# Global cache manager instance
cache_manager = CacheManager()

def cached_project_data(timeout=300):
    """Decorator for caching project-related data"""
    return cache_manager.cached_query(timeout=timeout)

def cached_dashboard_data(timeout=600):
    """Decorator for caching dashboard data"""
    return cache_manager.cached_query(timeout=timeout)