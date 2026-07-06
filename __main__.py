import sys

if len(sys.argv) > 1 and sys.argv[1] == "server":
    sys.argv.pop(1)
    from server import mcp
    mcp.run(transport="stdio")
else:
    from cli import cli
    cli()
