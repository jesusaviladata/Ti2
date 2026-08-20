FROM python:3.11-slim-bookworm

WORKDIR /app

# pyodbc requires unixODBC at runtime. Install Microsoft's SQL Server driver
# so connection and backup operations also work inside the Linux container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unixodbc libgssapi-krb5-2 tzdata \
    && curl -sSL -o /tmp/packages-microsoft-prod.deb \
       https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

ENV SQLSERVER_DRIVER="ODBC Driver 18 for SQL Server"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
