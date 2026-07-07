# Deployment image for the Python services (planner, publishers, policy, operator).
# The Flutter commuter app is built separately (see commuter_app/).
FROM python:3.13-slim

WORKDIR /app
RUN pip install --no-cache-dir "atsdk>=0.2.70" pydantic "langgraph==1.0.9" gpxpy "folium==0.14.0"

COPY smart-route-planning-agent/src /app/src
COPY config /app/config
COPY scripts /app/scripts

ENV PYTHONPATH=/app/src
ENV ATSIGN_CONFIG=/app/config/ee_atsigns.json
ENV ATSIGN_PROFILE=vanity
# Each service mounts its own atKeys at $HOME/.atsign/keys
ENV HOME=/keys

# Default command is overridden per-service in compose.yaml
CMD ["python", "scripts/planner_subscriber.py"]
