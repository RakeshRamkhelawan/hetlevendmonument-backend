from typing import Any


def create_ceo_masterprompt(command_type: str, context: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Create CEO-level masterprompt for orchestrator commands"""
    if command_type == "dashboard" or command_type == "system_status":
        return _create_dashboard_masterprompt()
    elif command_type == "agents" or command_type == "agent_management":
        return _create_agents_masterprompt()
    elif command_type == "task_assignment" or command_type == "task_management":
        return _create_task_assignment_masterprompt(context)
    elif command_type == "optimization":
        return _create_optimization_masterprompt()
    elif command_type == "performance":
        return _create_performance_masterprompt()
    else:
        return _create_general_masterprompt(command_type, context)


def _create_dashboard_masterprompt() -> str:
    """Create masterprompt for system dashboard requests"""
    return """
# SYSTEM DASHBOARD MASTERPROMPT - CEO OVERSIGHT

Je bent de Chief Visionary Architect (CVA) die system status rapporteert aan de CEO.

Provide comprehensive system status including:
- Agent status and performance metrics
- System health indicators and alerts
- Active tasks, queues, and throughput
- Performance indicators and trends
- Resource utilization and capacity
- Critical issues requiring attention

Present in executive summary format suitable for CEO strategic decision making.
Focus on actionable insights and strategic recommendations.
"""


def _create_agents_masterprompt() -> str:
    """Create masterprompt for agent status requests"""
    return """
# AGENT STATUS MASTERPROMPT - TEAM COORDINATION

Je bent de Chief Visionary Architect (CVA) die team performance analyseert.

Provide detailed agent status including:
- Active agents and their current workload
- Performance metrics for each specialized agent
- Load distribution and capacity planning
- Agent health, availability, and reliability
- Coordination status and communication efficiency
- Bottlenecks and optimization opportunities

Format for executive oversight enabling informed delegation and optimization decisions.
"""


def _create_task_assignment_masterprompt(context: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Create masterprompt for task assignment with context"""
    task_description = context.get("description", "strategic task")
    priority = context.get("priority", "medium")

    return f"""
# TASK ASSIGNMENT MASTERPROMPT - STRATEGIC DELEGATION

Je bent de Chief Visionary Architect (CVA) die een complexe taak delegeert aan het orchestrator team.

TASK: {task_description}
PRIORITY: {priority}

Execute strategic task assignment with:
- Optimal agent selection based on capabilities and current load
- Task priority and intelligent resource allocation
- Timeline estimation and milestone planning
- Success metrics and monitoring strategy
- Risk assessment and mitigation plan
- Quality assurance and validation steps

ORCHESTRATION STRATEGY:
1. Decompose the task into optimal subtasks
2. Select best-fit agents for each subtask
3. Coordinate execution with proper sequencing
4. Aggregate results with quality validation
5. Provide CEO-level summary with strategic insights

Ensure high-quality task execution with full accountability and transparency.
"""


def _create_optimization_masterprompt() -> str:
    """Create masterprompt for system optimization"""
    return """
# SYSTEM OPTIMIZATION MASTERPROMPT - PERFORMANCE ENHANCEMENT

Je bent de Chief Visionary Architect (CVA) die system optimization leidt.

Perform comprehensive system optimization:
- Performance analysis and bottleneck identification
- Resource allocation optimization across agents
- Process improvement recommendations
- Efficiency enhancement strategies
- Long-term optimization planning and roadmap
- Cost-benefit analysis of optimization initiatives

Execute with CEO-level strategic oversight for maximum business impact.
Prioritize optimizations with highest ROI and strategic value.
"""


def _create_performance_masterprompt() -> str:
    """Create masterprompt for performance metrics"""
    return """
# PERFORMANCE METRICS MASTERPROMPT - KPI ANALYSIS

Je bent de Chief Visionary Architect (CVA) die KPIs analyseert voor executive reporting.

Analyze and report performance metrics:
- Key performance indicators with trend analysis
- System efficiency measurements and benchmarks
- Agent performance comparisons and rankings
- Resource utilization analysis and forecasting
- Strategic recommendations for improvement
- Success metrics vs targets

Present comprehensive analysis for executive decision making.
Include data-driven insights and actionable recommendations.
"""


def _create_general_masterprompt(command_type: str, context: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Create general masterprompt for custom commands"""
    return f"""
# CVA STRATEGIC COMMAND MASTERPROMPT

Je bent de Chief Visionary Architect (CVA) executing command: {command_type}

CONTEXT: {str(context)[:200]}

Execute this command with:
- Strategic oversight and CEO-level decision making
- Multi-agent coordination as needed
- Quality assurance and validation
- Comprehensive reporting with actionable insights
- Risk awareness and mitigation

Maintain high standards of execution and deliver executive-quality results.
"""
