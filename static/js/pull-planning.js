/**
 * Pull Planning Implementation for BBSchedule Platform
 * Interactive weekly planning board with drag-and-drop functionality
 */

class PullPlanningBoard {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            weeksToShow: 6,
            allowDragDrop: true,
            autoSave: true,
            ...options
        };
        
        this.weeks = new Map();
        this.tasks = [];
        this.draggedTask = null;
        
        this.init();
    }
    
    init() {
        if (!this.container) {
            console.error('Pull planning container not found');
            return;
        }
        
        this.container.className = 'pull-planning-board';
        this.createWeekColumns();
        this.setupEventListeners();
    }
    
    createWeekColumns() {
        this.container.innerHTML = '';
        
        // Create header
        const header = document.createElement('div');
        header.className = 'pull-planning-header mb-3';
        header.innerHTML = `
            <div class="row align-items-center">
                <div class="col">
                    <h4><i class="fas fa-tasks"></i> Pull Planning Board</h4>
                </div>
                <div class="col-auto">
                    <button class="btn btn-primary btn-sm" onclick="pullPlanning.addTask()">
                        <i class="fas fa-plus"></i> Add Task
                    </button>
                    <button class="btn btn-outline-primary btn-sm" onclick="pullPlanning.exportBoard()">
                        <i class="fas fa-download"></i> Export
                    </button>
                </div>
            </div>
        `;
        this.container.appendChild(header);
        
        // Create weeks container
        const weeksContainer = document.createElement('div');
        weeksContainer.className = 'pull-planning-weeks row';
        
        for (let i = 1; i <= this.options.weeksToShow; i++) {
            const weekColumn = this.createWeekColumn(i);
            weeksContainer.appendChild(weekColumn);
        }
        
        this.container.appendChild(weeksContainer);
    }
    
    createWeekColumn(weekNumber) {
        const col = document.createElement('div');
        col.className = 'col-md-2 mb-3';
        
        const weekCard = document.createElement('div');
        weekCard.className = 'pull-planning-week';
        weekCard.dataset.week = weekNumber;
        
        // Calculate week dates
        const startDate = new Date();
        startDate.setDate(startDate.getDate() + (weekNumber - 1) * 7);
        const endDate = new Date(startDate);
        endDate.setDate(endDate.getDate() + 6);
        
        weekCard.innerHTML = `
            <div class="week-header">
                <h5>Week ${weekNumber}</h5>
                <small class="text-muted">
                    ${startDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - 
                    ${endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </small>
            </div>
            <div class="week-tasks" data-week="${weekNumber}">
                <!-- Tasks will be added here -->
            </div>
            <div class="week-footer">
                <small class="text-muted">Drop tasks here</small>
            </div>
        `;
        
        col.appendChild(weekCard);
        
        if (this.options.allowDragDrop) {
            this.setupDropZone(weekCard.querySelector('.week-tasks'));
        }
        
        return col;
    }
    
    setupDropZone(element) {
        element.addEventListener('dragover', (e) => {
            e.preventDefault();
            element.classList.add('drag-over');
        });
        
        element.addEventListener('dragleave', (e) => {
            if (!element.contains(e.relatedTarget)) {
                element.classList.remove('drag-over');
            }
        });
        
        element.addEventListener('drop', (e) => {
            e.preventDefault();
            element.classList.remove('drag-over');
            
            if (this.draggedTask) {
                const targetWeek = parseInt(element.dataset.week);
                this.moveTaskToWeek(this.draggedTask, targetWeek);
            }
        });
    }
    
    setupEventListeners() {
        // Global drag events
        document.addEventListener('dragstart', (e) => {
            if (e.target.classList.contains('pull-planning-task')) {
                this.draggedTask = {
                    id: e.target.dataset.taskId,
                    element: e.target
                };
                e.target.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            }
        });
        
        document.addEventListener('dragend', (e) => {
            if (e.target.classList.contains('pull-planning-task')) {
                e.target.classList.remove('dragging');
                this.draggedTask = null;
                
                // Remove drag-over class from all drop zones
                document.querySelectorAll('.week-tasks').forEach(zone => {
                    zone.classList.remove('drag-over');
                });
            }
        });
    }
    
    setData(pullPlanWeeks) {
        this.weeks = new Map();
        this.tasks = [];
        
        // Clear existing tasks
        document.querySelectorAll('.week-tasks').forEach(container => {
            container.innerHTML = '';
        });
        
        // Populate weeks with tasks
        Object.entries(pullPlanWeeks).forEach(([weekNumber, tasks]) => {
            const week = parseInt(weekNumber);
            this.weeks.set(week, tasks);
            
            tasks.forEach(task => {
                this.tasks.push({ ...task, week });
                this.addTaskToWeek(task, week);
            });
        });
    }
    
    addTaskToWeek(task, weekNumber) {
        const weekContainer = document.querySelector(`.week-tasks[data-week="${weekNumber}"]`);
        if (!weekContainer) return;
        
        const taskElement = this.createTaskElement(task);
        weekContainer.appendChild(taskElement);
    }
    
    createTaskElement(task) {
        const taskDiv = document.createElement('div');
        taskDiv.className = 'pull-planning-task';
        taskDiv.draggable = this.options.allowDragDrop;
        taskDiv.dataset.taskId = task.id;
        
        // Set status class
        taskDiv.classList.add(`status-${task.status.replace('_', '-')}`);
        
        taskDiv.innerHTML = `
            <div class="task-content">
                <div class="task-name">${task.name}</div>
                <div class="task-details">
                    <small class="text-muted">
                        ${task.duration} days
                        ${task.progress > 0 ? `• ${task.progress}%` : ''}
                    </small>
                </div>
                <div class="task-constraints">
                    ${task.constraints && task.constraints.length > 0 ? 
                        task.constraints.map(c => `<span class="badge badge-warning badge-sm">${c}</span>`).join(' ') : 
                        ''
                    }
                </div>
            </div>
            <div class="task-actions">
                <button class="btn btn-sm btn-outline-primary" onclick="pullPlanning.editTask(${task.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="pullPlanning.removeTask(${task.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        // Add click handler for task details
        taskDiv.addEventListener('click', (e) => {
            if (!e.target.closest('.task-actions')) {
                this.showTaskDetails(task);
            }
        });
        
        return taskDiv;
    }
    
    moveTaskToWeek(draggedTask, targetWeek) {
        const taskId = parseInt(draggedTask.id);
        const task = this.tasks.find(t => t.id === taskId);
        
        if (!task) return;
        
        // Remove from current week
        const currentWeekTasks = this.weeks.get(task.week) || [];
        const updatedCurrentWeek = currentWeekTasks.filter(t => t.id !== taskId);
        this.weeks.set(task.week, updatedCurrentWeek);
        
        // Add to target week
        task.week = targetWeek;
        task.pull_plan_week = targetWeek;
        const targetWeekTasks = this.weeks.get(targetWeek) || [];
        targetWeekTasks.push(task);
        this.weeks.set(targetWeek, targetWeekTasks);
        
        // Remove task element from DOM
        draggedTask.element.remove();
        
        // Add task to new week
        this.addTaskToWeek(task, targetWeek);
        
        // Update task on server
        if (this.options.autoSave) {
            this.updateTaskOnServer(task);
        }
        
        // Show success message
        this.showMessage(`Task "${task.name}" moved to Week ${targetWeek}`, 'success');
    }
    
    updateTaskOnServer(task) {
        fetch(`/scheduling/api/tasks/${task.id}/update`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            },
            body: JSON.stringify({
                pull_plan_week: task.pull_plan_week
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error updating task:', data.error);
                this.showMessage(`Error updating task: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            this.showMessage('Failed to update task on server', 'error');
        });
    }
    
    showTaskDetails(task) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Task Details: ${task.name}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <p><strong>Duration:</strong> ${task.duration} days</p>
                                <p><strong>Progress:</strong> ${task.progress}%</p>
                                <p><strong>Status:</strong> 
                                    <span class="badge badge-status badge-${task.status.replace('_', '-')}">${task.status}</span>
                                </p>
                            </div>
                            <div class="col-md-6">
                                <p><strong>Start Date:</strong> ${new Date(task.start_date).toLocaleDateString()}</p>
                                <p><strong>End Date:</strong> ${new Date(task.end_date).toLocaleDateString()}</p>
                                <p><strong>Week:</strong> ${task.week}</p>
                            </div>
                        </div>
                        ${task.constraints && task.constraints.length > 0 ? `
                            <div class="mt-3">
                                <strong>Constraints:</strong><br>
                                ${task.constraints.map(c => `<span class="badge badge-warning me-1">${c}</span>`).join('')}
                            </div>
                        ` : ''}
                        <div class="progress mt-3">
                            <div class="progress-bar" style="width: ${task.progress}%"></div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-primary" onclick="pullPlanning.editTask(${task.id})">
                            Edit Task
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
        
        // Clean up modal when hidden
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }
    
    addTask() {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Add New Task</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="add-task-form">
                            <div class="mb-3">
                                <label class="form-label">Task Name</label>
                                <input type="text" class="form-control" name="name" required>
                            </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Duration (days)</label>
                                        <input type="number" class="form-control" name="duration" min="1" value="1" required>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Week</label>
                                        <select class="form-control" name="week" required>
                                            ${Array.from({length: this.options.weeksToShow}, (_, i) => 
                                                `<option value="${i + 1}">Week ${i + 1}</option>`
                                            ).join('')}
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Constraints (optional)</label>
                                <input type="text" class="form-control" name="constraints" 
                                       placeholder="Enter constraints separated by commas">
                                <small class="form-text text-muted">e.g., Weather dependent, Material delivery</small>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-primary" onclick="pullPlanning.saveNewTask()">
                            Add Task
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
        
        // Store modal reference for saving
        this.currentModal = { element: modal, instance: bootstrapModal };
    }
    
    saveNewTask() {
        const form = document.getElementById('add-task-form');
        const formData = new FormData(form);
        
        const taskData = {
            name: formData.get('name'),
            duration: parseInt(formData.get('duration')),
            pull_plan_week: parseInt(formData.get('week')),
            constraints: formData.get('constraints') ? 
                         formData.get('constraints').split(',').map(c => c.trim()).filter(c => c) : []
        };
        
        // Send to server
        fetch(`/projects/${window.projectId}/tasks/create`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            },
            body: JSON.stringify(taskData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                this.showMessage(`Error creating task: ${data.error}`, 'error');
            } else {
                // Add task to local data
                const newTask = {
                    id: data.id,
                    name: data.name,
                    duration: taskData.duration,
                    week: taskData.pull_plan_week,
                    pull_plan_week: taskData.pull_plan_week,
                    constraints: taskData.constraints,
                    status: 'not_started',
                    progress: 0,
                    start_date: data.start_date,
                    end_date: data.end_date
                };
                
                this.tasks.push(newTask);
                
                // Add to week
                const weekTasks = this.weeks.get(newTask.week) || [];
                weekTasks.push(newTask);
                this.weeks.set(newTask.week, weekTasks);
                
                // Add to DOM
                this.addTaskToWeek(newTask, newTask.week);
                
                // Close modal
                this.currentModal.instance.hide();
                
                this.showMessage('Task created successfully', 'success');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            this.showMessage('Failed to create task', 'error');
        });
    }
    
    editTask(taskId) {
        const task = this.tasks.find(t => t.id === taskId);
        if (!task) return;
        
        // Implementation would show edit form similar to addTask
        console.log('Edit task:', task);
        this.showMessage('Edit functionality to be implemented', 'info');
    }
    
    removeTask(taskId) {
        if (!confirm('Are you sure you want to remove this task?')) return;
        
        const task = this.tasks.find(t => t.id === taskId);
        if (!task) return;
        
        // Remove from server (implementation needed)
        // For now, just remove from local data and DOM
        
        // Remove from tasks array
        this.tasks = this.tasks.filter(t => t.id !== taskId);
        
        // Remove from week
        const weekTasks = this.weeks.get(task.week) || [];
        this.weeks.set(task.week, weekTasks.filter(t => t.id !== taskId));
        
        // Remove from DOM
        const taskElement = document.querySelector(`[data-task-id="${taskId}"]`);
        if (taskElement) {
            taskElement.remove();
        }
        
        this.showMessage('Task removed', 'success');
    }
    
    exportBoard() {
        const exportData = {
            weeks: Object.fromEntries(this.weeks),
            tasks: this.tasks,
            exported_at: new Date().toISOString()
        };
        
        const blob = new Blob([JSON.stringify(exportData, null, 2)], {
            type: 'application/json'
        });
        
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'pull-planning-board.json';
        link.click();
        
        URL.revokeObjectURL(url);
    }
    
    showMessage(message, type = 'info') {
        const alertClass = type === 'error' ? 'alert-danger' : 
                          type === 'success' ? 'alert-success' : 
                          type === 'warning' ? 'alert-warning' : 'alert-info';
        
        const alert = document.createElement('div');
        alert.className = `alert ${alertClass} alert-dismissible fade show`;
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        this.container.insertBefore(alert, this.container.firstChild);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 5000);
    }
    
    // Public methods
    refreshBoard() {
        this.createWeekColumns();
        // Reload data would go here
    }
    
    getWeekData(weekNumber) {
        return this.weeks.get(weekNumber) || [];
    }
    
    getAllTasks() {
        return this.tasks;
    }
}

// Initialize Pull Planning when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('pull-planning-container')) {
        window.pullPlanning = new PullPlanningBoard('pull-planning-container');
        
        // Load data if available
        if (window.pullPlanningData) {
            window.pullPlanning.setData(window.pullPlanningData);
        }
    }
});
