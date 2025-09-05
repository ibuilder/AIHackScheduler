"""
Construction Project Templates for BBSchedule Platform
Predefined templates for common construction project types
"""

from datetime import datetime, timedelta
from models import TaskStatus

class ConstructionProjectTemplates:
    """Factory class for creating construction project templates"""
    
    @staticmethod
    def get_available_templates():
        """Get list of available project templates"""
        return [
            {
                'id': 'commercial_office',
                'name': 'Commercial Office Building',
                'description': 'Multi-story office building construction with standard phases',
                'duration_weeks': 52,
                'category': 'Commercial',
                'tasks_count': 45
            },
            {
                'id': 'residential_complex',
                'name': 'Residential Complex',
                'description': 'Multi-unit residential development with amenities',
                'duration_weeks': 36,
                'category': 'Residential',
                'tasks_count': 38
            },
            {
                'id': 'industrial_warehouse',
                'name': 'Industrial Warehouse',
                'description': 'Large-scale warehouse with loading docks and utilities',
                'duration_weeks': 28,
                'category': 'Industrial',
                'tasks_count': 32
            },
            {
                'id': 'retail_center',
                'name': 'Retail Shopping Center',
                'description': 'Multi-tenant retail space with parking and landscaping',
                'duration_weeks': 40,
                'category': 'Retail',
                'tasks_count': 42
            },
            {
                'id': 'infrastructure_road',
                'name': 'Road Infrastructure',
                'description': 'Highway/road construction with bridges and utilities',
                'duration_weeks': 24,
                'category': 'Infrastructure',
                'tasks_count': 28
            },
            {
                'id': 'hospital_medical',
                'name': 'Medical Facility',
                'description': 'Hospital or medical center with specialized systems',
                'duration_weeks': 60,
                'category': 'Healthcare',
                'tasks_count': 55
            }
        ]
    
    @staticmethod
    def create_commercial_office_template():
        """Create commercial office building template"""
        base_date = datetime.now().date()
        
        return {
            'name': 'Commercial Office Building',
            'description': 'Multi-story office building construction project',
            'tasks': [
                # Pre-Construction Phase (Weeks 1-4)
                {
                    'name': 'Site Survey and Geotechnical Analysis',
                    'description': 'Conduct detailed site survey and soil analysis',
                    'duration': 10,
                    'start_date': base_date,
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction',
                    'dependencies': []
                },
                {
                    'name': 'Permit Applications and Approvals',
                    'description': 'Submit building permits and obtain approvals',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=5),
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction',
                    'dependencies': ['Site Survey and Geotechnical Analysis']
                },
                {
                    'name': 'Final Design and Engineering',
                    'description': 'Complete architectural and engineering drawings',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=10),
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction',
                    'dependencies': ['Site Survey and Geotechnical Analysis']
                },
                
                # Site Preparation (Weeks 5-8)
                {
                    'name': 'Site Clearing and Grading',
                    'description': 'Clear vegetation and grade site to specifications',
                    'duration': 12,
                    'start_date': base_date + timedelta(days=28),
                    'priority': 'HIGH',
                    'phase': 'Site Preparation',
                    'dependencies': ['Permit Applications and Approvals']
                },
                {
                    'name': 'Utility Line Installation',
                    'description': 'Install water, sewer, electrical, and gas connections',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=35),
                    'priority': 'HIGH',
                    'phase': 'Site Preparation',
                    'dependencies': ['Site Clearing and Grading']
                },
                {
                    'name': 'Temporary Facilities Setup',
                    'description': 'Set up site office, storage, and safety barriers',
                    'duration': 5,
                    'start_date': base_date + timedelta(days=40),
                    'priority': 'MEDIUM',
                    'phase': 'Site Preparation',
                    'dependencies': ['Site Clearing and Grading']
                },
                
                # Foundation (Weeks 9-16)
                {
                    'name': 'Excavation and Earth Work',
                    'description': 'Excavate for foundation and basement areas',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=56),
                    'priority': 'HIGH',
                    'phase': 'Foundation',
                    'dependencies': ['Utility Line Installation']
                },
                {
                    'name': 'Foundation Footings and Walls',
                    'description': 'Pour concrete footings and foundation walls',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=70),
                    'priority': 'HIGH',
                    'phase': 'Foundation',
                    'dependencies': ['Excavation and Earth Work']
                },
                {
                    'name': 'Basement Waterproofing',
                    'description': 'Apply waterproofing membrane and drainage',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=90),
                    'priority': 'HIGH',
                    'phase': 'Foundation',
                    'dependencies': ['Foundation Footings and Walls']
                },
                {
                    'name': 'Foundation Backfill and Compaction',
                    'description': 'Backfill around foundation and compact soil',
                    'duration': 5,
                    'start_date': base_date + timedelta(days=100),
                    'priority': 'MEDIUM',
                    'phase': 'Foundation',
                    'dependencies': ['Basement Waterproofing']
                },
                
                # Structural Frame (Weeks 17-28)
                {
                    'name': 'Steel Frame Erection - Levels 1-5',
                    'description': 'Erect structural steel frame for lower floors',
                    'duration': 30,
                    'start_date': base_date + timedelta(days=112),
                    'priority': 'HIGH',
                    'phase': 'Structural',
                    'dependencies': ['Foundation Backfill and Compaction']
                },
                {
                    'name': 'Steel Frame Erection - Levels 6-10',
                    'description': 'Erect structural steel frame for upper floors',
                    'duration': 30,
                    'start_date': base_date + timedelta(days=135),
                    'priority': 'HIGH',
                    'phase': 'Structural',
                    'dependencies': ['Steel Frame Erection - Levels 1-5']
                },
                {
                    'name': 'Concrete Floor Slabs - Levels 1-5',
                    'description': 'Pour concrete floor slabs for lower levels',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=140),
                    'priority': 'HIGH',
                    'phase': 'Structural',
                    'dependencies': ['Steel Frame Erection - Levels 1-5']
                },
                {
                    'name': 'Concrete Floor Slabs - Levels 6-10',
                    'description': 'Pour concrete floor slabs for upper levels',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=160),
                    'priority': 'HIGH',
                    'phase': 'Structural',
                    'dependencies': ['Steel Frame Erection - Levels 6-10']
                },
                
                # Building Envelope (Weeks 29-36)
                {
                    'name': 'Exterior Wall Framing',
                    'description': 'Frame exterior walls and install sheathing',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=196),
                    'priority': 'HIGH',
                    'phase': 'Envelope',
                    'dependencies': ['Concrete Floor Slabs - Levels 1-5']
                },
                {
                    'name': 'Roofing Installation',
                    'description': 'Install roof decking, membrane, and finish roofing',
                    'duration': 18,
                    'start_date': base_date + timedelta(days=210),
                    'priority': 'HIGH',
                    'phase': 'Envelope',
                    'dependencies': ['Steel Frame Erection - Levels 6-10']
                },
                {
                    'name': 'Exterior Windows and Doors',
                    'description': 'Install windows, curtain wall, and exterior doors',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=220),
                    'priority': 'HIGH',
                    'phase': 'Envelope',
                    'dependencies': ['Exterior Wall Framing']
                },
                {
                    'name': 'Building Weatherization',
                    'description': 'Complete exterior insulation and weatherproofing',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=240),
                    'priority': 'MEDIUM',
                    'phase': 'Envelope',
                    'dependencies': ['Exterior Windows and Doors']
                },
                
                # MEP Systems (Weeks 25-40)
                {
                    'name': 'Electrical Rough-In',
                    'description': 'Install electrical conduit, wiring, and panels',
                    'duration': 30,
                    'start_date': base_date + timedelta(days=175),
                    'priority': 'HIGH',
                    'phase': 'MEP',
                    'dependencies': ['Concrete Floor Slabs - Levels 1-5']
                },
                {
                    'name': 'Plumbing Rough-In',
                    'description': 'Install plumbing pipes, drains, and fixtures rough-in',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=180),
                    'priority': 'HIGH',
                    'phase': 'MEP',
                    'dependencies': ['Concrete Floor Slabs - Levels 1-5']
                },
                {
                    'name': 'HVAC System Installation',
                    'description': 'Install ductwork, equipment, and controls',
                    'duration': 35,
                    'start_date': base_date + timedelta(days=200),
                    'priority': 'HIGH',
                    'phase': 'MEP',
                    'dependencies': ['Concrete Floor Slabs - Levels 6-10']
                },
                {
                    'name': 'Fire Protection Systems',
                    'description': 'Install sprinkler systems and fire alarms',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=220),
                    'priority': 'HIGH',
                    'phase': 'MEP',
                    'dependencies': ['Electrical Rough-In']
                },
                
                # Interior Construction (Weeks 37-48)
                {
                    'name': 'Interior Framing and Drywall',
                    'description': 'Frame interior walls and install drywall',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=259),
                    'priority': 'MEDIUM',
                    'phase': 'Interior',
                    'dependencies': ['Electrical Rough-In', 'Plumbing Rough-In']
                },
                {
                    'name': 'Flooring Installation',
                    'description': 'Install carpet, tile, hardwood, and other flooring',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=280),
                    'priority': 'MEDIUM',
                    'phase': 'Interior',
                    'dependencies': ['Interior Framing and Drywall']
                },
                {
                    'name': 'Interior Doors and Hardware',
                    'description': 'Install interior doors, frames, and hardware',
                    'duration': 10,
                    'start_date': base_date + timedelta(days=300),
                    'priority': 'MEDIUM',
                    'phase': 'Interior',
                    'dependencies': ['Interior Framing and Drywall']
                },
                {
                    'name': 'Painting and Wall Finishes',
                    'description': 'Prime and paint walls, install wall coverings',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=310),
                    'priority': 'LOW',
                    'phase': 'Interior',
                    'dependencies': ['Interior Doors and Hardware']
                },
                
                # Final Systems (Weeks 49-52)
                {
                    'name': 'Electrical Final Installation',
                    'description': 'Install outlets, switches, fixtures, and equipment',
                    'duration': 12,
                    'start_date': base_date + timedelta(days=336),
                    'priority': 'HIGH',
                    'phase': 'Final',
                    'dependencies': ['Interior Framing and Drywall']
                },
                {
                    'name': 'Plumbing Final Installation',
                    'description': 'Install final plumbing fixtures and connections',
                    'duration': 10,
                    'start_date': base_date + timedelta(days=340),
                    'priority': 'HIGH',
                    'phase': 'Final',
                    'dependencies': ['Interior Framing and Drywall']
                },
                {
                    'name': 'HVAC System Testing and Balancing',
                    'description': 'Test and balance HVAC systems for proper operation',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=350),
                    'priority': 'HIGH',
                    'phase': 'Final',
                    'dependencies': ['HVAC System Installation']
                },
                {
                    'name': 'Final Inspections and Testing',
                    'description': 'Complete all required inspections and system testing',
                    'duration': 10,
                    'start_date': base_date + timedelta(days=355),
                    'priority': 'HIGH',
                    'phase': 'Final',
                    'dependencies': ['Electrical Final Installation', 'Plumbing Final Installation']
                },
                {
                    'name': 'Site Cleanup and Landscaping',
                    'description': 'Final site cleanup, landscaping, and exterior work',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=360),
                    'priority': 'MEDIUM',
                    'phase': 'Final',
                    'dependencies': ['Final Inspections and Testing']
                },
                {
                    'name': 'Project Closeout and Handover',
                    'description': 'Final documentation, warranties, and client handover',
                    'duration': 5,
                    'start_date': base_date + timedelta(days=365),
                    'priority': 'HIGH',
                    'phase': 'Final',
                    'dependencies': ['Site Cleanup and Landscaping']
                }
            ]
        }
    
    @staticmethod
    def create_residential_complex_template():
        """Create residential complex template"""
        base_date = datetime.now().date()
        
        return {
            'name': 'Residential Complex',
            'description': 'Multi-unit residential development project',
            'tasks': [
                # Pre-Construction Phase
                {
                    'name': 'Site Planning and Design',
                    'description': 'Master planning and architectural design',
                    'duration': 15,
                    'start_date': base_date,
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction'
                },
                {
                    'name': 'Environmental Impact Assessment',
                    'description': 'Environmental studies and impact assessment',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=5),
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction'
                },
                {
                    'name': 'Zoning and Planning Approvals',
                    'description': 'Obtain zoning variances and planning approvals',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=15),
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction'
                },
                
                # Infrastructure Development
                {
                    'name': 'Site Infrastructure - Roads',
                    'description': 'Build internal roads and access ways',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=45),
                    'priority': 'HIGH',
                    'phase': 'Infrastructure'
                },
                {
                    'name': 'Site Infrastructure - Utilities',
                    'description': 'Install water, sewer, electrical infrastructure',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=60),
                    'priority': 'HIGH',
                    'phase': 'Infrastructure'
                },
                
                # Building Construction - Phase 1
                {
                    'name': 'Buildings A-C Foundation',
                    'description': 'Foundation work for first phase buildings',
                    'duration': 18,
                    'start_date': base_date + timedelta(days=85),
                    'priority': 'HIGH',
                    'phase': 'Construction Phase 1'
                },
                {
                    'name': 'Buildings A-C Framing',
                    'description': 'Structural framing for first phase',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=105),
                    'priority': 'HIGH',
                    'phase': 'Construction Phase 1'
                },
                {
                    'name': 'Buildings A-C MEP Systems',
                    'description': 'Mechanical, electrical, plumbing installation',
                    'duration': 30,
                    'start_date': base_date + timedelta(days=125),
                    'priority': 'HIGH',
                    'phase': 'Construction Phase 1'
                },
                {
                    'name': 'Buildings A-C Interior Finishes',
                    'description': 'Interior finishes and fixtures',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=150),
                    'priority': 'MEDIUM',
                    'phase': 'Construction Phase 1'
                },
                
                # Building Construction - Phase 2
                {
                    'name': 'Buildings D-F Foundation',
                    'description': 'Foundation work for second phase buildings',
                    'duration': 18,
                    'start_date': base_date + timedelta(days=130),
                    'priority': 'HIGH',
                    'phase': 'Construction Phase 2'
                },
                {
                    'name': 'Buildings D-F Framing',
                    'description': 'Structural framing for second phase',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=150),
                    'priority': 'HIGH',
                    'phase': 'Construction Phase 2'
                },
                {
                    'name': 'Buildings D-F MEP Systems',
                    'description': 'Mechanical, electrical, plumbing installation',
                    'duration': 30,
                    'start_date': base_date + timedelta(days=170),
                    'priority': 'HIGH',
                    'phase': 'Construction Phase 2'
                },
                {
                    'name': 'Buildings D-F Interior Finishes',
                    'description': 'Interior finishes and fixtures',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=195),
                    'priority': 'MEDIUM',
                    'phase': 'Construction Phase 2'
                },
                
                # Amenities and Common Areas
                {
                    'name': 'Community Center Construction',
                    'description': 'Build community center and clubhouse',
                    'duration': 35,
                    'start_date': base_date + timedelta(days=180),
                    'priority': 'MEDIUM',
                    'phase': 'Amenities'
                },
                {
                    'name': 'Recreation Facilities',
                    'description': 'Pool, fitness center, and recreation areas',
                    'duration': 25,
                    'start_date': base_date + timedelta(days=200),
                    'priority': 'MEDIUM',
                    'phase': 'Amenities'
                },
                {
                    'name': 'Parking and Garages',
                    'description': 'Construct parking areas and garages',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=210),
                    'priority': 'MEDIUM',
                    'phase': 'Amenities'
                },
                
                # Final Phase
                {
                    'name': 'Landscaping and Hardscaping',
                    'description': 'Complete landscaping and outdoor improvements',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=230),
                    'priority': 'LOW',
                    'phase': 'Final'
                },
                {
                    'name': 'Final Inspections and CO',
                    'description': 'Final inspections and certificate of occupancy',
                    'duration': 10,
                    'start_date': base_date + timedelta(days=245),
                    'priority': 'HIGH',
                    'phase': 'Final'
                },
                {
                    'name': 'Marketing and Leasing Preparation',
                    'description': 'Prepare units for marketing and leasing',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=250),
                    'priority': 'MEDIUM',
                    'phase': 'Final'
                }
            ]
        }
    
    @staticmethod
    def create_industrial_warehouse_template():
        """Create industrial warehouse template"""
        base_date = datetime.now().date()
        
        return {
            'name': 'Industrial Warehouse',
            'description': 'Large-scale warehouse construction project',
            'tasks': [
                # Planning and Design
                {
                    'name': 'Industrial Design and Engineering',
                    'description': 'Specialized warehouse design and engineering',
                    'duration': 12,
                    'start_date': base_date,
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction'
                },
                {
                    'name': 'Site Survey and Soil Testing',
                    'description': 'Geotechnical analysis for heavy loading',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=5),
                    'priority': 'HIGH',
                    'phase': 'Pre-Construction'
                },
                
                # Site Work
                {
                    'name': 'Site Clearing and Grading',
                    'description': 'Large-scale site preparation',
                    'duration': 10,
                    'start_date': base_date + timedelta(days=20),
                    'priority': 'HIGH',
                    'phase': 'Site Work'
                },
                {
                    'name': 'Heavy Utility Installation',
                    'description': 'Industrial-grade utility installation',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=30),
                    'priority': 'HIGH',
                    'phase': 'Site Work'
                },
                
                # Foundation and Structure
                {
                    'name': 'Deep Foundation System',
                    'description': 'Piles and deep foundation for heavy loads',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=50),
                    'priority': 'HIGH',
                    'phase': 'Foundation'
                },
                {
                    'name': 'Concrete Floor Slab',
                    'description': 'Heavy-duty reinforced concrete flooring',
                    'duration': 12,
                    'start_date': base_date + timedelta(days=65),
                    'priority': 'HIGH',
                    'phase': 'Foundation'
                },
                {
                    'name': 'Structural Steel Erection',
                    'description': 'Pre-engineered steel building system',
                    'duration': 20,
                    'start_date': base_date + timedelta(days=80),
                    'priority': 'HIGH',
                    'phase': 'Structure'
                },
                
                # Building Envelope
                {
                    'name': 'Metal Building Envelope',
                    'description': 'Metal wall and roof panels',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=105),
                    'priority': 'HIGH',
                    'phase': 'Envelope'
                },
                {
                    'name': 'Loading Dock Construction',
                    'description': 'Truck docks and levelers',
                    'duration': 10,
                    'start_date': base_date + timedelta(days=120),
                    'priority': 'HIGH',
                    'phase': 'Envelope'
                },
                
                # Specialized Systems
                {
                    'name': 'Material Handling Systems',
                    'description': 'Conveyor and racking systems',
                    'duration': 18,
                    'start_date': base_date + timedelta(days=135),
                    'priority': 'MEDIUM',
                    'phase': 'Systems'
                },
                {
                    'name': 'Industrial Electrical Systems',
                    'description': 'High-voltage electrical and controls',
                    'duration': 12,
                    'start_date': base_date + timedelta(days=140),
                    'priority': 'HIGH',
                    'phase': 'Systems'
                },
                {
                    'name': 'Fire Suppression Systems',
                    'description': 'Industrial fire protection',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=155),
                    'priority': 'HIGH',
                    'phase': 'Systems'
                },
                
                # Final Work
                {
                    'name': 'Office Area Construction',
                    'description': 'Administrative office spaces',
                    'duration': 15,
                    'start_date': base_date + timedelta(days=160),
                    'priority': 'MEDIUM',
                    'phase': 'Final'
                },
                {
                    'name': 'Site Paving and Striping',
                    'description': 'Asphalt paving and traffic markings',
                    'duration': 8,
                    'start_date': base_date + timedelta(days=175),
                    'priority': 'MEDIUM',
                    'phase': 'Final'
                },
                {
                    'name': 'Final Testing and Commissioning',
                    'description': 'System testing and startup',
                    'duration': 5,
                    'start_date': base_date + timedelta(days=185),
                    'priority': 'HIGH',
                    'phase': 'Final'
                }
            ]
        }
    
    @classmethod
    def get_template(cls, template_id):
        """Get specific template by ID"""
        templates = {
            'commercial_office': cls.create_commercial_office_template,
            'residential_complex': cls.create_residential_complex_template,
            'industrial_warehouse': cls.create_industrial_warehouse_template
        }
        
        if template_id in templates:
            return templates[template_id]()
        else:
            raise ValueError(f"Template '{template_id}' not found")
    
    @staticmethod
    def calculate_project_metrics(template):
        """Calculate basic project metrics from template"""
        tasks = template.get('tasks', [])
        
        if not tasks:
            return {}
        
        total_duration = sum(task.get('duration', 0) for task in tasks)
        critical_tasks = len([task for task in tasks if task.get('priority') == 'HIGH'])
        phases = list(set(task.get('phase', 'Unknown') for task in tasks))
        
        # Calculate project timeline
        start_dates = [task.get('start_date') for task in tasks if task.get('start_date')]
        end_dates = []
        
        for task in tasks:
            if task.get('start_date') and task.get('duration'):
                end_date = task['start_date'] + timedelta(days=task['duration'])
                end_dates.append(end_date)
        
        project_start = min(start_dates) if start_dates else datetime.now().date()
        project_end = max(end_dates) if end_dates else datetime.now().date()
        
        return {
            'total_tasks': len(tasks),
            'total_duration_days': total_duration,
            'critical_tasks': critical_tasks,
            'phases': phases,
            'estimated_start': project_start,
            'estimated_end': project_end,
            'estimated_duration_weeks': (project_end - project_start).days // 7
        }