#!/usr/bin/env python3
"""
Data Analysis Agent - Specialized Agent for Data Processing
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union, cast
from collections.abc import Awaitable, Callable

from src.core.subagents.agent_factory import BaseAgent

logger = logging.getLogger(__name__)

AnalysisMethod = Callable[..., Awaitable[dict[str, object]]]


class DataAnalysisAgent(BaseAgent):
    """Specialized agent for data analysis tasks"""

    async def _agent_specific_init(self) -> None:
        """Initialize data analysis capabilities"""
        self.analysis_methods: dict[str, AnalysisMethod] = {
            "statistical_summary": self._statistical_summary,
            "pattern_recognition": self._pattern_recognition,
            "correlation_analysis": self._correlation_analysis,
            "trend_analysis": self._trend_analysis,
            "anomaly_detection": self._anomaly_detection,
        }
        logger.info(
            f"Data Analysis Agent {self.agent_id} initialized with {len(self.analysis_methods)} methods"
        )

    async def _execute_specific_task(
        self,
        task_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute data analysis task"""
        analysis_type = task_data.get("analysis_type", "statistical_summary")
        data = task_data.get("data", [])
        parameters = task_data.get("parameters", {})

        if analysis_type not in self.analysis_methods:
            return {
                "error": f"Unknown analysis type: {analysis_type}",
                "available_methods": list(self.analysis_methods.keys()),
            }

        # Execute the specific analysis
        analysis_method = self.analysis_methods[analysis_type]
        result = await analysis_method(data, parameters)

        return {
            "analysis_type": analysis_type,
            "result": result,
            "data_points_analyzed": len(data) if isinstance(data, list) else 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _statistical_summary(
        self,
        data: list[float],
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Comprehensive statistical analysis with numpy/pandas/scipy"""
        if not data:
            return {"success": False, "error": "No data provided"}

        try:
            import numpy as np
            import pandas as pd
            from scipy import stats

            # Convert to pandas Series for analysis
            df = pd.Series(data)

            # pandas 3.x typeert Series.std() en .var() als `Series | float` (anders dan
            # mean/median/min/max). Op deze 1-D Series is het altijd een scalar; via een
            # los getypeerde binding blijft float() de echte conversie doen.
            std_value: Any = df.std()  # TODO(TYPE): replace Any with concrete type
            variance_value: Any = df.var()  # TODO(TYPE): replace Any with concrete type

            # Basic statistics
            basic_stats = {
                "count": len(data),
                "mean": float(df.mean()),
                "median": float(df.median()),
                "std_dev": float(std_value),
                "variance": float(variance_value),
                "min": float(df.min()),
                "max": float(df.max()),
                "range": float(df.max() - df.min()),
            }

            # Quartiles and percentiles
            quartiles = {
                "q1": float(df.quantile(0.25)),
                "q2": float(df.quantile(0.50)),  # median
                "q3": float(df.quantile(0.75)),
                "iqr": float(df.quantile(0.75) - df.quantile(0.25)),
            }

            # Outlier detection using IQR method
            q1, q3 = quartiles["q1"], quartiles["q3"]
            iqr = quartiles["iqr"]
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outliers = [x for x in data if x < lower_bound or x > upper_bound]

            # Distribution analysis
            distribution_analysis: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            if len(data) >= 8:  # Minimum for normality test
                shapiro_stat, shapiro_p = stats.shapiro(data[:5000])  # Limit for performance
                distribution_analysis = {
                    "shapiro_wilk_statistic": float(shapiro_stat),
                    "shapiro_wilk_p_value": float(shapiro_p),
                    "is_normally_distributed": bool(shapiro_p > 0.05),
                    "skewness": float(stats.skew(data)),
                    "kurtosis": float(stats.kurtosis(data)),
                }

            return {
                "success": True,
                "basic_statistics": basic_stats,
                "quartiles": quartiles,
                "outliers": {
                    "count": len(outliers),
                    "values": outliers,
                    "bounds": {"lower": lower_bound, "upper": upper_bound},
                },
                "distribution": distribution_analysis,
                "data_quality": {
                    "has_missing": any(pd.isna([x]) for x in data),
                    "has_infinite": any(np.isinf([x]) for x in data if isinstance(x, (int, float))),
                    "outlier_percentage": (len(outliers) / len(data)) * 100,
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Statistical analysis failed: {str(e)}",
                "error_type": type(e).__name__,
            }

    async def _pattern_recognition(
        self,
        data: list[Any],  # TODO(TYPE): replace Any with concrete type
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Advanced pattern recognition using ML clustering techniques"""
        try:
            import numpy as np
            from sklearn.cluster import KMeans
            from sklearn.preprocessing import StandardScaler

            if not data or len(data) < 2:
                return {
                    "success": False,
                    "error": "Insufficient data for pattern recognition (minimum 2 points required)",
                }

            # Convert to numpy array and reshape for clustering
            np_data = np.array(data).reshape(-1, 1)

            # Standardize data for better clustering
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(np_data)

            # Determine optimal number of clusters using elbow method
            max_clusters = min(len(data) // 2, 10)  # Reasonable upper limit
            if max_clusters < 2:
                return {
                    "success": False,
                    "error": "Data too small for meaningful clustering",
                }

            inertias: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            k_range = range(1, max_clusters + 1)

            for k in k_range:
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=cast(str, 10))
                kmeans.fit(scaled_data)
                inertias.append(kmeans.inertia_)

            # Find elbow point (simplified method)
            optimal_k = 2  # Default
            if len(inertias) > 2:
                # Calculate rate of change to find elbow
                changes = [inertias[i - 1] - inertias[i] for i in range(1, len(inertias))]
                optimal_k = changes.index(max(changes)) + 2

            # Perform clustering with optimal k
            kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=cast(str, 10))
            cluster_labels = kmeans.fit_predict(scaled_data)

            # Analyze cluster patterns
            patterns: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for cluster_id in range(optimal_k):
                cluster_points = [
                    data[i] for i, label in enumerate(cluster_labels) if label == cluster_id
                ]
                patterns[f"cluster_{cluster_id}"] = {
                    "size": len(cluster_points),
                    "center": float(np.mean(cluster_points)),
                    "std_dev": float(np.std(cluster_points)),
                    "min": float(min(cluster_points)),
                    "max": float(max(cluster_points)),
                    "points": cluster_points[:10],  # Sample points (limit for output size)
                }

            # Calculate cluster separation quality (silhouette score)
            try:
                from sklearn.metrics import silhouette_score

                if len(set(cluster_labels)) > 1:  # Need at least 2 clusters
                    silhouette_avg = silhouette_score(scaled_data, cluster_labels)
                else:
                    silhouette_avg = 0.0
            except Exception as e:
                logger.debug(
                    f"Failed to calculate silhouette score for clustering: {str(e)}",
                    exc_info=False,
                )
                silhouette_avg = 0.0

            return {
                "success": True,
                "optimal_clusters": optimal_k,
                "patterns": patterns,
                "cluster_labels": cluster_labels.tolist(),
                "quality_metrics": {
                    "silhouette_score": float(silhouette_avg),
                    "inertias": inertias,
                    "total_data_points": len(data),
                },
                "algorithm": "KMeans with StandardScaler preprocessing",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Pattern recognition failed: {str(e)}",
                "error_type": type(e).__name__,
            }

    async def _correlation_analysis(
        self,
        data: dict[str, list[Any]],  # TODO(TYPE): replace Any with concrete type
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze correlations between variables"""
        if not isinstance(data, dict) or len(data) < 2:
            return {"error": "Need at least 2 variables for correlation analysis"}

        correlations: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        variables = list(data.keys())

        # Simple correlation coefficient calculation
        for i, var1 in enumerate(variables):
            for var2 in variables[i + 1 :]:
                if len(data[var1]) == len(data[var2]) and len(data[var1]) > 1:
                    # Simplified correlation (Pearson-like)
                    corr_coef = self._calculate_correlation(data[var1], data[var2])
                    correlations[f"{var1}_vs_{var2}"] = {
                        "coefficient": corr_coef,
                        "strength": self._interpret_correlation_strength(corr_coef),
                    }

        return {
            "correlations": correlations,
            "variables_analyzed": len(variables),
            "total_comparisons": len(correlations),
        }

    def _calculate_correlation(self, x: list[float], y: list[float]) -> float:
        """Calculate correlation coefficient"""
        try:
            n = len(x)
            if n != len(y) or n < 2:
                return 0.0

            mean_x = sum(x) / n
            mean_y = sum(y) / n

            numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))

            sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
            sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))

            denominator = (sum_sq_x * sum_sq_y) ** 0.5

            return numerator / denominator if denominator != 0 else 0.0
        except Exception as e:
            logger.debug(f"Failed to calculate Pearson correlation: {str(e)}", exc_info=False)
            return 0.0

    def _interpret_correlation_strength(self, coef: float) -> str:
        """Interpret correlation strength"""
        abs_coef = abs(coef)
        if abs_coef >= 0.9:
            return "very_strong"
        elif abs_coef >= 0.7:
            return "strong"
        elif abs_coef >= 0.5:
            return "moderate"
        elif abs_coef >= 0.3:
            return "weak"
        else:
            return "very_weak"

    async def _trend_analysis(
        self,
        data: list[float],
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze trends in time series data"""
        if len(data) < 3:
            return {"error": "Need at least 3 data points for trend analysis"}

        # Simple trend analysis
        differences = [data[i + 1] - data[i] for i in range(len(data) - 1)]
        avg_change = sum(differences) / len(differences)

        trend_direction = (
            "increasing" if avg_change > 0 else "decreasing" if avg_change < 0 else "stable"
        )

        # Volatility measure
        volatility = sum(abs(diff - avg_change) for diff in differences) / len(differences)

        return {
            "trend_direction": trend_direction,
            "average_change": avg_change,
            "volatility": volatility,
            "data_points": len(data),
            "analysis_period": len(differences),
        }

    async def _anomaly_detection(
        self,
        data: list[float],
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Detect anomalies in data"""
        if len(data) < 5:
            return {"error": "Need at least 5 data points for anomaly detection"}

        threshold_method = parameters.get("method", "standard_deviation")
        sensitivity = parameters.get("sensitivity", 2.0)

        anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if threshold_method == "standard_deviation":
            import statistics

            mean = statistics.mean(data)
            std_dev = statistics.stdev(data)
            threshold = sensitivity * std_dev

            for i, value in enumerate(data):
                if abs(value - mean) > threshold:
                    anomalies.append(
                        {
                            "index": i,
                            "value": value,
                            "deviation": abs(value - mean),
                            "severity": "high" if abs(value - mean) > 2 * threshold else "medium",
                        }
                    )

        return {
            "anomalies_detected": len(anomalies),
            "anomalies": anomalies,
            "detection_method": threshold_method,
            "sensitivity": sensitivity,
            "data_points_analyzed": len(data),
        }
