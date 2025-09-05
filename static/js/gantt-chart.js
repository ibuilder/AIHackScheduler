/**
 * Gantt Chart Implementation for BBSchedule Platform
 * Professional construction scheduling with drag-and-drop functionality
 */

class GanttChart {
    constructor(containerId, options = {}) {
        this.container = d3.select(`#${containerId}`);
        this.options = {
            margin: { top: 20, right: 50, bottom: 30, left: 200 },
            height: 400,
            taskHeight: 30,
            taskPadding: 5,
            dateFormat: d3.timeFormat("%Y-%m-%d"),
            ...options
        };
        
        this.tasks = [];
        this.svg = null;
        this.timeScale = null;
        this.taskScale = null;
        
        this.init();
    }
    
    init() {
        // Clear existing content
        this.container.selectAll("*").remove();
        
        // Create SVG
        this.svg = this.container
            .append("svg")
            .attr("class", "gantt-chart")
            .style("width", "100%")
            .style("height", this.options.height);
            
        // Create main group
        this.mainGroup = this.svg
            .append("g")
            .attr("transform", `translate(${this.options.margin.left}, ${this.options.margin.top})`);
            
        // Create tooltip
        this.tooltip = d3.select("body")
            .append("div")
            .attr("class", "tooltip")
            .style("opacity", 0)
            .style("position", "absolute")
            .style("background", "rgba(0, 0, 0, 0.8)")
            .style("color", "white")
            .style("padding", "8px")
            .style("border-radius", "4px")
            .style("font-size", "12px")
            .style("pointer-events", "none");
    }
    
    setData(tasks) {
        this.tasks = tasks.map(task => ({
            ...task,
            start: new Date(task.start),
            end: new Date(task.end),
            progress: task.progress || 0
        }));
        
        this.render();
    }
    
    render() {
        if (this.tasks.length === 0) return;
        
        // Calculate dimensions
        const width = this.container.node().offsetWidth - this.options.margin.left - this.options.margin.right;
        const height = this.tasks.length * (this.options.taskHeight + this.options.taskPadding);
        
        // Update SVG height
        this.svg.attr("height", height + this.options.margin.top + this.options.margin.bottom);
        
        // Create scales
        const timeExtent = d3.extent(this.tasks.flatMap(d => [d.start, d.end]));
        this.timeScale = d3.scaleTime()
            .domain(timeExtent)
            .range([0, width]);
            
        this.taskScale = d3.scaleBand()
            .domain(this.tasks.map(d => d.id))
            .range([0, height])
            .padding(0.1);
        
        // Render time axis
        this.renderTimeAxis(width);
        
        // Render task labels
        this.renderTaskLabels();
        
        // Render tasks
        this.renderTasks();
        
        // Render dependencies
        this.renderDependencies();
        
        // Render current date line
        this.renderCurrentDateLine(height);
    }
    
    renderTimeAxis(width) {
        // Remove existing axis
        this.mainGroup.selectAll(".time-axis").remove();
        
        const timeAxis = d3.axisTop(this.timeScale)
            .tickFormat(d3.timeFormat("%m/%d"))
            .ticks(d3.timeWeek.every(1));
            
        this.mainGroup
            .append("g")
            .attr("class", "time-axis")
            .call(timeAxis);
            
        // Add grid lines
        this.mainGroup.selectAll(".grid-line")
            .data(this.timeScale.ticks(d3.timeDay.every(1)))
            .enter()
            .append("line")
            .attr("class", "grid-line")
            .attr("x1", d => this.timeScale(d))
            .attr("x2", d => this.timeScale(d))
            .attr("y1", 0)
            .attr("y2", this.taskScale.range()[1])
            .style("stroke", "#e0e0e0")
            .style("stroke-width", 1);
    }
    
    renderTaskLabels() {
        // Remove existing labels
        this.svg.selectAll(".task-label").remove();
        
        this.svg.selectAll(".task-label")
            .data(this.tasks)
            .enter()
            .append("text")
            .attr("class", "task-label")
            .attr("x", this.options.margin.left - 10)
            .attr("y", d => this.options.margin.top + this.taskScale(d.id) + this.taskScale.bandwidth() / 2)
            .attr("dy", "0.35em")
            .style("text-anchor", "end")
            .style("font-size", "12px")
            .style("font-weight", "500")
            .text(d => d.name);
    }
    
    renderTasks() {
        const taskGroups = this.mainGroup.selectAll(".task-group")
            .data(this.tasks, d => d.id);
            
        // Remove old tasks
        taskGroups.exit().remove();
        
        // Create new task groups
        const newTaskGroups = taskGroups.enter()
            .append("g")
            .attr("class", "task-group");
            
        // Merge new and existing
        const allTaskGroups = newTaskGroups.merge(taskGroups);
        
        // Render task bars
        const taskBars = allTaskGroups.selectAll(".task-bar")
            .data(d => [d]);
            
        taskBars.enter()
            .append("rect")
            .attr("class", "task-bar gantt-task")
            .merge(taskBars)
            .attr("x", d => this.timeScale(d.start))
            .attr("y", d => this.taskScale(d.id))
            .attr("width", d => this.timeScale(d.end) - this.timeScale(d.start))
            .attr("height", this.taskScale.bandwidth())
            .attr("class", d => `task-bar gantt-task ${d.status.toLowerCase().replace('_', '-')}`)
            .style("cursor", "move")
            .on("mouseover", (event, d) => this.showTooltip(event, d))
            .on("mouseout", () => this.hideTooltip())
            .call(this.setupDragBehavior());
            
        // Render progress bars
        const progressBars = allTaskGroups.selectAll(".progress-bar")
            .data(d => [d]);
            
        progressBars.enter()
            .append("rect")
            .attr("class", "progress-bar")
            .merge(progressBars)
            .attr("x", d => this.timeScale(d.start))
            .attr("y", d => this.taskScale(d.id) + 2)
            .attr("width", d => (this.timeScale(d.end) - this.timeScale(d.start)) * (d.progress / 100))
            .attr("height", this.taskScale.bandwidth() - 4)
            .style("fill", "rgba(255, 255, 255, 0.7)")
            .style("pointer-events", "none");
            
        // Render task text
        const taskText = allTaskGroups.selectAll(".task-text")
            .data(d => [d]);
            
        taskText.enter()
            .append("text")
            .attr("class", "task-text")
            .merge(taskText)
            .attr("x", d => this.timeScale(d.start) + 5)
            .attr("y", d => this.taskScale(d.id) + this.taskScale.bandwidth() / 2)
            .attr("dy", "0.35em")
            .style("font-size", "11px")
            .style("font-weight", "500")
            .style("fill", "white")
            .style("pointer-events", "none")
            .text(d => `${d.progress}%`);
    }
    
    renderDependencies() {
        // Remove existing dependencies
        this.mainGroup.selectAll(".dependency").remove();
        
        this.tasks.forEach(task => {
            if (task.dependencies && task.dependencies.length > 0) {
                task.dependencies.forEach(depId => {
                    const predecessor = this.tasks.find(t => t.id === depId);
                    if (predecessor) {
                        this.drawDependencyLine(predecessor, task);
                    }
                });
            }
        });
    }
    
    drawDependencyLine(predecessor, successor) {
        const x1 = this.timeScale(predecessor.end);
        const y1 = this.taskScale(predecessor.id) + this.taskScale.bandwidth() / 2;
        const x2 = this.timeScale(successor.start);
        const y2 = this.taskScale(successor.id) + this.taskScale.bandwidth() / 2;
        
        const path = `M ${x1} ${y1} L ${x1 + 10} ${y1} L ${x1 + 10} ${y2} L ${x2} ${y2}`;
        
        this.mainGroup
            .append("path")
            .attr("class", "dependency")
            .attr("d", path)
            .style("fill", "none")
            .style("stroke", "#666")
            .style("stroke-width", 2)
            .style("marker-end", "url(#arrowhead)");
            
        // Add arrowhead marker
        if (!this.svg.select("#arrowhead").node()) {
            const defs = this.svg.append("defs");
            defs.append("marker")
                .attr("id", "arrowhead")
                .attr("viewBox", "0 -5 10 10")
                .attr("refX", 8)
                .attr("refY", 0)
                .attr("markerWidth", 6)
                .attr("markerHeight", 6)
                .attr("orient", "auto")
                .append("path")
                .attr("d", "M0,-5L10,0L0,5")
                .style("fill", "#666");
        }
    }
    
    renderCurrentDateLine(height) {
        const today = new Date();
        
        this.mainGroup.selectAll(".current-date-line").remove();
        
        if (today >= this.timeScale.domain()[0] && today <= this.timeScale.domain()[1]) {
            this.mainGroup
                .append("line")
                .attr("class", "current-date-line")
                .attr("x1", this.timeScale(today))
                .attr("x2", this.timeScale(today))
                .attr("y1", 0)
                .attr("y2", height)
                .style("stroke", "#ff4444")
                .style("stroke-width", 2)
                .style("stroke-dasharray", "5,5");
        }
    }
    
    setupDragBehavior() {
        return d3.drag()
            .on("start", (event, d) => {
                d3.select(event.sourceEvent.target).style("opacity", 0.7);
            })
            .on("drag", (event, d) => {
                const newStartDate = this.timeScale.invert(event.x);
                const duration = d.end - d.start;
                const newEndDate = new Date(newStartDate.getTime() + duration);
                
                // Update task dates
                d.start = newStartDate;
                d.end = newEndDate;
                
                // Re-render the task
                this.render();
            })
            .on("end", (event, d) => {
                d3.select(event.sourceEvent.target).style("opacity", 1);
                
                // Trigger update event
                this.onTaskUpdate(d);
            });
    }
    
    showTooltip(event, d) {
        this.tooltip.transition()
            .duration(200)
            .style("opacity", .9);
            
        this.tooltip.html(`
            <strong>${d.name}</strong><br/>
            Start: ${this.options.dateFormat(d.start)}<br/>
            End: ${this.options.dateFormat(d.end)}<br/>
            Progress: ${d.progress}%<br/>
            Status: ${d.status}
        `)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
    }
    
    hideTooltip() {
        this.tooltip.transition()
            .duration(500)
            .style("opacity", 0);
    }
    
    onTaskUpdate(task) {
        // Override this method to handle task updates
        console.log('Task updated:', task);
        
        // Send update to server
        fetch(`/scheduling/api/tasks/${task.id}/update`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').getAttribute('content')
            },
            body: JSON.stringify({
                start_date: this.options.dateFormat(task.start),
                end_date: this.options.dateFormat(task.end)
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error updating task:', data.error);
                // Revert changes and show error
                this.showUpdateError(data.error);
            } else {
                this.showUpdateSuccess();
            }
        })
        .catch(error => {
            console.error('Error:', error);
            this.showUpdateError('Failed to update task');
        });
    }
    
    showUpdateSuccess() {
        // Show success message
        const alert = document.createElement('div');
        alert.className = 'alert alert-success alert-dismissible fade show';
        alert.innerHTML = `
            <strong>Success!</strong> Task updated successfully.
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('.container').insertBefore(alert, document.querySelector('.container').firstChild);
        
        setTimeout(() => {
            alert.remove();
        }, 3000);
    }
    
    showUpdateError(message) {
        // Show error message
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show';
        alert.innerHTML = `
            <strong>Error!</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.querySelector('.container').insertBefore(alert, document.querySelector('.container').firstChild);
        
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }
    
    // Public methods
    addTask(task) {
        this.tasks.push({
            ...task,
            start: new Date(task.start),
            end: new Date(task.end)
        });
        this.render();
    }
    
    removeTask(taskId) {
        this.tasks = this.tasks.filter(t => t.id !== taskId);
        this.render();
    }
    
    updateTask(taskId, updates) {
        const task = this.tasks.find(t => t.id === taskId);
        if (task) {
            Object.assign(task, updates);
            if (updates.start) task.start = new Date(updates.start);
            if (updates.end) task.end = new Date(updates.end);
            this.render();
        }
    }
    
    exportAsPNG() {
        const svgElement = this.svg.node();
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        
        const svgString = new XMLSerializer().serializeToString(svgElement);
        const img = new Image();
        
        img.onload = function() {
            canvas.width = img.width;
            canvas.height = img.height;
            context.drawImage(img, 0, 0);
            
            const link = document.createElement('a');
            link.download = 'gantt-chart.png';
            link.href = canvas.toDataURL();
            link.click();
        };
        
        img.src = 'data:image/svg+xml;base64,' + btoa(svgString);
    }
}

// Initialize Gantt chart when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('gantt-chart-container')) {
        window.ganttChart = new GanttChart('gantt-chart-container');
        
        // Load tasks data if available
        if (window.ganttTasksData) {
            window.ganttChart.setData(window.ganttTasksData);
        }
    }
});
