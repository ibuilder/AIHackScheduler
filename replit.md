# Overview

BBSchedule Platform is a comprehensive enterprise-grade construction scheduling application built specifically for Balfour Beatty US. The platform provides professional project management capabilities with multiple scheduling methodologies including Gantt charts, linear scheduling, and pull planning. It integrates with Azure AI services, Microsoft Fabric, and Azure AI Foundry to provide intelligent optimization and analytics for construction projects.

The application serves multiple user roles from administrators to field supervisors, offering role-based access control and company-specific data isolation. It supports complex project workflows, task management, resource allocation, and real-time collaboration features essential for large-scale construction operations.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Web Framework and Structure
The application is built using Flask with a modular blueprint architecture. The codebase is organized into distinct blueprints for authentication, projects, scheduling, Azure integration, reports, and administration. This separation allows for maintainable code and clear responsibility boundaries. The application uses SQLAlchemy as the ORM with Flask-SQLAlchemy for database integration, providing a robust data layer with relationship management.

## Database Design
The system uses PostgreSQL as the primary database with a comprehensive schema supporting users, companies, projects, tasks, resources, and Azure integrations. The data model includes proper foreign key relationships and enum types for status management. Multi-tenancy is implemented through company-based data isolation, ensuring organizations can only access their own data.

## Authentication and Authorization
User authentication is handled through Flask-Login with role-based access control using enum-defined user roles (Admin, Project Manager, Scheduler, Field Supervisor, Viewer). The system includes session management with configurable timeouts and CSRF protection. User passwords are hashed using Werkzeug's security utilities.

## Frontend Architecture
The frontend uses Bootstrap 5 for responsive design with custom CSS theming matching Balfour Beatty branding. Interactive scheduling views are built with D3.js for Gantt charts and linear schedules, while Chart.js provides dashboard analytics. The interface supports drag-and-drop functionality for pull planning boards and real-time updates through JavaScript.

## Background Task Processing
Asynchronous task processing is implemented using Celery with Redis as the message broker. This handles file processing, Azure synchronization, report generation, and notifications without blocking the main application. Tasks are organized into different queues based on priority and resource requirements.

## Scheduling Methodologies
The platform supports three distinct scheduling approaches: traditional Gantt charts for timeline visualization, linear scheduling for location-based projects using time-distance diagrams, and pull planning boards for lean construction methodology. Each method includes specialized data models and visualization components.

## File Upload and Processing
The system supports importing project data from various formats including Microsoft Project (MSP), CSV, and Excel files. File processing is handled asynchronously with progress tracking and validation. Uploaded files are processed to create tasks, dependencies, and resource assignments automatically.

# External Dependencies

## Azure Cloud Services
The platform integrates extensively with Microsoft Azure services including Azure AI for project analysis and optimization, Microsoft Fabric for data warehousing and analytics, and Azure AI Foundry for predictive modeling. These services provide intelligent insights for schedule optimization, risk assessment, and project outcome prediction.

## Database and Caching
PostgreSQL serves as the primary database for persistent storage, while Redis functions as both the caching layer and message broker for Celery background tasks. The database configuration includes connection pooling and automatic reconnection handling for production reliability.

## Authentication Services
The system integrates with Azure Active Directory for enterprise authentication, supporting both direct login and OAuth flows. This allows integration with existing corporate identity management systems.

## Third-Party APIs
External API integrations include Azure Resource Manager for cloud resource management, Microsoft Graph API for calendar and user data, and various construction industry APIs for equipment and material data synchronization.

## Development and Deployment
The application uses Flask-Migrate for database schema management, Flask-WTF for form handling and CSRF protection, and includes comprehensive logging and monitoring capabilities. Static assets are served through CDN integration for Bootstrap, Font Awesome icons, Chart.js, and D3.js libraries.