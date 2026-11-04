"""
Unit Tests for Pagination Utility (SC-8.2)

Tests pagination parameters and response formatting.
"""

import pytest

from src.core.utils.pagination import PageInfo, PageParams, create_page_info, paginate_query


class TestPageParams:
    """Tests for PageParams dependency."""

    def test_default_values(self):
        """Test default pagination values."""
        # When used as dependency, Query provides defaults
        # In unit test, we pass values directly
        params = PageParams(page=1, size=20)
        assert params.page == 1
        assert params.size == 20
        assert params.skip == 0
        assert params.limit == 20

    def test_custom_page(self):
        """Test custom page number."""
        params = PageParams(page=3, size=10)
        assert params.page == 3
        assert params.skip == 20  # (3-1) * 10
        assert params.limit == 10

    def test_first_page_skip_is_zero(self):
        """Test first page has zero skip."""
        params = PageParams(page=1, size=50)
        assert params.skip == 0

    def test_large_page_number(self):
        """Test large page number calculation."""
        params = PageParams(page=100, size=25)
        assert params.skip == 2475  # (100-1) * 25


class TestPageInfo:
    """Tests for PageInfo response model."""

    def test_create_page_info_first_page(self):
        """Test page info for first page."""
        info = create_page_info(page=1, size=10, total=50)
        assert info.page == 1
        assert info.size == 10
        assert info.total == 50
        assert info.pages == 5
        assert info.has_next is True
        assert info.has_prev is False

    def test_create_page_info_last_page(self):
        """Test page info for last page."""
        info = create_page_info(page=5, size=10, total=50)
        assert info.has_next is False
        assert info.has_prev is True

    def test_create_page_info_single_page(self):
        """Test page info when only one page exists."""
        info = create_page_info(page=1, size=20, total=15)
        assert info.pages == 1
        assert info.has_next is False
        assert info.has_prev is False

    def test_create_page_info_empty_result(self):
        """Test page info with no results."""
        info = create_page_info(page=1, size=10, total=0)
        assert info.pages == 0
        assert info.has_next is False
        assert info.has_prev is False

    def test_create_page_info_partial_last_page(self):
        """Test pages calculation with partial last page."""
        info = create_page_info(page=1, size=10, total=25)
        assert info.pages == 3  # 25 items / 10 per page = 3 pages
