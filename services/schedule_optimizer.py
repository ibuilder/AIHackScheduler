from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
from models import Project, Task, Resource, ResourceAssignment, TaskDependency, TaskStatus
from extensions import db
import numpy as np

class ScheduleOptimizer:
    def __init__(self):
        self.optimization_methods = {
            'time': self._optimize_for_time,
            'cost': self._optimize_for_cost,
            'resource': self._optimize_for_resources
        }

    def optimize_project_schedule(self, project_id: int, optimization_type: str = 'time') -> Dict[str, Any]:
        """Optimize project schedule based on specified criteria."""
        if optimization_type not in self.optimization_methods:
            raise ValueError(f"Unsupported optimization type: {optimization_type}")
        
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        if not tasks:
            return {
                'success': False,
                'error': 'No tasks found for optimization'
            }
        
        # Run optimization
        optimization_method = self.optimization_methods[optimization_type]
        results = optimization_method(project, tasks)
        
        return {
            'success': True,
            'optimization_type': optimization_type,
            'project_id': project_id,
            'results': results,
            'generated_at': datetime.utcnow().isoformat()
        }

    def _optimize_for_time(self, project: Project, tasks: List[Task]) -> Dict[str, Any]:
        """Optimize schedule to minimize project duration."""
        # Calculate critical path
        critical_path = self._find_critical_path(tasks)
        
        # Identify optimization opportunities
        optimizations = []
        
        # 1. Task parallelization opportunities
        parallel_opportunities = self._find_parallelization_opportunities(tasks)
        if parallel_opportunities:
            optimizations.extend(parallel_opportunities)
        
        # 2. Duration compression opportunities
        compression_opportunities = self._find_compression_opportunities(tasks)
        if compression_opportunities:
            optimizations.extend(compression_opportunities)
        
        # 3. Resource reallocation for critical path
        resource_optimizations = self._optimize_critical_path_resources(critical_path, tasks)
        if resource_optimizations:
            optimizations.extend(resource_optimizations)
        
        # Calculate potential time savings
        potential_savings = sum(opt.get('time_saved_days', 0) for opt in optimizations)
        
        return {
            'critical_path': [
                {
                    'task_id': task.id,
                    'task_name': task.name,
                    'duration': task.duration,
                    'start_date': task.start_date.isoformat(),
                    'end_date': task.end_date.isoformat()
                }
                for task in critical_path
            ],
            'optimizations': optimizations,
            'potential_time_savings_days': potential_savings,
            'current_duration_days': (project.end_date - project.start_date).days,
            'optimized_duration_days': max(1, (project.end_date - project.start_date).days - potential_savings)
        }

    def _optimize_for_cost(self, project: Project, tasks: List[Task]) -> Dict[str, Any]:
        """Optimize schedule to minimize project cost."""
        resources = Resource.query.filter_by(project_id=project.id).all()
        resource_assignments = ResourceAssignment.query.join(Task).filter(
            Task.project_id == project.id
        ).all()
        
        optimizations = []
        
        # 1. Resource utilization optimization
        utilization_opts = self._optimize_resource_utilization(resources, resource_assignments)
        if utilization_opts:
            optimizations.extend(utilization_opts)
        
        # 2. Task scheduling to minimize resource costs
        scheduling_opts = self._optimize_task_scheduling_for_cost(tasks, resources)
        if scheduling_opts:
            optimizations.extend(scheduling_opts)
        
        # 3. Resource substitution opportunities
        substitution_opts = self._find_resource_substitutions(resources, resource_assignments)
        if substitution_opts:
            optimizations.extend(substitution_opts)
        
        # Calculate potential cost savings
        potential_savings = sum(opt.get('cost_saved', 0) for opt in optimizations)
        current_cost = sum(r.unit_cost * r.total_quantity for r in resources if r.unit_cost)
        
        return {
            'optimizations': optimizations,
            'potential_cost_savings': potential_savings,
            'current_estimated_cost': current_cost,
            'optimized_estimated_cost': max(0, current_cost - potential_savings),
            'savings_percentage': (potential_savings / current_cost * 100) if current_cost > 0 else 0
        }

    def _optimize_for_resources(self, project: Project, tasks: List[Task]) -> Dict[str, Any]:
        """Optimize schedule for resource efficiency."""
        resources = Resource.query.filter_by(project_id=project.id).all()
        
        optimizations = []
        
        # 1. Resource leveling
        leveling_opts = self._optimize_resource_leveling(tasks, resources)
        if leveling_opts:
            optimizations.extend(leveling_opts)
        
        # 2. Resource conflict resolution
        conflict_opts = self._resolve_resource_conflicts(tasks, resources)
        if conflict_opts:
            optimizations.extend(conflict_opts)
        
        # 3. Resource capacity optimization
        capacity_opts = self._optimize_resource_capacity(resources)
        if capacity_opts:
            optimizations.extend(capacity_opts)
        
        return {
            'optimizations': optimizations,
            'resource_utilization_analysis': self._analyze_resource_utilization(resources),
            'recommended_adjustments': self._recommend_resource_adjustments(resources, tasks)
        }

    def _find_critical_path(self, tasks: List[Task]) -> List[Task]:
        """Find the critical path using CPM algorithm."""
        # Build task dependency graph
        task_dict = {task.id: task for task in tasks}
        dependencies = TaskDependency.query.filter(
            TaskDependency.task_id.in_(task_dict.keys())
        ).all()
        
        # Calculate earliest start/finish times (forward pass)
        earliest_start = {}
        earliest_finish = {}
        
        for task in tasks:
            if not any(dep.task_id == task.id for dep in dependencies):
                # Start task
                earliest_start[task.id] = 0
                earliest_finish[task.id] = task.duration
            else:
                # Dependent task
                max_predecessor_finish = 0
                for dep in dependencies:
                    if dep.task_id == task.id:
                        predecessor = task_dict[dep.predecessor_task_id]
                        max_predecessor_finish = max(
                            max_predecessor_finish,
                            earliest_finish.get(predecessor.id, 0) + dep.lag_days
                        )
                
                earliest_start[task.id] = max_predecessor_finish
                earliest_finish[task.id] = max_predecessor_finish + task.duration
        
        # Calculate latest start/finish times (backward pass)
        project_duration = max(earliest_finish.values()) if earliest_finish else 0
        latest_start = {}
        latest_finish = {}
        
        for task in reversed(tasks):
            if not any(dep.predecessor_task_id == task.id for dep in dependencies):
                # End task
                latest_finish[task.id] = project_duration
                latest_start[task.id] = project_duration - task.duration
            else:
                # Predecessor task
                min_successor_start = float('inf')
                for dep in dependencies:
                    if dep.predecessor_task_id == task.id:
                        successor = task_dict[dep.task_id]
                        min_successor_start = min(
                            min_successor_start,
                            latest_start.get(successor.id, project_duration) - dep.lag_days
                        )
                
                latest_finish[task.id] = min_successor_start
                latest_start[task.id] = min_successor_start - task.duration
        
        # Identify critical tasks (tasks with zero float)
        critical_tasks = []
        for task in tasks:
            float_time = latest_start[task.id] - earliest_start[task.id]
            if float_time <= 0:
                critical_tasks.append(task)
        
        return critical_tasks

    def _find_parallelization_opportunities(self, tasks: List[Task]) -> List[Dict]:
        """Find tasks that can be executed in parallel."""
        opportunities = []
        dependencies = TaskDependency.query.filter(
            TaskDependency.task_id.in_([task.id for task in tasks])
        ).all()
        
        dependency_map = {}
        for dep in dependencies:
            if dep.task_id not in dependency_map:
                dependency_map[dep.task_id] = []
            dependency_map[dep.task_id].append(dep.predecessor_task_id)
        
        # Find independent tasks that are currently sequential
        for i, task1 in enumerate(tasks):
            for task2 in tasks[i+1:]:
                # Check if tasks are independent
                task1_deps = set(dependency_map.get(task1.id, []))
                task2_deps = set(dependency_map.get(task2.id, []))
                
                if (task1.id not in task2_deps and 
                    task2.id not in task1_deps and
                    not task1_deps.intersection(task2_deps)):
                    
                    # Check if they're currently sequential
                    if abs((task1.start_date - task2.end_date).days) <= 1:
                        time_saved = min(task1.duration, task2.duration)
                        opportunities.append({
                            'type': 'parallelization',
                            'description': f'Run tasks "{task1.name}" and "{task2.name}" in parallel',
                            'task_ids': [task1.id, task2.id],
                            'time_saved_days': time_saved,
                            'impact': 'medium',
                            'implementation_effort': 'low'
                        })
        
        return opportunities[:5]  # Return top 5 opportunities

    def _find_compression_opportunities(self, tasks: List[Task]) -> List[Dict]:
        """Find task duration compression opportunities."""
        opportunities = []
        
        for task in tasks:
            if task.duration > 3:  # Only consider tasks longer than 3 days
                # Fast-tracking opportunity
                max_compression = min(task.duration * 0.2, 2)  # Max 20% or 2 days
                opportunities.append({
                    'type': 'fast_tracking',
                    'description': f'Compress task "{task.name}" by adding resources',
                    'task_id': task.id,
                    'time_saved_days': max_compression,
                    'additional_cost': task.duration * 100,  # Estimated additional cost
                    'impact': 'high' if max_compression >= 2 else 'medium',
                    'implementation_effort': 'medium'
                })
        
        # Sort by potential time savings
        opportunities.sort(key=lambda x: x['time_saved_days'], reverse=True)
        return opportunities[:3]  # Return top 3 opportunities

    def _optimize_critical_path_resources(self, critical_tasks: List[Task], all_tasks: List[Task]) -> List[Dict]:
        """Optimize resource allocation for critical path tasks."""
        optimizations = []
        
        for critical_task in critical_tasks:
            # Find resources that could be reallocated from non-critical tasks
            resource_assignments = ResourceAssignment.query.filter_by(
                task_id=critical_task.id
            ).all()
            
            for assignment in resource_assignments:
                # Look for similar resources in non-critical tasks
                other_assignments = ResourceAssignment.query.join(Task).filter(
                    ResourceAssignment.resource_id == assignment.resource_id,
                    Task.id != critical_task.id,
                    Task.id.in_([t.id for t in all_tasks if t not in critical_tasks])
                ).all()
                
                if other_assignments:
                    optimizations.append({
                        'type': 'resource_reallocation',
                        'description': f'Reallocate resources to critical task "{critical_task.name}"',
                        'from_task_id': other_assignments[0].task_id,
                        'to_task_id': critical_task.id,
                        'resource_id': assignment.resource_id,
                        'time_saved_days': 1,  # Estimated time savings
                        'impact': 'high',
                        'implementation_effort': 'medium'
                    })
        
        return optimizations[:3]

    def _optimize_resource_utilization(self, resources: List[Resource], assignments: List[ResourceAssignment]) -> List[Dict]:
        """Optimize resource utilization to reduce costs."""
        optimizations = []
        
        # Calculate utilization for each resource
        for resource in resources:
            resource_assignments = [a for a in assignments if a.resource_id == resource.id]
            total_assigned = sum(a.quantity for a in resource_assignments)
            
            if resource.total_quantity > 0:
                utilization = total_assigned / resource.total_quantity
                
                if utilization < 0.7:  # Under-utilized resource
                    optimizations.append({
                        'type': 'reduce_resource',
                        'description': f'Reduce "{resource.name}" allocation (currently {utilization:.1%} utilized)',
                        'resource_id': resource.id,
                        'current_quantity': resource.total_quantity,
                        'recommended_quantity': total_assigned * 1.1,  # 10% buffer
                        'cost_saved': (resource.total_quantity - total_assigned * 1.1) * resource.unit_cost if resource.unit_cost else 0,
                        'impact': 'medium'
                    })
                
                elif utilization > 0.95:  # Over-utilized resource
                    optimizations.append({
                        'type': 'increase_resource',
                        'description': f'Increase "{resource.name}" allocation (currently {utilization:.1%} utilized)',
                        'resource_id': resource.id,
                        'current_quantity': resource.total_quantity,
                        'recommended_quantity': total_assigned * 1.2,  # 20% buffer
                        'additional_cost': (total_assigned * 1.2 - resource.total_quantity) * resource.unit_cost if resource.unit_cost else 0,
                        'impact': 'high'
                    })
        
        return optimizations

    def _optimize_task_scheduling_for_cost(self, tasks: List[Task], resources: List[Resource]) -> List[Dict]:
        """Optimize task scheduling to minimize resource costs."""
        optimizations = []
        
        # Group tasks by resource requirements
        resource_intensive_tasks = []
        for task in tasks:
            assignments = ResourceAssignment.query.filter_by(task_id=task.id).all()
            if len(assignments) >= 3:  # Tasks with 3+ resource types
                resource_intensive_tasks.append(task)
        
        # Suggest scheduling optimization
        if len(resource_intensive_tasks) >= 2:
            optimizations.append({
                'type': 'schedule_adjustment',
                'description': 'Stagger resource-intensive tasks to reduce peak resource costs',
                'task_ids': [task.id for task in resource_intensive_tasks[:3]],
                'cost_saved': 5000,  # Estimated savings from reduced peak usage
                'impact': 'medium',
                'implementation_effort': 'low'
            })
        
        return optimizations

    def _find_resource_substitutions(self, resources: List[Resource], assignments: List[ResourceAssignment]) -> List[Dict]:
        """Find opportunities to substitute expensive resources with cheaper alternatives."""
        optimizations = []
        
        # Find high-cost resources
        high_cost_resources = [r for r in resources if r.unit_cost and r.unit_cost > 100]
        
        for resource in high_cost_resources:
            # Look for similar, cheaper resources
            similar_resources = [
                r for r in resources 
                if r.type == resource.type and r.unit_cost and r.unit_cost < resource.unit_cost * 0.8
            ]
            
            if similar_resources:
                cheapest = min(similar_resources, key=lambda x: x.unit_cost)
                cost_difference = resource.unit_cost - cheapest.unit_cost
                
                optimizations.append({
                    'type': 'resource_substitution',
                    'description': f'Substitute "{resource.name}" with cheaper alternative "{cheapest.name}"',
                    'from_resource_id': resource.id,
                    'to_resource_id': cheapest.id,
                    'cost_saved': cost_difference * resource.total_quantity,
                    'impact': 'medium',
                    'implementation_effort': 'low'
                })
        
        return optimizations[:2]

    def _optimize_resource_leveling(self, tasks: List[Task], resources: List[Resource]) -> List[Dict]:
        """Optimize resource leveling to smooth resource demand."""
        optimizations = []
        
        # This is a simplified resource leveling algorithm
        # In practice, you would use more sophisticated algorithms like the Resource Constrained Project Scheduling Problem (RCPSP)
        
        optimizations.append({
            'type': 'resource_leveling',
            'description': 'Adjust task scheduling to smooth resource demand curves',
            'impact': 'medium',
            'implementation_effort': 'high',
            'benefits': [
                'Reduced resource peak demands',
                'More consistent workforce utilization',
                'Lower overtime costs'
            ]
        })
        
        return optimizations

    def _resolve_resource_conflicts(self, tasks: List[Task], resources: List[Resource]) -> List[Dict]:
        """Identify and resolve resource conflicts."""
        optimizations = []
        
        # Find tasks with overlapping resource requirements
        task_resources = {}
        for task in tasks:
            assignments = ResourceAssignment.query.filter_by(task_id=task.id).all()
            task_resources[task.id] = [a.resource_id for a in assignments]
        
        conflicts = []
        for i, task1 in enumerate(tasks):
            for task2 in tasks[i+1:]:
                # Check if tasks overlap in time and share resources
                if (task1.start_date <= task2.end_date and task2.start_date <= task1.end_date):
                    common_resources = set(task_resources.get(task1.id, [])).intersection(
                        set(task_resources.get(task2.id, []))
                    )
                    if common_resources:
                        conflicts.append((task1, task2, common_resources))
        
        for task1, task2, common_resources in conflicts[:3]:  # Top 3 conflicts
            optimizations.append({
                'type': 'resolve_conflict',
                'description': f'Resolve resource conflict between "{task1.name}" and "{task2.name}"',
                'task_ids': [task1.id, task2.id],
                'conflicting_resources': list(common_resources),
                'suggested_action': 'Reschedule one task or allocate additional resources',
                'impact': 'high',
                'implementation_effort': 'medium'
            })
        
        return optimizations

    def _optimize_resource_capacity(self, resources: List[Resource]) -> List[Dict]:
        """Optimize resource capacity allocation."""
        optimizations = []
        
        for resource in resources:
            if resource.available_quantity and resource.total_quantity:
                availability_ratio = resource.available_quantity / resource.total_quantity
                
                if availability_ratio < 0.1:  # Very low availability
                    optimizations.append({
                        'type': 'increase_capacity',
                        'description': f'Increase capacity for "{resource.name}" (only {availability_ratio:.1%} available)',
                        'resource_id': resource.id,
                        'current_available': resource.available_quantity,
                        'recommended_increase': resource.total_quantity * 0.2,
                        'impact': 'high'
                    })
        
        return optimizations

    def _analyze_resource_utilization(self, resources: List[Resource]) -> Dict[str, Any]:
        """Analyze overall resource utilization."""
        total_resources = len(resources)
        labor_resources = len([r for r in resources if r.type == 'labor'])
        equipment_resources = len([r for r in resources if r.type == 'equipment'])
        material_resources = len([r for r in resources if r.type == 'material'])
        
        return {
            'total_resources': total_resources,
            'resource_breakdown': {
                'labor': labor_resources,
                'equipment': equipment_resources,
                'material': material_resources
            },
            'utilization_summary': 'Resource utilization analysis complete'
        }

    def _recommend_resource_adjustments(self, resources: List[Resource], tasks: List[Task]) -> List[Dict]:
        """Recommend resource adjustments based on project analysis."""
        recommendations = []
        
        # High-level recommendations
        recommendations.append({
            'category': 'capacity_planning',
            'recommendation': 'Consider implementing dynamic resource allocation based on task priorities',
            'priority': 'medium',
            'expected_benefit': 'Improved resource efficiency and cost reduction'
        })
        
        recommendations.append({
            'category': 'scheduling',
            'recommendation': 'Implement resource leveling to smooth demand patterns',
            'priority': 'high',
            'expected_benefit': 'Reduced peak resource costs and improved workflow'
        })
        
        return recommendations
