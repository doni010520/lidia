#!/usr/bin/env bash
set -e

# Espera o postgres ficar pronto
echo "[entrypoint] aguardando postgres em $PGHOST..."
for i in $(seq 1 60); do
    if pg_isready -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" > /dev/null 2>&1; then
        echo "[entrypoint] postgres ok"
        break
    fi
    sleep 2
done

# Cria database se não existir
echo "[entrypoint] criando database $PGDATABASE (se necessário)..."
PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d postgres \
    -tc "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'" | grep -q 1 \
    || PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d postgres \
       -c "CREATE DATABASE \"$PGDATABASE\""

# Garante pgvector
PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null

# Aplica migrations idempotentemente
echo "[entrypoint] aplicando migrations..."
for f in /app/migrations/*.sql; do
    echo "  -> $(basename $f)"
    PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" \
        -v ON_ERROR_STOP=0 -f "$f" 2>&1 | grep -E "^(NOTICE|ERROR|psql:)" | head -5
done

echo "[entrypoint] iniciando uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
