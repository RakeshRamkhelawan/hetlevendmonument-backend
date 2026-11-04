"""
Comprehensive tests for src/core/database/retry_utils.py
Coverage target: 100% of retry utilities
"""

import time
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from src.core.database.retry_utils import create_db_connection_with_retry, retry_database_operation


class TestRetryDatabaseOperation:
    """Test retry_database_operation decorator"""

    def test_successful_operation_on_first_try(self):
        """Test operation succeeds on first attempt"""
        # Arrange
        mock_func = Mock(return_value="success")
        decorated = retry_database_operation(max_retries=3)(mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_operational_error(self):
        """Test retries on OperationalError"""
        # Arrange
        mock_func = Mock(return_value="success", __name__="mock_func")
        mock_func.side_effect = [
            OperationalError("connection failed", None, None),
            OperationalError("connection failed", None, None),
            "success",
        ]
        decorated = retry_database_operation(max_retries=3, base_delay=0.01)(mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert mock_func.call_count == 3

    def test_retry_on_dbapi_error(self):
        """Test retries on DBAPIError"""
        # Arrange
        mock_func = Mock(return_value="success", __name__="mock_func")
        mock_func.side_effect = [DBAPIError("database error", None, None), "success"]
        decorated = retry_database_operation(max_retries=2, base_delay=0.01)(mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert mock_func.call_count == 2

    def test_max_retries_exceeded(self):
        """Test raises error when max retries exceeded"""
        # Arrange
        error = OperationalError("persistent error", None, None)
        mock_func = Mock(side_effect=error, __name__="mock_func")
        decorated = retry_database_operation(max_retries=2, base_delay=0.01)(mock_func)

        # Act & Assert
        with pytest.raises(OperationalError) as exc_info:
            decorated()

        assert mock_func.call_count == 3  # initial + 2 retries
        assert "persistent error" in str(exc_info.value)

    def test_exponential_backoff_delay(self):
        """Test exponential backoff increases delay"""
        # Arrange
        mock_func = Mock(return_value="success", __name__="mock_func")
        mock_func.side_effect = [
            OperationalError("error", None, None),
            OperationalError("error", None, None),
            "success",
        ]
        decorated = retry_database_operation(max_retries=2, base_delay=0.1, exponential_base=2.0)(
            mock_func
        )

        # Act
        with patch("time.sleep") as mock_sleep:
            result = decorated()

        # Assert
        assert result == "success"
        assert mock_sleep.call_count == 2
        # First retry: 0.1 * 2^0 = 0.1
        # Second retry: 0.1 * 2^1 = 0.2
        assert mock_sleep.call_args_list[0][0][0] == pytest.approx(0.1, rel=0.01)
        assert mock_sleep.call_args_list[1][0][0] == pytest.approx(0.2, rel=0.01)

    def test_max_delay_cap(self):
        """Test max_delay caps the backoff delay"""
        # Arrange
        mock_func = Mock(return_value="success", __name__="mock_func")
        mock_func.side_effect = [
            OperationalError("error", None, None),
            OperationalError("error", None, None),
            OperationalError("error", None, None),
            "success",
        ]
        decorated = retry_database_operation(
            max_retries=3, base_delay=1.0, max_delay=2.0, exponential_base=3.0
        )(mock_func)

        # Act
        with patch("time.sleep") as mock_sleep:
            result = decorated()

        # Assert
        assert result == "success"
        # Without cap: 1.0, 3.0, 9.0
        # With cap of 2.0: 1.0, 2.0, 2.0
        delays = [call_obj[0][0] for call_obj in mock_sleep.call_args_list]
        assert all(delay <= 2.0 for delay in delays)

    def test_preserves_function_metadata(self):
        """Test decorator preserves original function metadata"""

        # Arrange
        @retry_database_operation(max_retries=3)
        def test_function():
            """Test docstring"""
            return "result"

        # Assert
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test docstring"

    def test_passes_arguments_to_function(self):
        """Test decorator passes args and kwargs correctly"""
        # Arrange
        mock_func = Mock(return_value="success")
        decorated = retry_database_operation(max_retries=1)(mock_func)

        # Act
        result = decorated("arg1", "arg2", kwarg1="value1", kwarg2="value2")

        # Assert
        assert result == "success"
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")

    def test_non_database_errors_not_retried(self):
        """Test non-database errors are raised immediately"""
        # Arrange
        mock_func = Mock(side_effect=ValueError("not a database error"))
        decorated = retry_database_operation(max_retries=3)(mock_func)

        # Act & Assert
        with pytest.raises(ValueError):
            decorated()

        assert mock_func.call_count == 1  # No retries

    def test_logging_on_retry(self, caplog):
        """Test warning logged on retry attempts"""
        # Arrange
        import logging

        caplog.set_level(logging.WARNING)

        mock_func = Mock(side_effect=[OperationalError("connection failed", None, None), "success"])
        mock_func.__name__ = "test_func"
        decorated = retry_database_operation(max_retries=2, base_delay=0.01)(mock_func)

        # Act
        result = decorated()

        # Assert
        assert result == "success"
        assert any("test_func" in record.message for record in caplog.records)
        assert any("retrying" in record.message.lower() for record in caplog.records)

    def test_logging_on_max_retries_exceeded(self, caplog):
        """Test error logged when max retries exceeded"""
        # Arrange
        import logging

        caplog.set_level(logging.ERROR)

        mock_func = Mock(side_effect=OperationalError("persistent error", None, None))
        mock_func.__name__ = "failing_func"
        decorated = retry_database_operation(max_retries=1, base_delay=0.01)(mock_func)

        # Act
        with pytest.raises(OperationalError):
            decorated()

        # Assert
        assert any("failing_func" in record.message for record in caplog.records)
        assert any("failed after" in record.message for record in caplog.records)


class TestCreateDbConnectionWithRetry:
    """Test create_db_connection_with_retry function"""

    @patch("sqlalchemy.create_engine")
    def test_successful_connection(self, mock_create_engine):
        """Test successful database connection on first try"""
        # Arrange
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        database_url = "postgresql://user:pass@localhost/db"

        # Act
        engine = create_db_connection_with_retry(database_url, max_retries=3)

        # Assert
        assert engine == mock_engine
        mock_create_engine.assert_called_once()
        mock_conn.execute.assert_called_once()

    @patch("sqlalchemy.create_engine")
    def test_connection_with_retry(self, mock_create_engine):
        """Test connection succeeds after retries"""
        # Arrange
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Fail twice, then succeed
        mock_create_engine.side_effect = [
            OperationalError("connection failed", None, None),
            OperationalError("connection failed", None, None),
            mock_engine,
        ]

        database_url = "postgresql://user:pass@localhost/db"

        # Act
        with patch("time.sleep"):  # Speed up test
            engine = create_db_connection_with_retry(database_url, max_retries=3)

        # Assert
        assert engine == mock_engine
        assert mock_create_engine.call_count == 3

    @patch("sqlalchemy.create_engine")
    def test_connection_failure_after_max_retries(self, mock_create_engine):
        """Test raises error after max retries"""
        # Arrange
        mock_create_engine.side_effect = OperationalError("persistent error", None, None)
        database_url = "postgresql://user:pass@localhost/db"

        # Act & Assert
        with patch("time.sleep"):  # Speed up test
            with pytest.raises(OperationalError):
                create_db_connection_with_retry(database_url, max_retries=2)

        assert mock_create_engine.call_count == 3  # initial + 2 retries

    @patch("sqlalchemy.create_engine")
    def test_engine_configuration(self, mock_create_engine):
        """Test engine is configured with correct parameters"""
        # Arrange
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        database_url = "postgresql://user:pass@localhost/db"

        # Act
        create_db_connection_with_retry(database_url)

        # Assert
        call_kwargs = mock_create_engine.call_args[1]
        assert call_kwargs["pool_size"] == 20
        assert call_kwargs["max_overflow"] == 30
        assert call_kwargs["pool_timeout"] == 30
        assert call_kwargs["pool_recycle"] == 3600
        assert call_kwargs["pool_pre_ping"] is True

    @patch("sqlalchemy.create_engine")
    def test_connection_test_query(self, mock_create_engine):
        """Test connection is validated with SELECT 1 query"""
        # Arrange
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        database_url = "postgresql://user:pass@localhost/db"

        # Act
        create_db_connection_with_retry(database_url)

        # Assert - check that execute was called with a TextClause (text("SELECT 1"))
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]
        # The argument should be a TextClause object with "SELECT 1" text
        from sqlalchemy import text

        assert isinstance(call_args[0], type(text("")))
        assert str(call_args[0]) == "SELECT 1"

    @patch("sqlalchemy.create_engine")
    def test_logging_on_success(self, mock_create_engine, caplog):
        """Test success message is logged"""
        # Arrange
        import logging

        caplog.set_level(logging.INFO)

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_create_engine.return_value = mock_engine

        database_url = "postgresql://user:pass@localhost/db"

        # Act
        create_db_connection_with_retry(database_url)

        # Assert
        assert any(
            "connection established successfully" in record.message.lower()
            for record in caplog.records
        )
