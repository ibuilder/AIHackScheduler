from extensions import db
from sqlalchemy import Index, text
import logging

class DatabaseOptimizer:
    """Database optimization utilities for enterprise performance"""
    
    def __init__(self, app=None):
        self.app = app
    
    def init_app(self, app):
        """Initialize database optimizations"""
        self.app = app
        with app.app_context():
            self.create_indexes()
            self.optimize_queries()
    
    def create_indexes(self):
        """Create database indexes for better query performance"""
        try:
            # User table indexes
            self.create_index('users', ['company_id'])
            self.create_index('users', ['email'])
            self.create_index('users', ['username'])
            self.create_index('users', ['role'])
            
            # Project table indexes
            self.create_index('projects', ['company_id'])
            self.create_index('projects', ['created_by'])
            self.create_index('projects', ['status'])
            self.create_index('projects', ['start_date'])
            self.create_index('projects', ['end_date'])
            self.create_index('projects', ['project_number'])
            
            # Task table indexes
            self.create_index('tasks', ['project_id'])
            self.create_index('tasks', ['parent_task_id'])
            self.create_index('tasks', ['status'])
            self.create_index('tasks', ['start_date'])
            self.create_index('tasks', ['end_date'])
            self.create_index('tasks', ['priority'])
            
            # Composite indexes for common queries
            self.create_index('tasks', ['project_id', 'status'])
            self.create_index('tasks', ['project_id', 'start_date'])
            self.create_index('projects', ['company_id', 'status'])
            
            # Resource table indexes
            self.create_index('resources', ['project_id'])
            self.create_index('resources', ['type'])
            
            # Resource assignment indexes
            self.create_index('resource_assignments', ['task_id'])
            self.create_index('resource_assignments', ['resource_id'])
            
            # Task dependency indexes
            self.create_index('task_dependencies', ['task_id'])
            self.create_index('task_dependencies', ['predecessor_task_id'])
            
            # Audit log indexes
            self.create_index('audit_logs', ['user_id'])
            self.create_index('audit_logs', ['company_id'])
            self.create_index('audit_logs', ['resource_type', 'resource_id'])
            self.create_index('audit_logs', ['timestamp'])
            self.create_index('audit_logs', ['action'])
            
            # Azure integration indexes
            self.create_index('azure_integrations', ['project_id'])
            self.create_index('azure_integrations', ['service_type'])
            
            # Power BI integration indexes
            self.create_index('powerbi_integrations', ['company_id'])
            self.create_index('powerbi_integrations', ['workspace_id'])
            self.create_index('powerbi_integrations', ['sync_timestamp'])
            
            logging.info("Database indexes created successfully")
            
        except Exception as e:
            logging.error(f"Failed to create database indexes: {str(e)}")
    
    def create_index(self, table_name, columns, unique=False):
        """Create an index on specified columns"""
        try:
            index_name = f"idx_{table_name}_{'_'.join(columns)}"
            
            # Check if index already exists
            result = db.engine.execute(text(f"""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = :table_name AND indexname = :index_name
            """), table_name=table_name, index_name=index_name)
            
            if result.fetchone():
                logging.debug(f"Index {index_name} already exists")
                return
            
            # Create the index
            columns_str = ', '.join(columns)
            unique_str = "UNIQUE" if unique else ""
            
            sql = f"""
                CREATE {unique_str} INDEX CONCURRENTLY {index_name} 
                ON {table_name} ({columns_str})
            """
            
            db.engine.execute(text(sql))
            logging.info(f"Created index: {index_name}")
            
        except Exception as e:
            logging.warning(f"Could not create index {index_name}: {str(e)}")
    
    def optimize_queries(self):
        """Run database optimization queries"""
        try:
            # Update table statistics
            db.engine.execute(text("ANALYZE;"))
            
            # Vacuum analyze for better performance (PostgreSQL)
            try:
                db.engine.execute(text("VACUUM ANALYZE;"))
                logging.info("Database vacuum analyze completed")
            except Exception as e:
                logging.warning(f"Vacuum analyze failed: {str(e)}")
            
        except Exception as e:
            logging.error(f"Query optimization failed: {str(e)}")
    
    def get_slow_queries(self, limit=10):
        """Get slow query information (PostgreSQL specific)"""
        try:
            result = db.engine.execute(text(f"""
                SELECT query, mean_time, calls, total_time
                FROM pg_stat_statements 
                ORDER BY mean_time DESC 
                LIMIT {limit}
            """))
            return result.fetchall()
        except Exception as e:
            logging.error(f"Failed to get slow queries: {str(e)}")
            return []
    
    def get_table_sizes(self):
        """Get table size information"""
        try:
            result = db.engine.execute(text("""
                SELECT schemaname, tablename, 
                       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """))
            return result.fetchall()
        except Exception as e:
            logging.error(f"Failed to get table sizes: {str(e)}")
            return []

# Global database optimizer instance
db_optimizer = DatabaseOptimizer()