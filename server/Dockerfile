FROM python:3.12-slim
WORKDIR /app
COPY server /app/server
RUN useradd --uid 10001 --create-home relay && mkdir -p /data && chown relay:relay /data
USER relay
ENV SHIFT_RELAY_HOST=0.0.0.0 SHIFT_RELAY_DB=/data/shift-relay.sqlite3 SHIFT_RELAY_USERS_FILE=/data/users.json
EXPOSE 8090
CMD ["python", "-m", "server.app"]
