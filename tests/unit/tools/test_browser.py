from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.browser import BrowserTool


@pytest.fixture
def browser_tool():
    return BrowserTool()


@pytest.mark.asyncio
@patch("src.tools.browser.async_playwright")
async def test_browser_scrape_happy_path(mock_playwright, browser_tool):
    mock_pw_context = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_playwright.return_value.__aenter__.return_value = mock_pw_context
    mock_pw_context.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Mock page interactions
    mock_page.goto = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body>1,234.50 USD</body></html>")

    result = await browser_tool.scrape_url("https://www.kitco.com")

    assert "1,234.50 USD" in result["content"]
    assert result["success"] is True

    mock_pw_context.chromium.launch.assert_called_once()
    mock_page.goto.assert_called_once_with("https://www.kitco.com", timeout=30000)
    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
@patch("src.tools.browser.async_playwright")
async def test_browser_scrape_timeout(mock_playwright, browser_tool):
    mock_pw_context = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_playwright.return_value.__aenter__.return_value = mock_pw_context
    mock_pw_context.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Simulate timeout
    from src.tools.browser import TimeoutError

    mock_page.goto.side_effect = TimeoutError("Timeout 30000ms exceeded")

    result = await browser_tool.scrape_url("https://www.kitco.com")

    assert result["success"] is False
    assert "Timeout" in result["error"]

    mock_browser.close.assert_called_once()
