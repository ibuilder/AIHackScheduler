// Project Management JavaScript Functions
document.addEventListener('DOMContentLoaded', function() {
    // Initialize project management features
    initializeProjectForm();
    initializeQuickTaskAdd();
    initializeDashboardRefresh();
});

function initializeProjectForm() {
    const form = document.getElementById('projectForm');
    if (!form) return;
    
    // Set minimum dates
    const today = new Date().toISOString().split('T')[0];
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    if (startDateInput) {
        startDateInput.min = today;
        startDateInput.addEventListener('change', function() {
            if (endDateInput) {
                endDateInput.min = this.value;
            }
        });
    }
    
    // Form validation
    form.addEventListener('submit', function(e) {
        const name = document.getElementById('name')?.value;
        const startDate = startDateInput?.value;
        const endDate = endDateInput?.value;
        
        if (!name || !startDate || !endDate) {
            e.preventDefault();
            showAlert('Please fill in all required fields', 'error');
            return;
        }
        
        if (new Date(endDate) <= new Date(startDate)) {
            e.preventDefault();
            showAlert('End date must be after start date', 'error');
            return;
        }
        
        // Show loading state
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Creating...';
        }
    });
}

function initializeQuickTaskAdd() {
    // Quick task addition via modal or inline form
    const quickTaskForms = document.querySelectorAll('.quick-task-form');
    
    quickTaskForms.forEach(form => {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const projectId = this.dataset.projectId;
            const taskName = this.querySelector('input[name="task_name"]')?.value;
            const duration = this.querySelector('input[name="duration"]')?.value || 1;
            
            if (!taskName) {
                showAlert('Task name is required', 'error');
                return;
            }
            
            try {
                const response = await fetch('/api/projects/quick-task', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify({
                        project_id: projectId,
                        name: taskName,
                        duration: duration
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showAlert('Task added successfully!', 'success');
                    this.reset();
                    // Refresh task list if visible
                    refreshProjectTasks(projectId);
                } else {
                    showAlert(data.error || 'Failed to add task', 'error');
                }
                
            } catch (error) {
                console.error('Quick task add error:', error);
                showAlert('Network error. Please try again.', 'error');
            }
        });
    });
}

function initializeDashboardRefresh() {
    const refreshBtn = document.getElementById('refreshDashboard');
    const autoRefreshToggle = document.getElementById('autoRefreshToggle');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            refreshDashboardData();
        });
    }
    
    if (autoRefreshToggle) {
        autoRefreshToggle.addEventListener('change', function() {
            if (this.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
        
        // Start auto-refresh if enabled
        if (autoRefreshToggle.checked) {
            startAutoRefresh();
        }
    }
}

async function refreshDashboardData() {
    try {
        const response = await fetch('/api/projects/dashboard-stats');
        const stats = await response.json();
        
        if (stats.error) {
            console.error('Dashboard stats error:', stats.error);
            return;
        }
        
        // Update statistics
        updateStatElement('total-projects', stats.total_projects);
        updateStatElement('active-projects', stats.active_projects);
        updateStatElement('total-tasks', stats.total_tasks);
        updateStatElement('completed-tasks', stats.completed_tasks);
        
        // Update last refresh time
        const now = new Date().toLocaleTimeString();
        const refreshStatus = document.querySelector('.refresh-status');
        if (refreshStatus) {
            refreshStatus.textContent = `Last updated: ${now}`;
        }
        
    } catch (error) {
        console.error('Dashboard refresh error:', error);
    }
}

function updateStatElement(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = value;
        // Add animation
        element.classList.add('stat-updated');
        setTimeout(() => element.classList.remove('stat-updated'), 1000);
    }
}

async function refreshProjectTasks(projectId) {
    try {
        const response = await fetch(`/api/projects/project/${projectId}/tasks`);
        const data = await response.json();
        
        if (data.tasks) {
            // Update task list in the UI
            updateTaskList(data.tasks);
        }
        
    } catch (error) {
        console.error('Task refresh error:', error);
    }
}

function updateTaskList(tasks) {
    const taskList = document.querySelector('.task-list');
    if (!taskList) return;
    
    // Simple task list update - can be enhanced based on UI needs
    const taskItems = tasks.map(task => `
        <div class="task-item" data-task-id="${task.id}">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${task.name}</strong>
                    <small class="text-muted d-block">${task.duration} days</small>
                </div>
                <span class="badge bg-${getStatusBadgeClass(task.status)}">${task.status}</span>
            </div>
        </div>
    `).join('');
    
    taskList.innerHTML = taskItems;
}

function getStatusBadgeClass(status) {
    const statusClasses = {
        'NOT_STARTED': 'secondary',
        'IN_PROGRESS': 'primary',
        'COMPLETED': 'success',
        'ON_HOLD': 'warning',
        'CANCELLED': 'danger'
    };
    return statusClasses[status] || 'secondary';
}

function showAlert(message, type = 'info') {
    // Create alert element
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to alerts container or create one
    let alertContainer = document.querySelector('.alerts-container');
    if (!alertContainer) {
        alertContainer = document.createElement('div');
        alertContainer.className = 'alerts-container position-fixed top-0 end-0 p-3';
        alertContainer.style.zIndex = '1055';
        document.body.appendChild(alertContainer);
    }
    
    alertContainer.appendChild(alert);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        alert.remove();
    }, 5000);
}

function getCSRFToken() {
    const token = document.querySelector('meta[name=csrf-token]');
    return token ? token.getAttribute('content') : '';
}

// Auto-refresh functionality
let autoRefreshInterval;

function startAutoRefresh() {
    autoRefreshInterval = setInterval(refreshDashboardData, 30000); // 30 seconds
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
}