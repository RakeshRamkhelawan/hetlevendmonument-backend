
from src.core.shared.interfaces import AgentCapability


def get_analyzer_capabilities() -> list[AgentCapability]:
    """Get analyzer agent capabilities"""
    return [
        AgentCapability(
            name="statistical_analysis",
            description="Comprehensive statistical analysis and hypothesis testing",
            input_types=["dataset", "data_request"],
            output_types=["analysis_report", "statistical_summary"],
            resource_requirements={"memory": "1GB", "cpu": "2.0"},
        ),
        AgentCapability(
            name="machine_learning",
            description="ML model development, training, and evaluation",
            input_types=["dataset", "ml_request"],
            output_types=["ml_model", "prediction_results", "model_evaluation"],
            resource_requirements={"memory": "2GB", "cpu": "4.0"},
        ),
        AgentCapability(
            name="data_preprocessing",
            description="Data cleaning, transformation, and feature engineering",
            input_types=["raw_dataset", "preprocessing_request"],
            output_types=["clean_dataset", "preprocessing_report"],
            resource_requirements={"memory": "1GB", "cpu": "1.5"},
        ),
        AgentCapability(
            name="pattern_recognition",
            description="Identify patterns, anomalies, and insights in data",
            input_types=["dataset", "pattern_request"],
            output_types=["pattern_analysis", "anomaly_report"],
            resource_requirements={"memory": "1.5GB", "cpu": "2.5"},
        ),
        AgentCapability(
            name="predictive_modeling",
            description="Build and deploy predictive models",
            input_types=["historical_data", "prediction_request"],
            output_types=["predictive_model", "forecasts", "confidence_intervals"],
            resource_requirements={"memory": "2GB", "cpu": "3.0"},
        ),
        AgentCapability(
            name="data_visualization",
            description="Create interactive visualizations and dashboards",
            input_types=["dataset", "visualization_request"],
            output_types=["charts", "dashboards", "visualization_code"],
            resource_requirements={"memory": "512MB", "cpu": "1.0"},
        ),
        AgentCapability(
            name="time_series_analysis",
            description="Analyze temporal data patterns and forecasting",
            input_types=["time_series_data", "forecasting_request"],
            output_types=["trend_analysis", "forecasts", "seasonality_report"],
            resource_requirements={"memory": "1.5GB", "cpu": "2.0"},
        ),
        AgentCapability(
            name="advanced_analytics",
            description="Complex analytical workflows and custom algorithms",
            input_types=["complex_dataset", "analytics_request"],
            output_types=["analytical_insights", "custom_analysis", "recommendations"],
            resource_requirements={"memory": "3GB", "cpu": "4.0"},
        ),
    ]
