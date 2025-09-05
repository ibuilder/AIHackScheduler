# BBSchedule Platform

## Enterprise Construction Scheduling & Project Management

BBSchedule is a comprehensive, enterprise-grade construction scheduling application built specifically for Balfour Beatty US and general contracting companies. The platform provides professional project management capabilities with multiple scheduling methodologies, financial tracking, equipment management, and AI-powered analytics.

## 🚀 Key Features

### Project Management
- **Multi-tenant Architecture**: Company-specific data isolation with role-based access control
- **Project Templates**: Standardized project setups for consistent scheduling
- **Task Management**: Hierarchical task structures with dependencies and constraints
- **Resource Allocation**: Comprehensive resource planning and assignment tracking

### Scheduling Methodologies
- **Gantt Charts**: Traditional timeline visualization with drag-and-drop functionality
- **Linear Scheduling**: Time-distance diagrams for location-based projects
- **Pull Planning**: Lean construction methodology with collaborative planning boards

### Financial Management
- **Cost Tracking**: Comprehensive transaction management with categorization
- **Invoice Management**: Professional invoice generation and payment tracking
- **Budget Control**: Project budget tracking with variance analysis
- **Payment Processing**: Stripe integration for secure payment handling
- **Financial Reporting**: Real-time financial dashboards and analytics

### Equipment Management
- **Asset Tracking**: Complete equipment lifecycle management
- **Maintenance Scheduling**: Preventive maintenance planning and tracking
- **Utilization Analytics**: Equipment usage optimization and reporting
- **Assignment Management**: Equipment allocation across projects

### Azure AI Integration
- **Predictive Analytics**: Schedule optimization using Azure AI services
- **Risk Assessment**: AI-powered project outcome prediction
- **Microsoft Fabric**: Data warehousing and advanced analytics
- **Azure AI Foundry**: Intelligent insights and recommendations

### Power BI Integration
- **Executive Dashboards**: Real-time business intelligence
- **Custom Reports**: Tailored reporting for construction metrics
- **Data Visualization**: Interactive charts and analytics
- **Workspace Integration**: Seamless Power BI workspace connectivity

## 🛠 Technology Stack

### Backend
- **Flask**: Python web framework with modular blueprint architecture
- **SQLAlchemy**: Object-relational mapping with PostgreSQL database
- **Celery**: Asynchronous task processing with Redis message broker
- **Flask-Login**: User authentication and session management
- **Azure SDK**: Cloud services integration

### Frontend
- **Bootstrap 5**: Responsive design framework
- **D3.js**: Interactive data visualizations and Gantt charts
- **Chart.js**: Dashboard analytics and reporting charts
- **JavaScript**: Enhanced user interface interactions

### Database & Storage
- **PostgreSQL**: Primary database with multi-tenant design
- **Redis**: Caching layer and Celery message broker
- **Azure Blob Storage**: File storage and document management

### External Services
- **Stripe**: Payment processing and subscription management
- **Azure AI Services**: Machine learning and predictive analytics
- **Microsoft Graph API**: Calendar and user data integration
- **Power BI**: Business intelligence and reporting

## 📋 Prerequisites

- Python 3.11+
- PostgreSQL 13+
- Redis 6+ (for caching and background tasks)
- Azure Account (optional - for AI services)
- Stripe Account (optional - for payment processing)

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd bbschedule-platform
```

### 2. Environment Setup
```bash
# Install dependencies (using uv - recommended)
uv pip sync

# Alternative: Install from deployment requirements
pip install -r deployment/requirements.txt
```

### 3. Database Configuration
```bash
# Set up PostgreSQL database
createdb bbschedule_dev

# Configure environment variables
cp .env.example .env
# Edit .env with your database credentials
```

### 4. Environment Variables
Create a `.env` file with the following variables:

```env
# Database
DATABASE_URL=postgresql://username:password@localhost/bbschedule_dev

# Flask Configuration
SESSION_SECRET=your-secret-key-here
FLASK_ENV=development

# Azure Services
AZURE_CLIENT_ID=your-azure-client-id
AZURE_CLIENT_SECRET=your-azure-client-secret
AZURE_TENANT_ID=your-azure-tenant-id

# Stripe Payment Processing
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Power BI Integration
POWERBI_CLIENT_ID=your-powerbi-client-id
POWERBI_CLIENT_SECRET=your-powerbi-client-secret
POWERBI_TENANT_ID=your-powerbi-tenant-id

# Redis
REDIS_URL=redis://localhost:6379/0
```

### 5. Database Initialization
```bash
# Initialize database tables
export FLASK_APP=main.py
flask shell -c "from app import db; db.create_all()"

# Note: Database migrations are planned for future releases
```

### 6. Start Services
```bash
# Start Redis server
redis-server

# Start Celery worker (in separate terminal)
celery -A tasks.celery_config.celery worker --loglevel=info

# Start Flask application (development)
export FLASK_APP=main.py
flask run --host=0.0.0.0 --port=5000

# Or using Gunicorn (production)
gunicorn --bind 0.0.0.0:5000 --reload main:app
```

## 🚦 Usage

### Accessing the Platform
1. Navigate to `http://localhost:5000`
2. Register a new company account or login with existing credentials
3. Complete the company setup process
4. Start creating projects and managing schedules

### User Roles
- **Admin**: Full system access and user management
- **Project Manager**: Project creation and team management
- **Scheduler**: Schedule creation and task management
- **Field Supervisor**: Field updates and progress tracking
- **Viewer**: Read-only access to projects and reports

### Creating Your First Project
1. Go to Projects → New Project
2. Fill in project details and budget information
3. Select a scheduling methodology (Gantt, Linear, or Pull Planning)
4. Add tasks, resources, and dependencies
5. Assign team members and equipment
6. Start tracking progress and costs

## 📊 Key Modules

### Project Management (`/projects`)
- Project creation and configuration
- Task hierarchy and dependency management
- Resource allocation and scheduling
- Progress tracking and reporting

### Financial Management (`/financial`)
- Transaction recording and categorization
- Invoice generation and management
- Budget tracking and variance analysis
- Financial reporting and analytics
- *Payment processing integration in progress*

### Equipment Management (`/equipment`)
- Equipment registration and tracking
- Maintenance scheduling and history
- Utilization analytics and reporting
- Project assignment management

### Scheduling (`/scheduling`)
- Multiple scheduling methodologies
- Interactive timeline management
- Resource conflict resolution
- Schedule optimization tools

### Reports (`/reports`)
- Executive dashboards
- Project status reports
- Financial analytics
- Equipment utilization reports

## 🔐 Security Features

- **Multi-tenant Data Isolation**: Company-scoped data access
- **Role-based Access Control**: Granular permission system
- **Session Management**: Secure user authentication
- **CSRF Protection**: Form security and validation
- **HTTPS Enforcement**: Secure data transmission
- **Audit Logging**: Comprehensive activity tracking

## 🏗 Architecture

### Application Structure
```
├── app.py                 # Main application factory
├── models.py             # Database models and relationships
├── routes.py             # Core application routes
├── extensions.py         # Flask extensions configuration
├── blueprints/           # Feature-specific blueprints
│   ├── projects.py
│   ├── scheduling.py
│   ├── financial_management.py
│   └── equipment_management.py
├── templates/            # Jinja2 templates
├── static/              # CSS, JavaScript, images
├── azure_ai/            # Azure AI integration
├── analytics/           # Advanced analytics
├── security/            # Security utilities
└── deployment/          # Docker and deployment configs
```

### Database Design
- **Multi-tenant**: Company-scoped data isolation
- **Relational**: Proper foreign key relationships
- **Indexed**: Optimized for query performance
- **Auditable**: Comprehensive change tracking

## 🚀 Deployment

### Docker Deployment
```bash
# Build Docker image
docker build -t bbschedule-platform .

# Run with Docker Compose
docker-compose up -d
```

### Azure Deployment
```bash
# Deploy to Azure App Service
az webapp up --name bbschedule-platform --resource-group rg-bbschedule
```

### Production Configuration
- Configure environment variables for production
- Set up SSL certificates and domain
- Configure database backups and monitoring
- Set up log aggregation and alerting

## 📈 Performance

### Optimization Features
- **Database Indexing**: Optimized query performance
- **Caching Layer**: Redis-based caching for frequent queries
- **Async Processing**: Background tasks with Celery
- **CDN Integration**: Static asset optimization
- **Query Optimization**: Efficient database queries

### Monitoring
- Application performance monitoring
- Database query analysis
- User activity tracking
- System resource monitoring

## 🤝 Contributing

### Development Guidelines
1. Follow PEP 8 style guidelines
2. Write comprehensive tests for new features
3. Update documentation for API changes
4. Use meaningful commit messages
5. Create pull requests for code review

### Testing
```bash
# Testing framework setup is planned for future releases
# Currently: Manual testing via application interface
# Unit tests will be added in upcoming versions
```

## 📄 License

This project is proprietary software developed for Balfour Beatty US. All rights reserved.

## 📞 Support

For technical support and questions:
- Internal Documentation: [Company Wiki]
- Technical Issues: [Internal Support Portal]
- Feature Requests: [Product Management Team]

## 🔄 Version History

### v2.0.0 (Current)
- Complete financial management system
- Advanced equipment tracking
- Azure AI predictive analytics integration
- Enhanced security features
- *Stripe payment integration in progress*

### v1.5.0
- Power BI integration
- Mobile optimization
- Real-time collaboration
- Executive dashboards

### v1.0.0
- Initial platform release
- Basic project management
- Gantt chart scheduling
- User authentication

---

**BBSchedule Platform** - Empowering construction project success through intelligent scheduling and comprehensive project management.