"""Unit tests for Phase 9 BrowserTool and HTML Content Extractor."""

import pytest
from unittest.mock import MagicMock
import requests
from tools.base import Action
from tools.browser_tool import BrowserTool, WebContentExtractor


def test_web_content_extractor():
  html_doc = """
  <!DOCTYPE html>
  <html>
    <head><title>Test Article Title</title></head>
    <body>
      <h1>Main Headline</h1>
      <h2>Subheading Information</h2>
      <p>This is the first paragraph with important details for the reader.</p>
      <p>Here is another paragraph containing insights and analytics data.</p>
      <a href="https://example.com/docs">Documentation Link</a>
      <script>console.log("ignore me");</script>
      <style>body { color: red; }</style>
    </body>
  </html>
  """
  parser = WebContentExtractor()
  parser.feed(html_doc)

  assert parser.title == "Test Article Title"
  assert len(parser.headings) == 2
  assert parser.headings[0]["text"] == "Main Headline"
  assert len(parser.paragraphs) == 2
  assert len(parser.links) == 1
  assert parser.links[0]["href"] == "https://example.com/docs"


@pytest.fixture
def mock_browser_tool() -> BrowserTool:
  mock_session = MagicMock(spec=requests.Session)
  sample_html = """
  <html>
    <head><title>Sample Web Page</title></head>
    <body>
      <h1>Featured News</h1>
      <p>Autonomous AI agents are transforming modern software engineering.</p>
      <a href="https://xeren.ai">Xeren AI</a>
    </body>
  </html>
  """
  mock_response = MagicMock()
  mock_response.text = sample_html
  mock_response.raise_for_status = MagicMock()
  mock_session.get.return_value = mock_response

  return BrowserTool(session=mock_session)


@pytest.mark.asyncio
async def test_browser_navigate_url(mock_browser_tool: BrowserTool):
  action = Action(
      action_id="b_01",
      tool_name="browser",
      operation="navigate_url",
      parameters={"url": "https://example.org"},
  )
  result = await mock_browser_tool.execute(action)
  assert result.success is True
  assert result.data["title"] == "Sample Web Page"
  assert len(result.data["headings"]) == 1


@pytest.mark.asyncio
async def test_browser_extract_page_content(mock_browser_tool: BrowserTool):
  action = Action(
      action_id="b_02",
      tool_name="browser",
      operation="extract_page_content",
      parameters={"url": "https://example.org/article"},
  )
  result = await mock_browser_tool.execute(action)
  assert result.success is True
  assert "Autonomous AI agents" in result.data["text_content"]
  assert result.data["word_count"] > 0
