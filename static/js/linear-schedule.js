/**
 * Linear Schedule Implementation for BBSchedule Platform
 * Time-Distance diagram for construction projects
 */

class LinearSchedule {
    constructor(containerId, options = {}) {
        this.container = d3.select(`#${containerId}`);
        this.options = {
            margin: { top: 40, right: 50, bottom: 60, left: 80 },
            height: 500,
            dateFormat: d3.timeFormat("%m/%d"),
            locationLabel: "Station",
            ...options
        };
        
        this.tasks = [];
        this.svg = null;
        this.timeScale = null;
        this.locationScale = null;
        
        this.init();
    }
    
    init() {
        // Clear existing content
        this.container.selectAll("*").remove();
        
        // Create SVG
        this.svg = this.container
            .append("svg")
            .attr("class", "linear-schedule")
            .style("width", "100%")
            .style("height", this.options.height);
            
        // Create main group
        this.mainGroup = this.svg
            .append("g")
            .attr("transform", `translate(${this.options.margin.left}, ${this.options.margin.top})`);
            
        // Create tooltip
        this.tooltip = d3.select("body")
            .append("div")
            .attr("class", "linear-tooltip")
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
            start_date: new Date(task.start_date),
            end_date: new Date(task.end_date),
            station_start: parseFloat(task.station_start) || 0,
            station_end: parseFloat(task.station_end) || 0
        })).filter(task => 
            task.station_start !== undefined && 
            task.station_end !== undefined &&
            !isNaN(task.station_start) &&
            !isNaN(task.station_end)
        );
        
        this.render();
    }
    
    render() {
        if (this.tasks.length === 0) {
            this.showEmptyState();
            return;
        }
        
        // Calculate dimensions
        const width = this.container.node().offsetWidth - this.options.margin.left - this.options.margin.right;
        const height = this.options.height - this.options.margin.top - this.options.margin.bottom;
        
        // Create scales
        const timeExtent = d3.extent(this.tasks.flatMap(d => [d.start_date, d.end_date]));
        this.timeScale = d3.scaleTime()
            .domain(timeExtent)
            .range([0, width]);
            
        const locationExtent = d3.extent(this.tasks.flatMap(d => [d.station_start, d.station_end]));
        this.locationScale = d3.scaleLinear()
            .domain(locationExtent)
            .range([height, 0]);
        
        // Render axes
        this.renderAxes(width, height);
        
        // Render grid
        this.renderGrid(width, height);
        
        // Render activities
        this.renderActivities();
        
        // Render production rates
        this.renderProductionRates();
        
        // Render current date line
        this.renderCurrentDateLine(height);
    }
    
    renderAxes(width, height) {
        // Remove existing axes
        this.mainGroup.selectAll(".axis").remove();
        
        // Time axis (bottom)
        const timeAxis = d3.axisBottom(this.timeScale)
            .tickFormat(this.options.dateFormat)
            .ticks(d3.timeWeek.every(1));
            
        this.mainGroup
            .append("g")
            .attr("class", "axis time-axis")
            .attr("transform", `translate(0, ${height})`)
            .call(timeAxis);
            
        // Location axis (left)
        const locationAxis = d3.axisLeft(this.locationScale)
            .tickFormat(d => `${d.toFixed(0)}`);
            
        this.mainGroup
            .append("g")
            .attr("class", "axis location-axis")
            .call(locationAxis);
            
        // Add axis labels
        this.mainGroup
            .append("text")
            .attr("class", "axis-label")
            .attr("x", width / 2)
            .attr("y", height + 50)
            .style("text-anchor", "middle")
            .style("font-weight", "600")
            .text("Time");
            
        this.mainGroup
            .append("text")
            .attr("class", "axis-label")
            .attr("transform", "rotate(-90)")
            .attr("y", -60)
            .attr("x", -height / 2)
            .style("text-anchor", "middle")
            .style("font-weight", "600")
            .text(this.options.locationLabel);
    }
    
    renderGrid(width, height) {
        // Remove existing grid
        this.mainGroup.selectAll(".grid").remove();
        
        // Vertical grid lines (time)
        this.mainGroup.selectAll(".time-grid")
            .data(this.timeScale.ticks(d3.timeWeek.every(1)))
            .enter()
            .append("line")
            .attr("class", "grid time-grid")
            .attr("x1", d => this.timeScale(d))
            .attr("x2", d => this.timeScale(d))
            .attr("y1", 0)
            .attr("y2", height)
            .style("stroke", "#e0e0e0")
            .style("stroke-width", 1)
            .style("stroke-dasharray", "2,2");
            
        // Horizontal grid lines (location)
        this.mainGroup.selectAll(".location-grid")
            .data(this.locationScale.ticks(10))
            .enter()
            .append("line")
            .attr("class", "grid location-grid")
            .attr("x1", 0)
            .attr("x2", width)
            .attr("y1", d => this.locationScale(d))
            .attr("y2", d => this.locationScale(d))
            .style("stroke", "#e0e0e0")
            .style("stroke-width", 1)
            .style("stroke-dasharray", "2,2");
    }
    
    renderActivities() {
        // Group activities by name for consistent coloring
        const activityGroups = d3.group(this.tasks, d => d.name);
        const colorScale = d3.scaleOrdinal(d3.schemeCategory10);
        
        // Remove existing activities
        this.mainGroup.selectAll(".activity").remove();
        
        this.tasks.forEach((task, index) => {
            const line = d3.line()
                .x(d => this.timeScale(d.date))
                .y(d => this.locationScale(d.station))
                .curve(d3.curveLinear);
                
            // Create data points for the line
            const lineData = [
                { date: task.start_date, station: task.station_start },
                { date: task.end_date, station: task.station_end }
            ];
            
            // Draw activity line
            this.mainGroup
                .append("path")
                .datum(lineData)
                .attr("class", `activity activity-${task.id}`)
                .attr("d", line)
                .style("stroke", colorScale(task.name))
                .style("stroke-width", 3)
                .style("fill", "none")
                .style("opacity", task.status === 'completed' ? 1 : 0.7)
                .style("cursor", "pointer")
                .on("mouseover", (event) => this.showTooltip(event, task))
                .on("mouseout", () => this.hideTooltip())
                .on("click", () => this.selectActivity(task));
                
            // Add start and end markers
            this.mainGroup
                .append("circle")
                .attr("class", `activity-marker start-marker`)
                .attr("cx", this.timeScale(task.start_date))
                .attr("cy", this.locationScale(task.station_start))
                .attr("r", 4)
                .style("fill", colorScale(task.name))
                .style("stroke", "white")
                .style("stroke-width", 2);
                
            this.mainGroup
                .append("circle")
                .attr("class", `activity-marker end-marker`)
                .attr("cx", this.timeScale(task.end_date))
                .attr("cy", this.locationScale(task.station_end))
                .attr("r", 4)
                .style("fill", colorScale(task.name))
                .style("stroke", "white")
                .style("stroke-width", 2);
                
            // Add activity label
            const midX = (this.timeScale(task.start_date) + this.timeScale(task.end_date)) / 2;
            const midY = (this.locationScale(task.station_start) + this.locationScale(task.station_end)) / 2;
            
            this.mainGroup
                .append("text")
                .attr("class", "activity-label")
                .attr("x", midX)
                .attr("y", midY - 10)
                .style("text-anchor", "middle")
                .style("font-size", "10px")
                .style("font-weight", "600")
                .style("fill", colorScale(task.name))
                .style("pointer-events", "none")
                .text(task.name);
        });
        
        // Create legend
        this.renderLegend(Array.from(activityGroups.keys()), colorScale);
    }
    
    renderProductionRates() {
        // Calculate and display production rates for each activity
        this.tasks.forEach(task => {
            const distance = Math.abs(task.station_end - task.station_start);
            const timeSpan = (task.end_date - task.start_date) / (1000 * 60 * 60 * 24); // days
            const rate = distance / timeSpan; // units per day
            
            if (rate > 0) {
                const midX = (this.timeScale(task.start_date) + this.timeScale(task.end_date)) / 2;
                const midY = (this.locationScale(task.station_start) + this.locationScale(task.station_end)) / 2;
                
                this.mainGroup
                    .append("text")
                    .attr("class", "production-rate")
                    .attr("x", midX)
                    .attr("y", midY + 15)
                    .style("text-anchor", "middle")
                    .style("font-size", "8px")
                    .style("fill", "#666")
                    .style("pointer-events", "none")
                    .text(`${rate.toFixed(1)} units/day`);
            }
        });
    }
    
    renderLegend(activities, colorScale) {
        // Remove existing legend
        this.mainGroup.selectAll(".legend").remove();
        
        const legend = this.mainGroup
            .append("g")
            .attr("class", "legend")
            .attr("transform", "translate(10, 10)");
            
        const legendItems = legend.selectAll(".legend-item")
            .data(activities)
            .enter()
            .append("g")
            .attr("class", "legend-item")
            .attr("transform", (d, i) => `translate(0, ${i * 20})`);
            
        legendItems
            .append("line")
            .attr("x1", 0)
            .attr("x2", 15)
            .attr("y1", 0)
            .attr("y2", 0)
            .style("stroke", colorScale)
            .style("stroke-width", 3);
            
        legendItems
            .append("text")
            .attr("x", 20)
            .attr("y", 0)
            .attr("dy", "0.35em")
            .style("font-size", "12px")
            .text(d => d);
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
                
            // Add label
            this.mainGroup
                .append("text")
                .attr("class", "current-date-label")
                .attr("x", this.timeScale(today) + 5)
                .attr("y", 15)
                .style("font-size", "10px")
                .style("font-weight", "600")
                .style("fill", "#ff4444")
                .text("Today");
        }
    }
    
    showTooltip(event, task) {
        const distance = Math.abs(task.station_end - task.station_start);
        const timeSpan = (task.end_date - task.start_date) / (1000 * 60 * 60 * 24);
        const rate = distance / timeSpan;
        
        this.tooltip.transition()
            .duration(200)
            .style("opacity", .9);
            
        this.tooltip.html(`
            <strong>${task.name}</strong><br/>
            Start: ${this.options.dateFormat(task.start_date)} @ ${task.station_start}<br/>
            End: ${this.options.dateFormat(task.end_date)} @ ${task.station_end}<br/>
            Duration: ${timeSpan.toFixed(1)} days<br/>
            Distance: ${distance.toFixed(1)} units<br/>
            Rate: ${rate.toFixed(2)} units/day<br/>
            Progress: ${task.progress}%<br/>
            Status: ${task.status}
        `)
            .style("left", (event.pageX + 10) + "px")
            .style("top", (event.pageY - 28) + "px");
    }
    
    hideTooltip() {
        this.tooltip.transition()
            .duration(500)
            .style("opacity", 0);
    }
    
    selectActivity(task) {
        // Highlight selected activity
        this.mainGroup.selectAll(".activity")
            .style("opacity", 0.3);
            
        this.mainGroup.select(`.activity-${task.id}`)
            .style("opacity", 1)
            .style("stroke-width", 5);
            
        // Show activity details
        this.showActivityDetails(task);
    }
    
    showActivityDetails(task) {
        // Create or update activity details panel
        let detailsPanel = document.getElementById('activity-details');
        if (!detailsPanel) {
            detailsPanel = document.createElement('div');
            detailsPanel.id = 'activity-details';
            detailsPanel.className = 'card mt-3';
            this.container.node().parentNode.appendChild(detailsPanel);
        }
        
        const distance = Math.abs(task.station_end - task.station_start);
        const timeSpan = (task.end_date - task.start_date) / (1000 * 60 * 60 * 24);
        const rate = distance / timeSpan;
        
        detailsPanel.innerHTML = `
            <div class="card-header">
                <h5>Activity Details: ${task.name}</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Start:</strong> ${this.options.dateFormat(task.start_date)} @ Station ${task.station_start}</p>
                        <p><strong>End:</strong> ${this.options.dateFormat(task.end_date)} @ Station ${task.station_end}</p>
                        <p><strong>Duration:</strong> ${timeSpan.toFixed(1)} days</p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>Distance:</strong> ${distance.toFixed(1)} units</p>
                        <p><strong>Production Rate:</strong> ${rate.toFixed(2)} units/day</p>
                        <p><strong>Progress:</strong> ${task.progress}%</p>
                    </div>
                </div>
                <div class="progress mb-2">
                    <div class="progress-bar" style="width: ${task.progress}%"></div>
                </div>
                <span class="badge badge-status badge-${task.status.replace('_', '-')}">${task.status}</span>
            </div>
        `;
    }
    
    showEmptyState() {
        this.container.html(`
            <div class="text-center py-5">
                <i class="fas fa-chart-line fa-3x text-muted mb-3"></i>
                <h5>No Linear Schedule Data</h5>
                <p class="text-muted">Add tasks with location data to view the linear schedule.</p>
            </div>
        `);
    }
    
    // Public methods
    addTask(task) {
        this.tasks.push({
            ...task,
            start_date: new Date(task.start_date),
            end_date: new Date(task.end_date),
            station_start: parseFloat(task.station_start),
            station_end: parseFloat(task.station_end)
        });
        this.render();
    }
    
    updateTask(taskId, updates) {
        const task = this.tasks.find(t => t.id === taskId);
        if (task) {
            Object.assign(task, updates);
            if (updates.start_date) task.start_date = new Date(updates.start_date);
            if (updates.end_date) task.end_date = new Date(updates.end_date);
            if (updates.station_start) task.station_start = parseFloat(updates.station_start);
            if (updates.station_end) task.station_end = parseFloat(updates.station_end);
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
            link.download = 'linear-schedule.png';
            link.href = canvas.toDataURL();
            link.click();
        };
        
        img.src = 'data:image/svg+xml;base64,' + btoa(svgString);
    }
}

// Initialize Linear Schedule when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('linear-schedule-container')) {
        window.linearSchedule = new LinearSchedule('linear-schedule-container');
        
        // Load tasks data if available
        if (window.linearTasksData) {
            window.linearSchedule.setData(window.linearTasksData);
        }
    }
});
