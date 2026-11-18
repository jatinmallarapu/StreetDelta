# The API serves the bundled dashboard. Source imagery and model weights remain external.
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY streetdelta/ streetdelta/
COPY dashboard/ dashboard/
RUN python -m pip install --no-cache-dir .
ENV STREETDELTA_DASHBOARD=/app/dashboard PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","streetdelta.api:app","--host","0.0.0.0","--port","8000"]
