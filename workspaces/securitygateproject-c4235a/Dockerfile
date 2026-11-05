FROM python:3.11-alpine
WORKDIR /app
COPY src/ /app/src/
COPY tests/ /app/tests/
RUN adduser -D -u 1001 agenthive && chown -R agenthive:agenthive /app
USER agenthive
ENTRYPOINT ["python3", "-m", "unittest", "discover", "-s", "tests"]
