FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai
WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python3 -m pip install --disable-pip-version-check --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --requirement requirements.txt

COPY local_ext/ ./local_ext/
COPY local_web/ ./local_web/
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin macro \
    && mkdir -p /data/local-ext \
    && chown -R 10001:10001 /app /data
USER 10001:10001
EXPOSE 8790
CMD ["sh", "-c", "exec python3 -m uvicorn local_ext.api.app:app --host 0.0.0.0 --port ${LOCAL_MACRO_API_PORT:-8790}"]
