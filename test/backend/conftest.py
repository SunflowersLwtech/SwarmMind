"""Backend test helpers — patches fastmcp CallToolResult for subscript access."""
from fastmcp.client.client import CallToolResult


# fastmcp v3.1.1 CallToolResult is not subscriptable, but tests expect
# result[0].text (old API style). Patch to delegate to .content list.
if not hasattr(CallToolResult, '__getitem__'):
    CallToolResult.__getitem__ = lambda self, idx: self.content[idx]
