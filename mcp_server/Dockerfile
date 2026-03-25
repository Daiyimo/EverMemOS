FROM python:3.12-slim

WORKDIR /app

# Install MCP server dependencies only (lightweight)
COPY mcp_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server/server.py /app/server.py

# HTTP transport (for remote / plugin access)
EXPOSE 3456

ENV EVERMEMOS_BASE_URL=http://evermemos-app:1995
ENV MCP_PORT=3456

CMD ["python", "server.py", "--transport", "http", "--port", "3456"]
