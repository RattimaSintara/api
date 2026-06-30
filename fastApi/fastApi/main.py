from fastmcp import FastMCP

from fastApi.lxextract.service_lxextract import extract_citation, verify_citation

mcp = FastMCP("citation-extraction")


@mcp.tool()
def extract(text: str, model: str = "gpt-4.1-mini") -> dict:
    """Extract bibliographic metadata from an academic reference."""
    return extract_citation(text, model=model)


@mcp.tool()
def verify(text: str, model: str = "gpt-4.1-mini") -> dict:
    """Extract and verify bibliographic metadata against external sources."""
    return verify_citation(text, model=model)


if __name__ == "__main__":
    mcp.run()
