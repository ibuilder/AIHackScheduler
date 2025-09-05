/**
 * Dashboard JavaScript for BBSchedule Platform
 * Handles interactive charts, real-time updates, and dashboard functionality
 */

class BBScheduleDashboard {
    constructor() {
        this.charts = {};
        this.refreshInterval = 300000; // 5 minutes
        this.refreshTimer = null;
        
        this.init();
    }
    
    init() {
        this.initializeCharts();
        this.setupEventListeners();
        this.startAutoRefresh();
    }
    
    initializeCharts() {
        // Project Progress Chart
        if (document.getElementById('projectProgressChart')) {
            this.initProjectProgressChart();
        }
        
        // Task Status Distribution Chart
        if (document.getElementById('taskStatusChart')) {
            this.initTaskStatusChart();
        }
        
        // Resource Utilization Chart
        if (document.getElementById('resourceUtilizationChart')) {
            this.initResourceUtilizationChart();
        }
        
        // Schedule Performance Chart
        if (document.getElementById('schedulePerformanceChart')) {
            this.initSchedulePerformanceChart();
        }
        
        // Azure AI Insights Chart
        if (document.getElementById('azureInsightsChart')) {
            this.initAzureInsightsChart();
        }
    }
    
    initProjectProgressChart() {
        const ctx = document.getElementById('projectProgressChart').getContext('2d');
        
        this.charts.projectProgress = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: window.dashboardData?.project_progress?.map(p => p.name) || [],
                datasets: [{
                    label: 'Progress (%)',
                    data: window.dashboardData?.project_progress?.map(p => p.progress) || [],
                    backgroundColor: 'rgba(0, 166, 81, 0.8)',
                    borderColor: 'rgba(0, 166, 81, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `Progress: ${context.parsed.y}%`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    initTaskStatusChart() {
        const ctx = document.getElementById('taskStatusChart').getContext('2d');
        
        const statusData = window.dashboardData?.status_distribution || [];
        const colors = {
            'NOT_STARTED': '#6c757d',
            'IN_PROGRESS': '#f7931e',
            'COMPLETED': '#28a745',
            'ON_HOLD': '#ffc107',
            'CANCELLED': '#dc3545'
        };
        
        this.charts.taskStatus = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: statusData.map(s => s.status.replace('_', ' ')),
                datasets: [{
                    data: statusData.map(s => s.count),
                    backgroundColor: statusData.map(s => colors[s.status] || '#6c757d'),
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.parsed / total) * 100).toFixed(1);
                                return `${context.label}: ${context.parsed} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }
    
    initResourceUtilizationChart() {
        const ctx = document.getElementById('resourceUtilizationChart').getContext('2d');
        
        // Sample data - would be replaced with real data
        const resourceData = [
            { name: 'Labor', utilization: 85 },
            { name: 'Equipment', utilization: 72 },
            { name: 'Materials', utilization: 93 }
        ];
        
        this.charts.resourceUtilization = new Chart(ctx, {
            type: 'horizontalBar',
            data: {
                labels: resourceData.map(r => r.name),
                datasets: [{
                    label: 'Utilization (%)',
                    data: resourceData.map(r => r.utilization),
                    backgroundColor: resourceData.map(r => 
                        r.utilization > 90 ? '#dc3545' : 
                        r.utilization > 75 ? '#ffc107' : '#28a745'
                    ),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
    
    initSchedulePerformanceChart() {
        const ctx = document.getElementById('schedulePerformanceChart').getContext('2d');
        
        // Generate sample timeline data
        const last30Days = Array.from({length: 30}, (_, i) => {
            const date = new Date();
            date.setDate(date.getDate() - (29 - i));
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        });
        
        const plannedProgress = Array.from({length: 30}, (_, i) => (i + 1) * 2.5);
        const actualProgress = plannedProgress.map(p => p + (Math.random() - 0.5) * 10);
        
        this.charts.schedulePerformance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: last30Days,
                datasets: [{
                    label: 'Planned Progress',
                    data: plannedProgress,
                    borderColor: '#003f6b',
                    backgroundColor: 'rgba(0, 63, 107, 0.1)',
                    tension: 0.4
                }, {
                    label: 'Actual Progress',
                    data: actualProgress,
                    borderColor: '#00a651',
                    backgroundColor: 'rgba(0, 166, 81, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    }
                }
            }
        });
    }
    
    initAzureInsightsChart() {
        const ctx = document.getElementById('azureInsightsChart').getContext('2d');
        
        // Sample Azure AI insights data
        const insightsData = {
            labels: ['Schedule Risk', 'Budget Risk', 'Resource Risk', 'Quality Risk'],
            datasets: [{
                label: 'Risk Level',
                data: [65, 45, 80, 30],
                backgroundColor: [
                    'rgba(220, 53, 69, 0.8)',
                    'rgba(255, 193, 7, 0.8)',
                    'rgba(220, 53, 69, 0.8)',
                    'rgba(40, 167, 69, 0.8)'
                ],
                borderWidth: 1
            }]
        };
        
        this.charts.azureInsights = new Chart(ctx, {
            type: 'radar',
            data: insightsData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            stepSize: 20
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
    
    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.getElementById('refreshDashboard');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshDashboard();
            });
        }
        
        // Auto-refresh toggle
        const autoRefreshToggle = document.getElementById('autoRefreshToggle');
        if (autoRefreshToggle) {
            autoRefreshToggle.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.startAutoRefresh();
                } else {
                    this.stopAutoRefresh();
                }
            });
        }
        
        // Quick action buttons
        document.querySelectorAll('[data-action]').forEach(button => {
            button.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                this.handleQuickAction(action);
            });
        });
        
        // Dashboard stats click handlers
        document.querySelectorAll('.dashboard-stat').forEach(stat => {
            stat.addEventListener('click', (e) => {
                const statType = e.currentTarget.dataset.stat;
                this.handleStatClick(statType);
            });
        });
    }
    
    handleQuickAction(action) {
        switch (action) {
            case 'new-project':
                window.location.href = '/projects/create';
                break;
            case 'azure-sync':
                this.triggerAzureSync();
                break;
            case 'generate-report':
                this.generateReport();
                break;
            case 'optimize-schedule':
                this.openScheduleOptimizer();
                break;
            default:
                console.log('Unknown action:', action);
        }
    }
    
    handleStatClick(statType) {
        switch (statType) {
            case 'projects':
                window.location.href = '/projects';
                break;
            case 'tasks':
                this.showTasksModal();
                break;
            case 'overdue':
                this.showOverdueTasksModal();
                break;
            default:
                console.log('Unknown stat type:', statType);
        }
    }
    
    triggerAzureSync() {
        this.showLoading('Syncing with Azure services...');
        
        fetch('/azure/sync-all', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            }
        })
        .then(response => response.json())
        .then(data => {
            this.hideLoading();
            if (data.success) {
                this.showAlert('Azure sync completed successfully', 'success');
                this.refreshDashboard();
            } else {
                this.showAlert('Azure sync failed: ' + data.error, 'error');
            }
        })
        .catch(error => {
            this.hideLoading();
            console.error('Error:', error);
            this.showAlert('Azure sync failed', 'error');
        });
    }
    
    generateReport() {
        this.showLoading('Generating report...');
        
        fetch('/reports/generate-dashboard-report', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            }
        })
        .then(response => response.blob())
        .then(blob => {
            this.hideLoading();
            
            // Download the report
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `dashboard-report-${new Date().toISOString().split('T')[0]}.pdf`;
            link.click();
            window.URL.revokeObjectURL(url);
            
            this.showAlert('Report generated successfully', 'success');
        })
        .catch(error => {
            this.hideLoading();
            console.error('Error:', error);
            this.showAlert('Failed to generate report', 'error');
        });
    }
    
    openScheduleOptimizer() {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-magic"></i> Schedule Optimizer
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="optimizer-form">
                            <div class="mb-3">
                                <label class="form-label">Optimization Type</label>
                                <select class="form-control" name="type" required>
                                    <option value="time">Minimize Duration</option>
                                    <option value="cost">Minimize Cost</option>
                                    <option value="resource">Optimize Resources</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Project</label>
                                <select class="form-control" name="project_id" required>
                                    <option value="">Select a project...</option>
                                    <!-- Projects would be loaded here -->
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Constraints</label>
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" name="maintain_budget" value="1">
                                    <label class="form-check-label">Maintain budget constraints</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" name="maintain_quality" value="1">
                                    <label class="form-check-label">Maintain quality standards</label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" name="resource_limits" value="1">
                                    <label class="form-check-label">Respect resource limits</label>
                                </div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-primary" onclick="dashboard.runOptimization()">
                            <i class="fas fa-play"></i> Run Optimization
                        </button>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
        
        // Clean up when hidden
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
        
        // Store modal reference
        this.currentModal = { element: modal, instance: bootstrapModal };
    }
    
    runOptimization() {
        const form = document.getElementById('optimizer-form');
        const formData = new FormData(form);
        
        this.showLoading('Running AI-powered optimization...');
        this.currentModal.instance.hide();
        
        fetch('/scheduling/api/optimize', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            this.hideLoading();
            if (data.success) {
                this.showOptimizationResults(data.results);
            } else {
                this.showAlert('Optimization failed: ' + data.error, 'error');
            }
        })
        .catch(error => {
            this.hideLoading();
            console.error('Error:', error);
            this.showAlert('Optimization failed', 'error');
        });
    }
    
    showOptimizationResults(results) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-chart-line"></i> Optimization Results
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-body text-center">
                                        <h6>Potential Time Savings</h6>
                                        <h3 class="text-success">${results.potential_time_savings || 0} days</h3>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-body text-center">
                                        <h6>Potential Cost Savings</h6>
                                        <h3 class="text-success">$${(results.potential_cost_savings || 0).toLocaleString()}</h3>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="mt-3">
                            <h6>Recommended Actions:</h6>
                            <ul class="list-unstyled">
                                ${(results.optimizations || []).map(opt => 
                                    `<li><i class="fas fa-check text-success"></i> ${opt.description}</li>`
                                ).join('')}
                            </ul>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-primary">
                            Apply Recommendations
                        </button>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            Close
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
        
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }
    
    refreshDashboard() {
        this.showLoading('Refreshing dashboard...');
        
        fetch('/reports/dashboard-data', {
            headers: {
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            }
        })
        .then(response => response.json())
        .then(data => {
            this.hideLoading();
            this.updateDashboardData(data);
            this.showAlert('Dashboard refreshed', 'success');
        })
        .catch(error => {
            this.hideLoading();
            console.error('Error:', error);
            this.showAlert('Failed to refresh dashboard', 'error');
        });
    }
    
    updateDashboardData(data) {
        // Update statistics
        this.updateStatistics(data);
        
        // Update charts
        this.updateCharts(data);
        
        // Update recent activities
        this.updateRecentActivities(data);
    }
    
    updateStatistics(data) {
        const stats = {
            'total-projects': data.total_projects,
            'active-projects': data.active_projects,
            'total-tasks': data.total_tasks,
            'completed-tasks': data.completed_tasks,
            'overdue-tasks': data.overdue_tasks
        };
        
        Object.entries(stats).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value || 0;
            }
        });
    }
    
    updateCharts(data) {
        // Update project progress chart
        if (this.charts.projectProgress && data.project_progress) {
            this.charts.projectProgress.data.labels = data.project_progress.map(p => p.name);
            this.charts.projectProgress.data.datasets[0].data = data.project_progress.map(p => p.progress);
            this.charts.projectProgress.update();
        }
        
        // Update task status chart
        if (this.charts.taskStatus && data.status_distribution) {
            this.charts.taskStatus.data.labels = data.status_distribution.map(s => s.status.replace('_', ' '));
            this.charts.taskStatus.data.datasets[0].data = data.status_distribution.map(s => s.count);
            this.charts.taskStatus.update();
        }
    }
    
    updateRecentActivities(data) {
        const activitiesContainer = document.getElementById('recent-activities');
        if (activitiesContainer && data.recent_tasks) {
            activitiesContainer.innerHTML = data.recent_tasks.map(task => `
                <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
                    <div>
                        <div class="fw-bold">${task.name}</div>
                        <small class="text-muted">${task.project_name}</small>
                    </div>
                    <span class="badge badge-status badge-${task.status.replace('_', '-')}">${task.status}</span>
                </div>
            `).join('');
        }
    }
    
    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }
        
        this.refreshTimer = setInterval(() => {
            this.refreshDashboard();
        }, this.refreshInterval);
    }
    
    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }
    
    showLoading(message = 'Loading...') {
        // Remove existing loading overlay
        const existing = document.getElementById('loading-overlay');
        if (existing) {
            existing.remove();
        }
        
        const overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
        overlay.style.zIndex = '9999';
        overlay.innerHTML = `
            <div class="card">
                <div class="card-body text-center">
                    <div class="loading-spinner mb-3"></div>
                    <div>${message}</div>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
    }
    
    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
    
    showAlert(message, type = 'info') {
        const alertClass = type === 'error' ? 'alert-danger' : 
                          type === 'success' ? 'alert-success' : 
                          type === 'warning' ? 'alert-warning' : 'alert-info';
        
        const alert = document.createElement('div');
        alert.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
        alert.style.top = '20px';
        alert.style.right = '20px';
        alert.style.zIndex = '9998';
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 5000);
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.dashboard = new BBScheduleDashboard();
});
